"""Run the pipeline on the evaluation set and score it against the known answers.

Usage: uv run python eval/run.py [variant ...]   (variants: satb shared bad; default all)
"""

import statistics
import sys
import time
from pathlib import Path

from readablemusic import audiveris
from readablemusic.pipeline import transcribe
from score import compare

DATA = Path(__file__).parent / "data"
RESULTS = Path(__file__).parent / "results"
TRUTH = {"satb": "truth-satb.musicxml", "shared": "truth-shared.musicxml", "bad": "truth-satb.musicxml"}


def run_one(piece: Path, variant: str) -> Path:
    pages = sorted((piece / variant).glob("page-*"), key=lambda p: int(p.stem.split("-")[1]))
    return transcribe(pages, RESULTS / variant / piece.name, log=lambda msg: None)[0]


def main() -> None:
    variants = sys.argv[1:] or list(TRUTH)
    for variant in variants:
        f1s, lyrics = [], []
        print(f"=== {variant}")
        for piece in sorted(p for p in DATA.iterdir() if p.is_dir()):
            start = time.monotonic()
            try:
                result = compare(str(piece / TRUTH[variant]), str(run_one(piece, variant)))
            except audiveris.AudiverisError as e:
                print(f"  {piece.name:10} FAILED: {e}")
                f1s.append(0.0)
                lyrics.append(0.0)
                continue
            f1s.append(result.note_f1)
            lyrics.append(result.lyrics)
            print(f"  {piece.name:10} notes F1 {result.note_f1:6.1%}  lyrics {result.lyrics:6.1%}  "
                  f"staves {result.staves_found}/{result.staves_truth}  {time.monotonic() - start:4.0f}s", flush=True)
        print(f"  {'MEAN':10} notes F1 {statistics.mean(f1s):6.1%}  lyrics {statistics.mean(lyrics):6.1%}", flush=True)


if __name__ == "__main__":
    main()
