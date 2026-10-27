"""Run Audiveris in batch mode."""

import os
import shutil
import subprocess
from pathlib import Path

REPO_TOOLS = Path(__file__).resolve().parents[2] / "tools"


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
    """Transcribe an image file (possibly multi-page) and return the exported .mxl files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if "TESSDATA_PREFIX" not in env and (REPO_TOOLS / "tessdata").exists():
        env["TESSDATA_PREFIX"] = str(REPO_TOOLS / "tessdata")
    cmd = [str(find_executable()), "-batch", "-transcribe", "-export",
           "-output", str(out_dir), "--", str(image)]
    log = out_dir / "audiveris.log"
    with log.open("w", encoding="utf-8") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
    # A book with several movements is exported as <stem>.mvt1.mxl, <stem>.mvt2.mxl, ...
    exported = sorted(out_dir.glob(f"{image.stem}*.mxl"))
    if result.returncode != 0 or not exported:
        raise AudiverisError(f"Audiveris failed (exit {result.returncode}), see {log}")
    return exported
