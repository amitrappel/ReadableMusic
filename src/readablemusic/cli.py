"""Command line: readablemusic INPUT... -o OUT_DIR"""

import argparse
import time
from pathlib import Path

from .engrave import to_pdf
from .pipeline import transcribe


def main() -> None:
    parser = argparse.ArgumentParser(prog="readablemusic", description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="PDF or image files, in page order")
    parser.add_argument("-o", "--out", type=Path, default=Path("out"), help="output folder")
    args = parser.parse_args()

    start = time.monotonic()
    for dest in transcribe(args.inputs, args.out):
        pdf = dest.with_suffix(".pdf")
        print(f"Wrote {pdf} ({to_pdf(dest, pdf)} pages)")
    print(f"Done in {time.monotonic() - start:.0f}s")
