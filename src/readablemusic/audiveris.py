"""Run Audiveris in batch mode."""

import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from PIL import Image

from .reread import _place

REPO_TOOLS = Path(__file__).resolve().parents[2] / "tools"
SECONDS_PER_PAGE = 180  # normally 25-50 s; Audiveris can hang on odd pages
# Left unset, Tesseract misses whole lines of lyrics: 24 syllables of 62 on Irish Blessing.
OCR_RESOLUTION = "org.audiveris.omr.text.tesseract.TesseractOrder.typicalImageResolution=300"
# A short last system, centred under the others (the one measure of אתה הצבת), is dropped
# as too short for a staff, and once kept, its indent starts a score of its own.
SHORT_STAVES = ("org.audiveris.omr.sheet.grid.LinesRetriever.minStaffLength=10",
                "org.audiveris.omr.sheet.ProcessingSwitches.indentations=false")


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
    options = [arg for option in (OCR_RESOLUTION, *SHORT_STAVES) for arg in ("-option", option)]
    return _run(["-transcribe", "-export", *options], image, out_dir, timeout, "audiveris.log")


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
    omr = source if source.suffix == ".omr" else out_dir / f"{source.stem}.omr"
    if len(exported) == 1 and omr.exists():
        header_clefs(exported[0], omr)
    return exported


SHAPE_OCTAVES = {"8VA": 1, "8VB": -1, "15MA": 2, "15MB": -2}


def _system_clefs(omr: Path) -> list[list[tuple[str, int, int] | None]]:
    """For each system of the project, in order, the clef in each staff's header as (sign,
    line, octave change): treble where Audiveris found none, None for other clefs."""
    out = []
    with zipfile.ZipFile(omr) as z:
        sheets = sorted((n for n in z.namelist() if re.fullmatch(r"sheet#\d+/sheet#\d+\.xml", n)),
                        key=lambda n: int(re.search(r"#(\d+)", n).group(1)))
        for name in sheets:
            xml = z.read(name).decode("utf-8")
            inters = {m.group(2): m.group(1) for m in re.finditer(r'<clef ([^>]*)id="(\d+)"', xml)}
            for system in re.findall(r"<system .*?</system>", xml, re.S):
                clefs = []
                for staff in re.split(r"(?=<staff id=)", system)[1:]:
                    found = re.search(r"<header[^>/]*>\s*<clef>(\d+)</clef>", staff)
                    if not found:
                        clefs.append(("G", 2, 0))  # how Audiveris reads a staff without a clef
                        continue
                    attrs = inters.get(found.group(1), "")
                    shape, pitch = re.search(r'shape="([A-Z_0-9]+)"', attrs), re.search(r'pitch="(-?\d+)"', attrs)
                    sign = shape.group(1)[0] if shape else ""
                    if sign not in "GFC" or not pitch or not shape.group(1).startswith(("G_CLEF", "F_CLEF", "C_CLEF")):
                        clefs.append(None)
                        continue
                    octave = SHAPE_OCTAVES.get(shape.group(1).rsplit("_", 1)[-1], 0)
                    clefs.append((sign, 3 - int(pitch.group(1)) // 2, octave))
                out.append(clefs)
    return out


def header_clefs(mxl: Path, omr: Path) -> int:
    """Write the clef at the start of each system as Audiveris read its notes. On a staff
    where it finds no clef it reads the notes as treble but writes no clef, so the clef
    before seems to go on (אתה הצבת, staff 4: E♭5 as G3 under the bass clef of staff 3).
    Only for parts of one staff each, one per staff of every system. Return the clefs written."""
    with zipfile.ZipFile(mxl) as z:
        name = next(n for n in z.namelist() if n.endswith(".xml") and not n.startswith("META-INF"))
        text = z.read(name).decode("utf-8")
    start = text.index("<score-partwise")
    root = ET.fromstring(text[start:])
    parts = root.findall("part")
    systems = _system_clefs(omr)
    if any(int(s.text or 1) > 1 for part in parts for s in part.iter("staves")) or \
            any(len(clefs) != len(parts) for clefs in systems):
        return 0
    written = 0
    for j, part in enumerate(parts):
        s, now = -1, None
        for m in part.findall("measure"):
            mark = m.find("print")
            if s < 0 or (mark is not None and "yes" in (mark.get("new-system"), mark.get("new-page"))):
                s += 1
                if s < len(systems) and m.find("attributes/clef") is None and (read := systems[s][j]) \
                        and read != now and now is not None:
                    attributes = m.find("attributes")
                    if attributes is None:
                        attributes = ET.Element("attributes")
                        m.insert(next((k for k, c in enumerate(m) if c.tag != "print"), len(m)), attributes)
                    clef = ET.Element("clef")
                    ET.SubElement(clef, "sign").text, ET.SubElement(clef, "line").text = read[0], str(read[1])
                    if read[2]:
                        ET.SubElement(clef, "clef-octave-change").text = str(read[2])
                    _place(attributes, clef)
                    written += 1
            for c in m.findall("attributes/clef"):
                now = (c.findtext("sign"), int(c.findtext("line") or 2), int(c.findtext("clef-octave-change") or 0))
    if written:
        with zipfile.ZipFile(mxl, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(name, text[:start] + ET.tostring(root, encoding="unicode"))
            z.writestr("META-INF/container.xml", '<?xml version="1.0" encoding="UTF-8"?><container>'
                       f'<rootfiles><rootfile full-path="{name}"/></rootfiles></container>')
    return written
