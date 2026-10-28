"""Run the pipeline on every file in samples/raw (no answer keys; results are for inspection).

Usage: uv run python eval/samples.py [name-substring ...]
Writes work/samples/<stem>/ with the MusicXML, the PDF and Audiveris's log. Finished
samples are skipped; delete their folder to redo them.
"""

import sys
import time
import traceback
from pathlib import Path

from readablemusic.engrave import to_pdf
from readablemusic.pipeline import transcribe

RAW = Path("samples/raw")
OUT = Path("work/samples")


def main() -> None:
    wanted = sys.argv[1:]
    for src in sorted(RAW.iterdir()):
        if src.name == "README.md" or (wanted and not any(w in src.name for w in wanted)):
            continue
        dest = OUT / src.stem
        if any(dest.glob("*.pdf")):
            continue
        start = time.monotonic()
        try:
            for xml in transcribe([src], dest, log=lambda msg: None):
                to_pdf(xml, xml.with_suffix(".pdf"))
            print(f"{time.monotonic() - start:5.0f}s  ok      {src.name}", flush=True)
        except Exception:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
            print(f"{time.monotonic() - start:5.0f}s  FAILED  {src.name}", flush=True)


if __name__ == "__main__":
    main()
