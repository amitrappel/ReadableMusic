"""Download Audiveris and English OCR data into ./tools (Windows development setup).

Usage: uv run python scripts/fetch_tools.py
On Linux the Docker image installs Audiveris from its .deb package instead.
"""

import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

AUDIVERIS_VERSION = "5.11.0"
AUDIVERIS_MSI = (
    f"https://github.com/Audiveris/audiveris/releases/download/{AUDIVERIS_VERSION}/"
    f"Audiveris-{AUDIVERIS_VERSION}-windowsConsole-x86_64.msi"
)
TESSDATA_ENG = "https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata"

TOOLS = Path(__file__).resolve().parent.parent / "tools"


def download(url: str, dest: Path) -> None:
    print(f"Downloading {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)


def main() -> None:
    if sys.platform != "win32":
        sys.exit("This script is for Windows; on Linux install the Audiveris .deb package.")

    target = TOOLS / "audiveris"
    if not (target / "Audiveris" / "Audiveris.exe").exists():
        with tempfile.TemporaryDirectory() as tmp:
            msi = Path(tmp) / "audiveris.msi"
            download(AUDIVERIS_MSI, msi)
            # Administrative install: unpacks the files without installing system-wide.
            subprocess.run(
                ["msiexec", "/a", str(msi), "/qn", f"TARGETDIR={target}"], check=True
            )

    eng = TOOLS / "tessdata" / "eng.traineddata"
    if not eng.exists():
        download(TESSDATA_ENG, eng)

    print(f"Tools ready in {TOOLS}")


if __name__ == "__main__":
    main()
