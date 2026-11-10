"""Engrave MusicXML to PDF with Verovio (SVG pages) and svglib/reportlab (vector PDF)."""

import html
import io
import re
import xml.etree.ElementTree as ET
from importlib.resources import files
from pathlib import Path

import verovio
from bidi import get_display
from reportlab.graphics import renderPDF
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from svglib.fonts import register_font
from svglib.svglib import svg2rlg

A4_MM = (210, 297)
POINTS_PER_MM = 72 / 25.4
VEROVIO_STAFF_MM = 7.2  # staff height at Verovio's default unit and 100% scale
SVGLIB_CONTENT_RATIO = 0.75
RESOURCES = str(files("verovio") / "data")  # Verovio sets its default only in the importing thread
FONTS = files("readablemusic") / "fonts"
HEBREW_TEXT = re.compile(r">([^<>]*[֐-׿][^<>]*)<")
# Verovio nests the credits' position and size in tspans, which svglib ignores.
CREDIT_TEXT = re.compile(
    r'<text font-size="0px">\s*<tspan [^>]*class="rend"( font-weight="bold")? x="([\d.]+)" y="([\d.]+)" '
    r'text-anchor="(\w+)">\s*<tspan [^>]*class="text">\s*<tspan font-size="([\d.]+)px">([^<]*)</tspan>'
    r'\s*</tspan>\s*</tspan>\s*</text>')
# Chord symbols nest each piece in a tspan, accidentals in Verovio's music font.
CHORD_TEXT = re.compile(r'(<g [^>]*class="harm"[^>]*>\s*<text [^>]*?)font-size="0px">(.*?)</text>', re.S)
CHORD_PIECE = re.compile(r'<tspan (font-family="Leipzig" )?font-size="([\d.]+)px">([^<]*)</tspan>')
CHORD_ACCIDENTALS = {"": "b", "": "", "": "#", "𝄫": "bb", "𝄪": "x"}  # as in chord charts
TITLE_SCALE = 1.5  # Verovio prints all credits at one size; the title is the bold one
STAFF_GAP = 16  # Verovio units (half a staff space): least space between staves of a system
SYSTEM_GAP = 16  # least space between systems
LYRIC_WORD_SPACE = 2.0
MARGIN_MM = 20  # left and right
MARGIN_TOP_MM = MARGIN_BOTTOM_MM = 15
LINE_BARS = 4  # measures a line, or one fewer where they would be crowded
CROWDED = 0.8  # share of a line that its measures may take at Verovio's natural spacing
STAFF_LINE = re.compile(r'<path d="M(\d+) (\d+) L(\d+) \2"')  # horizontal; a measure draws its staff lines first

TEXT_FONT = "DavidLibre"  # has both Latin and Hebrew letters
FOOT_FONT = "DavidLibre-Regular"
FOOT_SIZE = 8  # points
FOOT_LEADING = 10
FOOT_BASE = 20  # baseline of the lowest line above the page edge
FOOT_GAP_MM = 4  # between the music and the footnotes
FOOT_MARGIN = MARGIN_MM * POINTS_PER_MM

for _weight, _file in (("normal", "DavidLibre-Regular.ttf"), ("bold", "DavidLibre-Bold.ttf")):
    for _style in ("normal", "italic"):
        register_font(TEXT_FONT, str(FONTS / _file), _weight, _style, rlgFontName=_file[:-4])


def _for_reportlab(svg: str) -> str:
    """Adapt Verovio's SVG text to reportlab.

    Verovio asks for Times, which svglib always maps to the built-in Latin-only font, so
    the family is renamed. Text with Hebrew is put in display order, since reportlab draws
    all text left to right. The credits' and chord symbols' nested text is flattened, with
    the chords' accidentals as letters: the text font has no flat sign.
    """
    def flip(m: re.Match) -> str:
        return f">{get_display(m.group(1))}<"
    svg = svg.replace('font-family="Times, serif"', f'font-family="{TEXT_FONT}"')
    def credit(m: re.Match) -> str:
        bold, x, y, anchor, size, text = m.groups()
        size, weight = (float(size) * TITLE_SCALE, ' font-weight="bold"') if bold else (float(size), "")
        return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size:g}px"{weight}>{text}</text>'
    svg = CREDIT_TEXT.sub(credit, svg)
    def chord(m: re.Match) -> str:
        pieces = CHORD_PIECE.findall(m.group(2))
        if not pieces:
            return m.group(0)
        size = next((size for music, size, _ in pieces if not music), pieces[0][1])
        text = "".join("".join(CHORD_ACCIDENTALS.get(c, c) for c in piece) for _, _, piece in pieces)
        return f'{m.group(1)}font-size="{size}px">{text}</text>'
    svg = CHORD_TEXT.sub(chord, svg)
    return HEBREW_TEXT.sub(flip, svg)


