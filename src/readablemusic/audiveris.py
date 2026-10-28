"""Run Audiveris in batch mode."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

REPO_TOOLS = Path(__file__).resolve().parents[2] / "tools"
SECONDS_PER_PAGE = 180  # normally 25-50 s; Audiveris can hang on odd pages


class AudiverisError(RuntimeError):
    pass


def find_executable() -> Path:
    if env := os.environ.get("READABLEMUSIC_AUDIVERIS"):
        return Path(env)
    local = REPO_TOOLS / "audiveris" / "Audiveris" / "Audiveris.exe"
    if local.exists():
        return local
    for name in ("audiveris", "Audiveris"):
        if found := shutil.which(name):
            return Path(found)
    linux = Path("/opt/audiveris/bin/Audiveris")
    if linux.exists():
        return linux
    raise AudiverisError("Audiveris not found; run scripts/fetch_tools.py or set READABLEMUSIC_AUDIVERIS")


def transcribe(image: Path, out_dir: Path) -> list[Path]:
    """Transcribe an image file (possibly multi-page) and return the exported .mxl files.

    The Audiveris project is kept next to them as <stem>.omr, for export().
    """
    with Image.open(image) as img:
        timeout = 60 + SECONDS_PER_PAGE * getattr(img, "n_frames", 1)
    return _run(["-transcribe", "-export"], image, out_dir, timeout, "audiveris.log")


def export(omr: Path, out_dir: Path) -> list[Path]:
    """Export the .mxl files again from a (possibly edited) Audiveris project."""
    return _run(["-export"], omr, out_dir, 120, "audiveris-export.log")


def _run(steps: list[str], source: Path, out_dir: Path, timeout: int, log_name: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if "TESSDATA_PREFIX" not in env and (REPO_TOOLS / "tessdata").exists():
        env["TESSDATA_PREFIX"] = str(REPO_TOOLS / "tessdata")
    log = out_dir / log_name
    # The Windows launcher garbles non-ASCII arguments, so Audiveris works in a temporary
    # folder on an ASCII-named copy, and the results are moved back afterwards.
    with tempfile.TemporaryDirectory(prefix="audiveris-") as tmp:
        book = Path(tmp) / f"book{source.suffix}"
        shutil.copy(source, book)
        cmd = [str(find_executable()), "-batch", *steps, "-output", tmp, "--", str(book)]
        with log.open("w", encoding="utf-8") as f:
            try:
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env, timeout=timeout)
            except subprocess.TimeoutExpired:
                raise AudiverisError(f"Audiveris took longer than {timeout} s, see {log}")
        if source.suffix != ".omr" and (Path(tmp) / "book.omr").exists():
            shutil.move(Path(tmp) / "book.omr", out_dir / f"{source.stem}.omr")
        # A book with several movements is exported as book.mvt1.mxl, book.mvt2.mxl, ...
        exported = []
        for mxl in sorted(Path(tmp).glob("book*.mxl")):
            dest = out_dir / (source.stem + mxl.name[len("book"):])
            shutil.move(mxl, dest)
            exported.append(dest)
    if result.returncode != 0 or not exported:
        raise AudiverisError(f"Audiveris failed (exit {result.returncode}), see {log}")
    return exported
