"""Scan to MusicXML, shared by the command line and the web worker."""

from pathlib import Path

import music21 as m21

from . import audiveris
from .cleanup import blank_outside_music
from .lyrics import clean_lyrics
from .pages import load_pages, save_tiff
from .parts import merge_parts
from .scale import staff_evidence
from .textlayer import fix_lyrics, has_text
from .tidy import tidy

MIN_STAFF_SHARE = 0.1  # pages with less staff evidence than this share of the best page may hold no music


def transcribe(inputs: list[Path], out_dir: Path, log=print) -> list[Path]:
    """Recognise the pages in inputs and write one cleaned MusicXML per score Audiveris finds."""
    pages = load_pages(inputs)
    log(f"{len(pages)} page(s) loaded, first page {pages[0].width}x{pages[0].height}")
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    support = [staff_evidence(page)[1] for page in pages]
    # All pages share one scale (see pages.py), so the best page's interline holds for all.
    interline = staff_evidence(pages[support.index(max(support))])[0]
    pages = [blank_outside_music(page, interline) for page in pages]
    try:
        mxls = audiveris.transcribe(save_tiff(pages, work / f"{inputs[0].stem}.tif"), work)
    except audiveris.AudiverisError:
        # Audiveris fails the whole book on a page without staves (e.g. lyrics only).
        # Noisy music pages can look just as empty, so drop such pages only on failure.
        music = [page for page, s in zip(pages, support) if s >= MIN_STAFF_SHARE * max(support)]
        if len(music) == len(pages):
            raise
        log(f"Audiveris failed; retrying without {len(pages) - len(music)} page(s) that look staff-less")
        mxls = audiveris.transcribe(save_tiff(music, work / f"{inputs[0].stem}.tif"), work)
        pages = music
    # PDFs from notation software carry the real lyrics as text; sheet n must be page n.
    source = inputs[0]
    if len(inputs) == 1 and source.suffix.lower() == ".pdf" and len(pages) == len(support) \
            and has_text(source):
        omr = work / f"{source.stem}.omr"
        if (fixed := fix_lyrics(omr, source)):
            try:
                mxls = audiveris.export(omr, work)
                log(f"Corrected {fixed} syllable(s) from the PDF text")
            except audiveris.AudiverisError as e:
                log(f"Keeping the OCR'd lyrics; re-export failed: {e}")
    results = []
    for mxl in mxls:
        score = tidy(clean_lyrics(merge_parts(m21.converter.parse(mxl))))
        dest = out_dir / mxl.with_suffix(".musicxml").name
        score.write("musicxml", dest, makeNotation=False)  # Audiveris output is already notated
        log(f"Wrote {dest} ({len(score.parts)} parts)")
        results.append(dest)
    return results