def _footnotes(xml: str, width: float) -> list[str]:
    """The footnotes and copyright lines of a score, wrapped to width points."""
    found = re.findall(r'<miscellaneous-field name="footnote">(.*?)</miscellaneous-field>', xml, re.S)
    found += re.findall(r"<rights>(.*?)</rights>", xml, re.S)
    return [line for text in found for line in simpleSplit(html.unescape(text), FOOT_FONT, FOOT_SIZE, width)]


def _draw_foot(pdf: canvas.Canvas, n: int, footnotes: list[str], width: float) -> None:
    """Footnotes at the foot of the first page, a page number on the others."""
    pdf.setFont(FOOT_FONT, FOOT_SIZE)
    if n > 1:
        pdf.drawCentredString(width / 2, FOOT_BASE, str(n))
    else:
        for k, line in enumerate(reversed(footnotes)):
            pdf.drawString(FOOT_MARGIN, FOOT_BASE + k * FOOT_LEADING, get_display(line))


def _units(mm: float, staff_mm: float) -> int:
    """Verovio units (tenths of a millimetre) on the enlarged page for mm on A4."""
    return round(mm * 10 * VEROVIO_STAFF_MM / staff_mm)


def _toolkit(staff_mm: float, bottom_mm: float = MARGIN_BOTTOM_MM, **options) -> verovio.toolkit:
    """Verovio laying out A4 pages with staves staff_mm high (the editor, editor.js, uses the same page).

    Verovio lays out on a page enlarged by 7.2/staff_mm at its natural size; each page is
    then shrunk onto A4, which gives the requested staff height.
    """
    tk = verovio.toolkit(False)
    tk.setResourcePath(RESOURCES)
    tk.setOptions({
        "pageWidth": _units(A4_MM[0], staff_mm),
        "pageHeight": _units(A4_MM[1], staff_mm),
        "pageMarginLeft": _units(MARGIN_MM, staff_mm),
        "pageMarginRight": _units(MARGIN_MM, staff_mm),
        "pageMarginTop": _units(MARGIN_TOP_MM, staff_mm),
        "pageMarginBottom": _units(bottom_mm, staff_mm),
        "breaks": "line",  # the lines of line_breaks; pages fill up
        "minLastJustification": 0,  # a last line of 3 measures as wide as the lines of 4
        "header": "encoded",  # the credits only: the Windows build garbles its page-number header
        "footer": "encoded",
        # Roomier than Verovio's defaults (12, 12, 4, 1.2), which crowd lyrics against the next staff.
        "spacingStaff": STAFF_GAP,
        "spacingBracketGroup": STAFF_GAP,
        "spacingBraceGroup": STAFF_GAP,
        "spacingSystem": SYSTEM_GAP,
        "lyricWordSpace": LYRIC_WORD_SPACE,
        **options,
    })
    return tk


def _measure_lines(tk: verovio.toolkit) -> list[tuple[int, int]]:
    """Where each measure's staff lines start and end, in SVG units (Verovio's tenfold)."""
    out = []
    for page in range(1, tk.getPageCount() + 1):
        for chunk in tk.renderToSVG(page).split('class="measure')[1:]:
            line = STAFF_LINE.search(chunk)
            out.append((int(line.group(1)), int(line.group(3))) if line else (0, 0))
    return out


