"""Engrave MusicXML to PDF with Verovio (SVG pages) and svglib/reportlab (vector PDF)."""

import html
import io
import re
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
TITLE_SCALE = 1.5  # Verovio prints all credits at one size; the title is the bold one

TEXT_FONT = "DavidLibre"  # has both Latin and Hebrew letters
FOOT_FONT = "DavidLibre-Regular"
FOOT_SIZE = 8  # points
FOOT_LEADING = 10
FOOT_BASE = 20  # baseline of the lowest line above the page edge
FOOT_MARGIN = 28

for _weight, _file in (("normal", "DavidLibre-Regular.ttf"), ("bold", "DavidLibre-Bold.ttf")):
    for _style in ("normal", "italic"):
        register_font(TEXT_FONT, str(FONTS / _file), _weight, _style, rlgFontName=_file[:-4])


def _for_reportlab(svg: str) -> str:
    """Adapt Verovio's SVG text to reportlab.

    Verovio asks for Times, which svglib always maps to the built-in Latin-only font, so
    the family is renamed. Text with Hebrew is put in display order, since reportlab draws
    all text left to right. The credits' nested text is flattened.
    """
    def flip(m: re.Match) -> str:
        return f">{get_display(m.group(1))}<"
    svg = svg.replace('font-family="Times, serif"', f'font-family="{TEXT_FONT}"')
    def credit(m: re.Match) -> str:
        bold, x, y, anchor, size, text = m.groups()
        size, weight = (float(size) * TITLE_SCALE, ' font-weight="bold"') if bold else (float(size), "")
        return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size:g}px"{weight}>{text}</text>'
    svg = CREDIT_TEXT.sub(credit, svg)
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


def to_pdf(musicxml: Path, dest: Path, staff_mm: float = 5.0) -> int:
    """Write an A4 PDF with staves staff_mm high and return its page count.

    Verovio lays out on a page enlarged by 7.2/staff_mm at its natural size; each
    page is then shrunk onto A4, which gives the requested staff height. Verovio cannot
    print footnotes from MusicXML, nor page numbers on Windows, so they are drawn here
    in a bottom margin kept free for them.
    """
    enlarge = VEROVIO_STAFF_MM / staff_mm
    xml = musicxml.read_text(encoding="utf-8")
    width, height = A4_MM[0] * POINTS_PER_MM, A4_MM[1] * POINTS_PER_MM
    footnotes = _footnotes(xml, width - 2 * FOOT_MARGIN)
    foot_points = FOOT_BASE + FOOT_LEADING * max(len(footnotes), 1)
    tk = verovio.toolkit(False)
    tk.setResourcePath(RESOURCES)
    tk.setOptions({
        "pageWidth": round(A4_MM[0] * 10 * enlarge),  # Verovio units are tenths of a millimetre
        "pageHeight": round(A4_MM[1] * 10 * enlarge),
        "pageMarginBottom": round(foot_points / POINTS_PER_MM * 10 * enlarge),
        "breaks": "auto",  # reflow instead of copying the scan's system breaks
        "header": "encoded",  # the credits only: the Windows build garbles its page-number header
        "footer": "encoded",
    })
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
