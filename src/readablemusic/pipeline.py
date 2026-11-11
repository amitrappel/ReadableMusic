"""Scan to MusicXML, shared by the command line and the web worker."""

import json
import os
import zipfile
from dataclasses import asdict
from pathlib import Path

import music21 as m21
import pypdfium2 as pdfium

from . import audiveris
from .clefs import fix_clefs
from .chords import add_chords, text_chords
from .cleanup import blank_outside_music, music_band, whiten
from .engrave import line_breaks
from .fresh import poor, read_fresh
from .lyrics import clean_lyrics, drop_stray_lines
from .ocr import read_scan_text, repair_hebrew_credits
from .pages import load_pages, save_tiff, uploaded_interline
from .pagetext import (CREDITS, Bounds, Item, add_directions, drop_repeated_text, measure_places, read_page_text,
                       stacked_names, write_page_text)
from .parts import merge_parts, standardize_names
from .reader import beam, open_endings, page_systems, read_again
from .scale import staff_evidence
from .staves import print_accidentals
from .symbols import fix_symbols
from .textlayer import fix_text, has_text
from .tidy import tidy
from .vision import Reading, ask, correct

MIN_STAFF_SHARE = 0.1  # pages with less staff evidence than this share of the best page may hold no music
MIN_INTERLINE = 7  # pixels between staff lines in an uploaded image; the scans read well had 8 and more
SYSTEM_COST = 0.08  # dollars, about, for Claude's reading of a system
KEPT = "first page.json"  # Claude's first-page reading, kept by a run the check stopped for the next


class PoorImage(Exception):
    """The pages look too poor to read well. problems say why, for the person who uploaded
    them; cost is about what Claude's reading of them would cost, None where it does not run."""

    def __init__(self, problems: list[str], cost: float | None):
        super().__init__(problems, cost)
        self.problems, self.cost = problems, cost


def _read_text(source: Path, pages: list, interline: float) -> list[Item]:
    pdf = pdfium.PdfDocument(source)
    bounds = []
    for n, page in enumerate(pages):
        band = music_band(page, interline)
        k = pdf[n].get_width() / page.width  # points per pixel
        bounds.append(Bounds(band.top * k, band.first * k, band.last * k, band.bottom * k) if band else None)
    return read_page_text(source, bounds)


def _measures(mxl: Path) -> int:
    """How many measures the first part of a compressed MusicXML file has."""
    with zipfile.ZipFile(mxl) as z:
        xml = z.read(next(n for n in z.namelist() if n.endswith(".xml") and not n.startswith("META-INF"))).decode()
    return xml[:xml.find("</part>")].count("<measure ")


def _sheets(inputs: list[Path], kept: list[int]) -> list:
    """The pages Audiveris read, as loaded and before any text was whitened."""
    pages = load_pages(inputs)
    return [pages[k] for k in kept]


def _uploaded(inputs: list[Path]) -> list[list]:
    return [[path.name, path.stat().st_size] for path in inputs]


def _keep(work: Path, inputs: list[Path], reading: Reading) -> None:
    (work / KEPT).write_text(json.dumps({"inputs": _uploaded(inputs), "reading": asdict(reading)}), encoding="utf-8")


def _kept(work: Path, inputs: list[Path]) -> Reading | None:
    """The first-page reading that a run of the same inputs, stopped by the check, kept;
    it goes to this run only."""
    if not (path := work / KEPT).is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    path.unlink()
    if data["inputs"] != _uploaded(inputs):
        return None
    return Reading(**{key: tuple(v) if key in ("notes", "problems") else v for key, v in data["reading"].items()})


def _problems(reading: Reading | None, why: str) -> list[str]:
    """What makes a scan too poor to read well, for the person who uploaded it: Audiveris's
    reading too poor to correct (why), or Claude's view of the page; [] if neither."""
    if not why and not (reading and reading.legibility == "poor"):
        return []
    problems = ["Audiveris, which recognises the music, could read little of it."] if why else []
    if reading and reading.legibility != "clear":
        problems += [p[0].upper() + p[1:] for p in reading.problems] or ["Claude could not read much of the page."]
    return problems


