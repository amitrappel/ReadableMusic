"""Correct OCR'd text with the text layer of PDFs exported from notation software.

Audiveris stores each recognised lyric syllable and word (part names, directions) in its
project (.omr, a zip of XML) with its box in page pixels. The PDF text inside that box
replaces the OCR'd value, and the project is then exported again (see audiveris.export).
A syllable takes its whole word, though OCR may have boxed only part of it, and a word
taken for a verse number becomes a syllable of the chord above it. Lyric syllables with
no text under them (symbols read as text) are removed; text that Audiveris did not detect
at all is not added.
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
LYRIC_BOX = re.compile(r'<lyric-item [^>]*?id="(\d+)">\s*<bounds x="(\d+)" y="(\d+)" w="(\d+)" h="(\d+)"/>')
CHORD_BOX = re.compile(r'<head-chord [^>]*?staff="(\d+)" id="(\d+)">\s*<bounds x="(\d+)" y="\d+" w="(\d+)"')
INTERLINE = re.compile(r'<interline [^>]*?main="(\d+)"')
PAD = 0.15  # share of the box height by which a character centre may fall outside the box
SPACE = 0.2  # a gap of this many font heights between letters is a word space
HYPHENS = "-‐"
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


def _inside(ch: Char, box: tuple[float, float, float, float]) -> bool:
    x, y, w, h = box
    pad = h * PAD
    return x - pad <= ch.x <= x + w + pad and y - pad <= ch.y <= y + h + pad


def _whole_words(chars: list[Char], picked: set[int], claimed: set[int]) -> set[int]:
    """Add the letters that continue the words of the picked ones, unless a syllable has
    claimed them: OCR leaves a letter out of its box when an accidental touches it.

    A word grows only into its neighbours in text order, so a space ends it even where
    the words are set closer than SPACE.
    """
    todo = list(picked)
    while todo:
        j = todo.pop()
        for i in (j - 1, j + 1):
            if i in picked or i in claimed or not 0 <= i < len(chars):
                continue
            ch, near = chars[i], chars[j]
            if (ch.c.strip() and ch.c.isprintable() and ch.c not in HYPHENS
                    and abs(ch.y - near.y) < near.size / 2
                    and max(ch.x0 - near.x1, near.x0 - ch.x1) < SPACE * max(ch.size, near.size)):
                picked.add(i)
                todo.append(i)
    return picked


def _link_syllables(xml: str, items: list[tuple[str, str, float]]) -> str:
    """Attach syllables to the chord above them; items are (id, staff, centre x in pixels).

    A chord that already has a syllable of the same lyric line keeps it.
    """
    interline = int(m.group(1)) if (m := INTERLINE.search(xml)) else 20
    chords = CHORD_BOX.findall(xml)
    contains = re.findall(r'<relation source="(\d+)" target="(\d+)">\s*<containment', xml)
    sung = set(re.findall(r'<relation source="(\d+)" target="(\d+)">\s*<chord-syllable', xml))
    contains = set(contains)
    for item, staff, x in items:
        line = {t for s, t in contains if (s, item) in contains}  # the syllables of its lyric line
        near = [(abs(int(cx) + int(cw) / 2 - x), cid) for st, cid, cx, cw in chords
                if st == staff and abs(int(cx) + int(cw) / 2 - x) <= interline
                and not any((cid, t) in sung for t in line)]
        if not near:
            continue
        chord = min(near)[1]
        end = xml.index("</relations>", xml.index(f'id="{item}"'))  # the relations of its system
        xml = (xml[:end] + f'  <relation source="{chord}" target="{item}">\n'
               f'            <chord-syllable grade="1"/>\n          </relation>\n        ' + xml[end:])
    return xml


def _fix_sheet(xml: str, page: pdfium.PdfPage, renames: dict[str, Counter]) -> tuple[str, int]:
    width = PICTURE_WIDTH.search(xml)
    if not width:
        return xml, 0
    k = page.get_width() / int(width.group(1))  # PDF points per image pixel
    chars = text_chars(page)
    lyric_boxes = [tuple(int(v) * k for v in box) for _, *box in LYRIC_BOX.findall(xml)]
    claimed = {i for i, ch in enumerate(chars) if any(_inside(ch, b) for b in lyric_boxes)}
    changed = found = 0
    role = None  # role of the sentence the following words belong to
    to_link = []  # words that OCR took for verse numbers, which become syllables

    def replace(m: re.Match) -> str:
        nonlocal changed, found, role
        if m.group("role"):
            role = m.group("role")
            return m.group(0)
        old = html.unescape(m.group(2))
        box = tuple(int(v) * k for v in m.groups()[3:7])
        picked = {i for i, ch in enumerate(chars) if _inside(ch, box) and ch.c.isprintable()}  # some PDFs hold control characters
        lyric = m.group(0).startswith("<lyric-item")
        if lyric and picked:
            picked = _whole_words(chars, picked, claimed)
            claimed.update(picked)
        text = "".join(chars[i].c for i in sorted(picked))
        if not text.strip() and lyric:
            return DROP + m.group(0)  # a symbol read as a syllable ('x' for a double sharp)
        found += 1
        text = " ".join(text.split()).strip("-‐ ")  # hyphens between syllables are separate items
        start = m.group(1)
        ids = re.search(r' staff="(\d+)".*? id="(\d+)"', m.group(0))
        if lyric and ids and 'kind="Number"' in start and any(c.isalpha() for c in text):
            start = start.replace('kind="Number"', 'kind="Syllable" syllabic="SINGLE"')
            to_link.append((ids.group(2), ids.group(1), (box[0] + box[2] / 2) / k))
        elif not text or text == old:
            return m.group(0)
        if role == "PartName" and m.group(0).startswith("<word"):
            renames[old][text] += 1
        changed += 1
        return start + html.escape(text or old) + m.group(3)

    xml = _link_syllables(TEXT_ITEM.sub(replace, xml), to_link)
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
