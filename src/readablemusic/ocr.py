"""Read the text around the music on a scanned page, with Tesseract.

Scans have no text layer, so this gives pagetext.py the lines it sorts in a PDF's. Only the
areas above and below the music are read. Each line is read in English, which also finds
the lines; one read poorly gets a second reading in Hebrew, since reading both languages
at once spoils the Latin text.
"""

import os
import re
from collections import Counter
from dataclasses import replace
from pathlib import Path

import tesserocr
from PIL import Image
from tesserocr import PSM, RIL, PyTessBaseAPI

from .audiveris import REPO_TOOLS
from .cleanup import Band
from .pagetext import CREDITS, LABELS, Bounds, Item, Line, sort_text

MIN_CONFIDENCE = 50  # below this a line is most likely not text at all
SURE = 80  # a line read this well in English is not tried in Hebrew
PAD = 0.15  # share of a line's height around it when it is whitened
HEBREW = re.compile(r"[֐-׿]")
CROP_PAD = 0.5  # share of a line's height kept around it for a reading on its own: tails need room


def _data_dir() -> Path:
    return Path(os.environ.get("TESSDATA_PREFIX") or REPO_TOOLS / "tessdata")


def _read_hebrew(hebrew: PyTessBaseAPI, image: Image.Image, box: tuple) -> tuple[int, str]:
    """Confidence and text of one line, in reading order, read with room around it."""
    pad = (box[3] - box[1]) * CROP_PAD
    hebrew.SetImage(image.crop((box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)))
    return hebrew.MeanTextConf(), " ".join(hebrew.GetUTF8Text().split())


def _read_lines(api: PyTessBaseAPI, image: Image.Image) -> list[tuple[int, str, tuple]]:
    """Confidence, text and box of each line in the image."""
    api.SetImage(image)
    api.Recognize()
    if not api.GetUTF8Text().strip():
        return []
    lines = []
    for r in tesserocr.iterate_level(api.GetIterator(), RIL.TEXTLINE):
        text = (r.GetUTF8Text(RIL.TEXTLINE) or "").strip()
        if text:
            lines.append((r.Confidence(RIL.TEXTLINE), text, r.BoundingBox(RIL.TEXTLINE)))
    return lines


def _read_area(english: PyTessBaseAPI, hebrew: PyTessBaseAPI | None, area: Image.Image, top: int) -> list[Line]:
    out = []
    for confidence, text, (x0, y0, x1, y1) in _read_lines(english, area):
        if hebrew and confidence < SURE:
            second_confidence, second = _read_hebrew(hebrew, area, (x0, y0, x1, y1))
            if len(HEBREW.findall(second)) >= 2 and second_confidence > confidence:
                confidence, text = second_confidence, second
        if confidence >= MIN_CONFIDENCE:
            pad = (y1 - y0) * PAD
            out.append(Line(text, (x0 - pad, y0 + top - pad, x1 + pad, y1 + top + pad)))
    return out


def restores_letters(text: str, shown: str) -> bool:
    """Whether a reading holds all of the text's Hebrew letters and more. Some PDFs also store
    words out of order, so the order is not compared."""
    had, has = Counter(HEBREW.findall(text)), Counter(HEBREW.findall(shown))
    return has.total() > had.total() and not had - has


def repair_hebrew_credits(items: list[Item], pages: list[Image.Image], points: list[float]) -> int:
    """Some PDFs' fonts lose letters from the text, here Hebrew final letters: 'החלו' for 'החלום'.

    A credit takes what the page shows only if that holds all the letters the text has, and
    more. The line may then turn out to have a label, or one more: 'מילים ולחן'.
    """
    data = _data_dir()
    if not (data / "heb.traineddata").exists():
        return 0
    repaired = 0
    with PyTessBaseAPI(path=str(data), lang="heb", psm=PSM.SINGLE_LINE) as hebrew:
        for item in list(items):
            if item.kind not in CREDITS or not HEBREW.search(item.text):
                continue
            page = pages[item.page].convert("L")
            confidence, shown = _read_hebrew(hebrew, page, tuple(v / points[item.page] for v in item.box))
            if confidence >= MIN_CONFIDENCE and restores_letters(item.text, shown):
                item.text = shown
                repaired += 1
                labels = [k for k, label in LABELS.items() if re.search(label, shown)]
                if labels and item.kind != "title":
                    item.kind = item.kind if item.kind in labels else labels[0]
                    items += [replace(item, kind=k) for k in labels if k != item.kind]
    return repaired


def read_scan_text(pages: list[Image.Image], bands: list[Band | None]) -> list[Item]:
    """Sort the text around the music of each scanned page; boxes are in pixels of the page."""
    data = _data_dir()
    if not (data / "eng.traineddata").exists():
        return []
    has_hebrew = (data / "heb.traineddata").exists()
    lines: list[list[Line]] = []
    with PyTessBaseAPI(path=str(data), lang="eng", psm=PSM.SPARSE_TEXT) as english:
        hebrew = PyTessBaseAPI(path=str(data), lang="heb", psm=PSM.SINGLE_LINE) if has_hebrew else None
        try:
            for page, band in zip(pages, bands):
                if band is None:
                    lines.append([])
                    continue
                gray = page.convert("L")
                lines.append(_read_area(english, hebrew, gray.crop((0, 0, gray.width, band.first)), 0)
                             + _read_area(english, hebrew, gray.crop((0, band.last, gray.width, gray.height)), band.last))
        finally:
            if hebrew:
                hebrew.End()
    bounds = [Bounds(b.top, b.first, b.last, b.bottom) if b else None for b in bands]
    # Only a text layer can tell 'Verse 2' from the rest: what lies outside the music is blanked here.
    return [i for i in sort_text(lines, bounds, [page.width for page in pages]) if i.kind != "music"]
