"""Scan to MusicXML, shared by the command line and the web worker."""

from pathlib import Path

import music21 as m21

from . import audiveris
from .lyrics import clean_lyrics
from .pages import load_pages, save_tiff
from .parts import merge_parts


def transcribe(inputs: list[Path], out_dir: Path, log=print) -> list[Path]:
    """Recognise the pages in inputs and write one cleaned MusicXML per score Audiveris finds."""
    pages = load_pages(inputs)
    log(f"{len(pages)} page(s) loaded, first page {pages[0].width}x{pages[0].height}")
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    book = save_tiff(pages, work / f"{inputs[0].stem}.tif")
    results = []
    for mxl in audiveris.transcribe(book, work):
        score = clean_lyrics(merge_parts(m21.converter.parse(mxl)))
        dest = out_dir / mxl.with_suffix(".musicxml").name
        score.write("musicxml", dest)
        log(f"Wrote {dest} ({len(score.parts)} parts)")
        results.append(dest)
    return results