def lines(first: list[int], inner: list[int], room: int) -> list[int]:
    """How many measures go on each line: LINE_BARS, or one fewer where they would take
    more than CROWDED of the room, and shorter lines only where nothing else fits or at
    the end of a short score. first is a measure's width starting a line, with the part
    names, clef and key, and inner its width within a line."""
    n = len(first)
    best: list[tuple[float, list[int]]] = [(0, [])] * (n + 1)
    for i in range(n - 1, -1, -1):
        options = []
        for size in range(min(LINE_BARS, n - i), 0, -1):
            need = first[i] + sum(inner[i + 1:i + size])
            cost = 1 if size >= LINE_BARS - 1 else 3 + LINE_BARS - size
            cost += 2 if size == LINE_BARS and need > CROWDED * room else 0
            cost += 10 if need > room and size > 1 else 0
            options.append((cost + best[i + size][0], [size] + best[i + size][1]))
        best[i] = min(options, key=lambda o: o[0])  # the first of equals: longer lines first
    return best[0][1]


def line_breaks(text: str, staff_mm: float = 5.0) -> str:
    """Start a line every LINE_BARS measures, or one fewer where they would be crowded
    (lines()), as print new-system marks in every part: Verovio's own layout puts as many
    measures on a line as fit, up to 14 of אתה הצבת. Other system and page breaks go."""
    start = text.index("<score-partwise")
    root = ET.fromstring(text[start:])
    parts = root.findall("part")
    if not parts:
        return text
    for part in parts:
        for m in part.findall("measure"):
            for mark in m.findall("print"):
                mark.attrib.pop("new-system", None)
                mark.attrib.pop("new-page", None)
                if not mark.attrib and not len(mark):
                    m.remove(mark)
    plain = text[:start] + ET.tostring(root, encoding="unicode")
    tk = _toolkit(staff_mm, breaks="none", header="none", footer="none")
    if not tk.loadData(plain):
        return plain
    inner = [end - begin for begin, end in _measure_lines(tk)]
    measures = [part.findall("measure") for part in parts]
    for ms in measures:
        for m in ms[1:]:
            m.insert(0, ET.Element("print", {"new-system": "yes"}))
    # A line for each measure, left at its natural width, gives its width starting a line.
    tk = _toolkit(staff_mm, breaks="encoded", noJustification=True, header="none", footer="none")
    tk.loadData(text[:start] + ET.tostring(root, encoding="unicode"))
    left = 10 * _units(MARGIN_MM, staff_mm)
    first = [end - left for _, end in _measure_lines(tk)]
    if not len(first) == len(inner) == len(measures[0]):
        return plain
    starts, k = set(), 0
    for size in lines(first, inner, 10 * _units(A4_MM[0] - 2 * MARGIN_MM, staff_mm)):
        starts.add(k)
        k += size
    for ms in measures:
        for k, m in enumerate(ms[1:], 1):
            if k not in starts:
                m.remove(m[0])
    return text[:start] + ET.tostring(root, encoding="unicode")


def to_pdf(musicxml: Path, dest: Path, staff_mm: float = 5.0) -> int:
    """Write an A4 PDF with staves staff_mm high and return its page count.

    Its lines are those of line_breaks. Verovio cannot print footnotes from MusicXML, nor
    page numbers on Windows, so they are drawn here in a bottom margin kept free for them.
    """
    xml = line_breaks(musicxml.read_text(encoding="utf-8"), staff_mm)
    width, height = A4_MM[0] * POINTS_PER_MM, A4_MM[1] * POINTS_PER_MM
    footnotes = _footnotes(xml, width - 2 * FOOT_MARGIN)
    foot_points = FOOT_BASE + FOOT_LEADING * max(len(footnotes), 1)
    tk = _toolkit(staff_mm, max(MARGIN_BOTTOM_MM, foot_points / POINTS_PER_MM + FOOT_GAP_MM))
    # loadData, not loadFile: Verovio cannot open non-ASCII paths on Windows
    if not tk.loadData(xml):
        raise ValueError(f"Verovio could not read {musicxml}")
    pdf = canvas.Canvas(str(dest), pagesize=(width, height))
    pages = tk.getPageCount()
    for n in range(1, pages + 1):
        drawing = svg2rlg(io.StringIO(_for_reportlab(tk.renderToSVG(n))))
        # svglib converts px to pt on both Verovio's outer <svg> and its inner viewBox,
        # so the music fills only the top-left 75% of the drawing.
        k = width / (drawing.width * SVGLIB_CONTENT_RATIO)
        drawing.scale(k, k)
        renderPDF.draw(drawing, pdf, 0, height - drawing.height * k)
        _draw_foot(pdf, n, footnotes, width)
        pdf.showPage()
    pdf.save()
    return pages
