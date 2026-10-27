"""Command line: readablemusic INPUT... -o OUT_DIR"""

import argparse
import time
from pathlib import Path

import music21 as m21

from . import audiveris
from .engrave import to_pdf
from .lyrics import clean_lyrics
from .pages import load_pages, save_tiff
from .parts import merge_parts


def main() -> None:
    parser = argparse.ArgumentParser(prog="readablemusic", description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="PDF or image files, in page order")
    parser.add_argument("-o", "--out", type=Path, default=Path("out"), help="output folder")
    args = parser.parse_args()

    start = time.monotonic()
    pages = load_pages(args.inputs)
    print(f"{len(pages)} page(s) loaded, first page {pages[0].width}x{pages[0].height}")

    work = args.out / "work"
    work.mkdir(parents=True, exist_ok=True)
    book = save_tiff(pages, work / f"{args.inputs[0].stem}.tif")
    for mxl in audiveris.transcribe(book, work):
        score = clean_lyrics(merge_parts(m21.converter.parse(mxl)))
        dest = args.out / mxl.with_suffix(".musicxml").name
        score.write("musicxml", dest)
        print(f"Wrote {dest} ({len(score.parts)} parts)")
        pdf = dest.with_suffix(".pdf")
        print(f"Wrote {pdf} ({to_pdf(dest, pdf)} pages)")
    print(f"Done in {time.monotonic() - start:.0f}s")
