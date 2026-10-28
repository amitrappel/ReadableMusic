"""Correct OCR'd lyrics with the text layer of PDFs exported from notation software.

Audiveris stores each recognised syllable in its project (.omr, a zip of XML) with its
box in page pixels. The PDF text inside that box replaces the OCR'd value, and the
project is then exported again (see audiveris.export). Lyrics that Audiveris did not
detect at all are not added.
"""

import ctypes
import html
import re
import shutil
import zipfile
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

LYRIC_ITEM = re.compile(
    r'(<lyric-item [^>]*?value=")([^"]*)("[^>]*>\s*<bounds x="(\d+)" y="(\d+)" w="(\d+)" h="(\d+)"/>)')
PICTURE_WIDTH = re.compile(r'<picture width="(\d+)"')
PAD = 0.15  # share of the box height by which a character centre may fall outside the box
MUSIC_GLYPHS = set("œ˙Œ∑‰")  # Finale-style music fonts map noteheads and rests to these


def has_text(pdf_path: Path) -> bool:
    pdf = pdfium.PdfDocument(pdf_path)
    return any(pdf[n].get_textpage().count_chars() > 0 for n in range(len(pdf)))


def fix_lyrics(omr: Path, pdf_path: Path) -> int:
    """Rewrite the lyric syllables in omr from the PDF's text; return how many changed.

    Sheet n of the project must be page n of the PDF.
    """
    pdf = pdfium.PdfDocument(pdf_path)
    changed = 0
    tmp = omr.with_suffix(".tmp")
    with zipfile.ZipFile(omr) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info)
            m = re.fullmatch(r"sheet#(\d+)/sheet#\1\.xml", info.filename)
            if m and int(m.group(1)) <= len(pdf):
                xml, n = _fix_sheet(data.decode("utf-8"), pdf[int(m.group(1)) - 1])
                data, changed = xml.encode("utf-8"), changed + n
            dst.writestr(info, data)
    shutil.move(tmp, omr)
    return changed


def _fix_sheet(xml: str, page: pdfium.PdfPage) -> tuple[str, int]:
    width = PICTURE_WIDTH.search(xml)
    if not width:
        return xml, 0
    k = page.get_width() / int(width.group(1))  # PDF points per image pixel
    height = page.get_height()
    chars = _text_chars(page.get_textpage(), height)
    changed = 0

    def replace(m: re.Match) -> str:
        nonlocal changed
        old = html.unescape(m.group(2))
        x, y, w, h = (int(v) * k for v in m.groups()[3:])
        pad = h * PAD
        text = "".join(c for cx, cy, c in chars  # some PDFs hold control characters
                       if x - pad <= cx <= x + w + pad and y - pad <= cy <= y + h + pad and c.isprintable())
        text = " ".join(text.split()).strip("-‐ ")  # hyphens between syllables are separate items
        if not text or text == old:
            return m.group(0)
        changed += 1
        return m.group(1) + html.escape(text) + m.group(3)

    return LYRIC_ITEM.sub(replace, xml), changed


def _text_chars(textpage: pdfium.PdfTextPage, height: float) -> list[tuple[float, float, str]]:
    """Return (x, y, char) for each character, y downwards, without music-font symbols.

    Some notation programs draw notes and accidentals as text in a music font; any font
    that holds a notehead character is taken to be one.
    """
    chars = []
    for i in range(textpage.count_chars()):
        name = ctypes.create_string_buffer(128)
        pdfium_c.FPDFText_GetFontInfo(textpage.raw, i, name, len(name), None)
        left, bottom, right, top = textpage.get_charbox(i)
        chars.append((name.value, (left + right) / 2, height - (bottom + top) / 2, textpage.get_text_range(i, 1)))
    music = {font for font, _, _, c in chars if c in MUSIC_GLYPHS}
    return [(x, y, c) for font, x, y, c in chars if font not in music]
