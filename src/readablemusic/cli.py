"""Command line: readablemusic INPUT... -o OUT_DIR"""

import argparse
import sys
import time
from pathlib import Path

from .engrave import to_pdf
from .pipeline import PoorImage, transcribe


def main() -> None:
    parser = argparse.ArgumentParser(prog="readablemusic", description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="PDF or image files, in page order")
    parser.add_argument("-o", "--out", type=Path, default=Path("out"), help="output folder")
    parser.add_argument("--check", action="store_true",
                        help="stop before Claude reads pages that look too poor, as the web app does")
    args = parser.parse_args()

    start = time.monotonic()
    try:
        results = transcribe(args.inputs, args.out, check=args.check)
    except PoorImage as e:
        print("Stopped, the pages look too poor to read well:", *e.problems, sep="\n  ")
        if e.cost is not None:
            print(f"Claude's reading would cost about ${e.cost:.2f}; run without --check to read them anyway.")
        sys.exit(2)
    for dest in results:
        pdf = dest.with_suffix(".pdf")
        print(f"Wrote {pdf} ({to_pdf(dest, pdf)} pages)")
    print(f"Done in {time.monotonic() - start:.0f}s")