def transcribe(inputs: list[Path], out_dir: Path, log=print, check: bool = False) -> list[Path]:
    """Recognise the pages in inputs and write one cleaned MusicXML per score Audiveris finds.
    With check, raise PoorImage instead where the pages look too poor to read well, before
    Claude reads them."""
    if check and (found := uploaded_interline(inputs)) and found < MIN_INTERLINE:
        raise PoorImage([f"The staff lines are only {found:.0f} pixels apart in the image, too few for the notes."],
                        None)
    pages = load_pages(inputs)
    first_page = pages[0]  # as printed, for Claude; sheet 1 of Audiveris's project
    log(f"{len(pages)} page(s) loaded, first page {pages[0].width}x{pages[0].height}")
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    support = [staff_evidence(page)[1] for page in pages]
    # All pages share one scale (see pages.py), so the best page's interline holds for all.
    interline = staff_evidence(pages[support.index(max(support))])[0]
    # First separate the text from the music. PDFs from notation software carry it as text.
    source = inputs[0]
    text_pdf = len(inputs) == 1 and source.suffix.lower() == ".pdf" and has_text(source)
    items = _read_text(source, pages, interline) if text_pdf else []
    # A PDF can hold text that is no use here: music symbols, or none of the credits.
    scanned = not any(i.kind in CREDITS for i in items)
    points = [pdfium.PdfDocument(source)[n].get_width() / page.width for n, page in enumerate(pages)] \
        if not scanned else [1.0] * len(pages)
    if scanned:
        # OCR just above a staff can read high notes as letters; whitening them would lose music.
        items = [i for i in read_scan_text(pages, [music_band(page, interline) for page in pages])
                 if i.kind != "direction"]
    elif (repaired := repair_hebrew_credits(items, pages, points)):
        log(f"Restored letters missing from the PDF's text in {repaired} credit(s)")
    if items:
        log("Text on the page: " + "; ".join(f"{i.kind}: {i.text}" for i in items if i.kind in CREDITS))

    def boxes(n: int, music: bool) -> list[tuple]:
        return [tuple(v / points[n] for v in i.box) for i in items if i.page == n and (i.kind == "music") == music]

    pages = [whiten(blank_outside_music(page, interline, keep=boxes(n, True)), boxes(n, False))
             for n, page in enumerate(pages)]
    kept = list(range(len(pages)))  # page of each of Audiveris's sheets
    try:
        mxls = audiveris.transcribe(save_tiff(pages, work / f"{inputs[0].stem}.tif"), work)
    except audiveris.AudiverisError:
        # Audiveris fails the whole book on a page without staves (e.g. lyrics only).
        # Noisy music pages can look just as empty, so drop such pages only on failure.
        kept = [k for k, s in enumerate(support) if s >= MIN_STAFF_SHARE * max(support)]
        music = [pages[k] for k in kept]
        if len(music) == len(pages):
            raise
        log(f"Audiveris failed; retrying without {len(pages) - len(music)} page(s) that look staff-less")
        mxls = audiveris.transcribe(save_tiff(music, work / f"{inputs[0].stem}.tif"), work)
        pages = music
        if support[0] < MIN_STAFF_SHARE * max(support):
            first_page = None  # Audiveris's first sheet is another page
    # The real lyrics, words, accidentals and ties are in the PDF's text and drawing;
    # sheet n must be page n.
    if text_pdf and len(pages) == len(support):
        omr = work / f"{source.stem}.omr"
        fixed = fix_text(omr, source)
        accidentals, ties = fix_symbols(omr, source)
        if fixed or accidentals or ties:
            try:
                mxls = audiveris.export(omr, work)
                log(f"Corrected {fixed} lyric syllable(s) or word(s) from the PDF text")
                log(f"Corrected {accidentals} accidental(s) and added {ties} tie(s) from the PDF drawing")
            except audiveris.AudiverisError as e:
                log(f"Keeping Audiveris's first reading; re-export failed: {e}")
    # Claude checks the first system's clefs, key and time, and reads credits better than OCR.
    reading = _kept(work, inputs) or (ask(first_page, work / f"{inputs[0].stem}.omr", log) if first_page else None)
    if reading and reading.legibility != "clear":
        log(f"Claude can read the page {reading.legibility}: {'; '.join(reading.problems) or 'no reason given'}")
    # On a scan Claude reads each system again, with Audiveris's reading as its draft, and
    # its chord symbols; a notation program prints them as text. Claude's pitches are as
    # printed, so the notes are read under the right clef and key before, not after. Where
    # Audiveris's reading is too poor to be a draft, Claude reads the systems itself.
    rewritten, chords = set(), []
    if scanned:
        if reading and (changed := correct(mxls[0], reading, scan=True)):
            log(f"Read again as Claude saw the first system: {changed}")
        omr = work / f"{inputs[0].stem}.omr"
        why = poor(mxls[0], omr)
        if check and (problems := _problems(reading, why)):
            if reading:
                _keep(work, inputs, reading)
            key = os.environ.get("ANTHROPIC_API_KEY")
            raise PoorImage(problems, SYSTEM_COST * len(page_systems(omr)) if key else None)
        if os.environ.get("ANTHROPIC_API_KEY") and why:
            log(f"Claude reads the systems itself, as Audiveris's reading is too poor to correct ({why})")
            rewritten, chords = read_fresh(mxls[0], omr, lambda: _sheets(inputs, kept), log)
        else:
            rewritten, chords = read_again(mxls[0], omr, lambda: _sheets(inputs, kept), log)
    elif len(pages) == len(support):
        chords = text_chords(source, work / f"{source.stem}.omr", _measures(mxls[0]))
    if reading and (reading.credits or reading.notes) and scanned:
        # OCR takes a footnote close to the music for lyrics, and keeps only the rest of it.
        replaced = (CREDITS if reading.credits else ()) + (("note", "rights") if reading.notes else ())
        items = [i for i in items if i.kind not in replaced] + reading.items(0)
    stacked = stacked_names(source) if text_pdf else {}
    results = []
    for n, mxl in enumerate(mxls):
        raw = m21.converter.parse(mxl)
        if n == 0:
            beam(raw, rewritten)
        # Only the first score is known to start on the first page.
        places = measure_places(raw, interline) if n == 0 and len(pages) == len(support) else []
        score = merge_parts(drop_stray_lines(raw), slurs=n == 0 and bool(rewritten))
        if (clefs := fix_clefs(score, move=not rewritten)):
            log(f"{'Gave' if rewritten else 'Reread'} {clefs} stretch(es) of music the clef of the rest of their part")
        footnotes = standardize_names(score, stacked)
        score = drop_repeated_text(tidy(clean_lyrics(score)), items)
        if (directions := add_directions(score, items, places, points)):
            log(f"Printed {directions} direction(s) from above the staves")
        if n == 0 and (added := add_chords(score, chords)):
            log(f"Printed {added} chord symbol(s)")
        dest = out_dir / mxl.with_suffix(".musicxml").name
        score.write("musicxml", dest, makeNotation=False)  # Audiveris output is already notated
        if n == 0 and rewritten:
            open_endings(dest)
        write_page_text(dest, items if n == 0 else [], footnotes)
        if n == 0 and reading and not scanned and (changed := correct(dest, reading)):
            log(f"Read again as Claude saw the first system: {changed}")
        dest.write_text(line_breaks(print_accidentals(dest.read_text(encoding="utf-8"))), encoding="utf-8")
        log(f"Wrote {dest} ({len(score.parts)} parts)")
        results.append(dest)
    return results
