"""Correct OCR'd text with the text layer of PDFs exported from notation software.

Audiveris stores each recognised lyric syllable and word (part names, directions) in its
project (.omr, a zip of XML) with its box in page pixels. The PDF text inside that box
replaces the OCR'd value, and the project is then exported again (see audiveris.export).
Lyric syllables with no text under them (symbols read as text) are removed; text that
Audiveris did not detect at all is not added.
"""

import ctypes
import html
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import NamedTuple

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

TEXT_ITEM = re.compile(
    r'(<(?:lyric-item|word) [^>]*?value=")([^"]*)("[^>]*>\s*<bounds x="(\d+)" y="(\d+)" w="(\d+)" h="(\d+)"/>)'
    r'|<sentence [^>]*?role="(?P<role>\w+)"')
PICTURE_WIDTH = re.compile(r'<picture width="(\d+)"')
PAD = 0.15  # share of the box height by which a character centre may fall outside the box
MUSIC_GLYPHS = set("œ˙Œ∑‰")  # Finale-style music fonts map noteheads and rests to these
DROP = "\x00drop"  # marks a lyric item to remove


INVISIBLE = 3  # text render mode of the OCR layer that scanners put under a scanned image


class Char(NamedTuple):
    x0: float
    x1: float
    y: float  # centre, downwards from the top of the page
    size: float  # loose box height; the font size some PDFs report is in other units
    c: str

    @property
    def x(self) -> float:
        return (self.x0 + self.x1) / 2


def has_text(pdf_path: Path) -> bool:
    """Whether the PDF has visible text; a scanner's invisible OCR layer does not count."""
    pdf = pdfium.PdfDocument(pdf_path)
    return any(pdfium_c.FPDFTextObj_GetTextRenderMode(obj.raw) != INVISIBLE
               for n in range(len(pdf)) for obj in pdf[n].get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_TEXT]))


def fix_text(omr: Path, pdf_path: Path) -> int:
    """Rewrite the lyric syllables and words in omr from the PDF's text; return how many changed.

    Sheet n of the project must be page n of the PDF.
    """
    pdf = pdfium.PdfDocument(pdf_path)
    changed = 0
    renames: dict[str, Counter] = defaultdict(Counter)  # OCR'd part-name word -> PDF text
    with zipfile.ZipFile(omr) as src:
        entries = [(info, src.read(info)) for info in src.infolist()]
    for e, (info, data) in enumerate(entries):
        m = re.fullmatch(r"sheet#(\d+)/sheet#\1\.xml", info.filename)
        if m and int(m.group(1)) <= len(pdf):
            xml, n = _fix_sheet(data.decode("utf-8"), pdf[int(m.group(1)) - 1], renames)
            entries[e], changed = (info, xml.encode("utf-8")), changed + n
    tmp = omr.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for info, data in entries:
            if info.filename == "book.xml":
                data = _rename_parts(data.decode("utf-8"), renames).encode("utf-8")
            dst.writestr(info, data)
    shutil.move(tmp, omr)
    return changed


def _rename_parts(book: str, renames: dict[str, Counter]) -> str:
    """Audiveris exports the part names kept in book.xml, not the words on the sheets."""
    def rename(m: re.Match) -> str:
        words = html.unescape(m.group(2)).split(" ")
        words = [renames[w].most_common(1)[0][0] if w in renames else w for w in words]
        return m.group(1) + html.escape(" ".join(words)) + '"'
    return re.sub(r'(<(?:logical-part|part) [^>]*?name=")([^"]*)"', rename, book)


def _fix_sheet(xml: str, page: pdfium.PdfPage, renames: dict[str, Counter]) -> tuple[str, int]:
    width = PICTURE_WIDTH.search(xml)
    if not width:
        return xml, 0
    k = page.get_width() / int(width.group(1))  # PDF points per image pixel
    chars = text_chars(page)
    changed = found = 0
    role = None  # role of the sentence the following words belong to

    def replace(m: re.Match) -> str:
        nonlocal changed, found, role
        if m.group("role"):
            role = m.group("role")
            return m.group(0)
        old = html.unescape(m.group(2))
        x, y, w, h = (int(v) * k for v in m.groups()[3:7])
        pad = h * PAD
        text = "".join(ch.c for ch in chars  # some PDFs hold control characters
                       if x - pad <= ch.x <= x + w + pad and y - pad <= ch.y <= y + h + pad and ch.c.isprintable())
        if not text.strip() and m.group(0).startswith("<lyric-item"):
            return DROP + m.group(0)  # a symbol read as a syllable ('x' for a double sharp)
        found += 1
        text = " ".join(text.split()).strip("-‐ ")  # hyphens between syllables are separate items
        if not text or text == old:
            return m.group(0)
        if role == "PartName" and m.group(0).startswith("<word"):
            renames[old][text] += 1
        changed += 1
        return m.group(1) + html.escape(text) + m.group(3)

    xml = TEXT_ITEM.sub(replace, xml)
    dropped = xml.count(DROP)
    # Drop the text-less syllables only where the page's lyrics are text: in a PDF mixing
    # text and scanned pages, a scanned page's syllables have no text under them either.
    xml = re.sub(rf"\s*{DROP}<lyric-item .*?</lyric-item>", "", xml, flags=re.S) if found > dropped \
        else xml.replace(DROP, "")
    return xml, changed + (dropped if found > dropped else 0)


def text_chars(page: pdfium.PdfPage) -> list[Char]:
    """Return the page's characters in text order, without music-font symbols.

    Some notation programs draw notes and accidentals as text in a music font; any font
    that holds a notehead character, or a private-use one as SMuFL fonts do, is taken to
    be one.
    """
    textpage, height = page.get_textpage(), page.get_height()
    chars = []
    for i in range(textpage.count_chars()):
        name = ctypes.create_string_buffer(128)
        pdfium_c.FPDFText_GetFontInfo(textpage.raw, i, name, len(name), None)
        _, bottom, _, top = textpage.get_charbox(i)
        # The loose box spans the advance width and the font's height, the same for all letters.
        left, low, right, high = textpage.get_charbox(i, loose=True)
        chars.append((name.value, Char(left, right, height - (bottom + top) / 2, high - low,
                                       textpage.get_text_range(i, 1))))
    music = {font for font, ch in chars if ch.c in MUSIC_GLYPHS or "" <= ch.c <= ""}
    return [ch for font, ch in chars if font not in music]
