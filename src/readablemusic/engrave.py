"""Engrave MusicXML to PDF with Verovio (SVG pages) and svglib/reportlab (vector PDF)."""

import io
from importlib.resources import files
from pathlib import Path

import verovio
from reportlab.graphics import renderPDF
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg

A4_MM = (210, 297)
POINTS_PER_MM = 72 / 25.4
VEROVIO_STAFF_MM = 7.2  # staff height at Verovio's default unit and 100% scale
SVGLIB_CONTENT_RATIO = 0.75
RESOURCES = str(files("verovio") / "data")  # Verovio sets its default only in the importing thread


def to_pdf(musicxml: Path, dest: Path, staff_mm: float = 5.0) -> int:
    """Write an A4 PDF with staves staff_mm high and return its page count.

    Verovio lays out on a page enlarged by 7.2/staff_mm at its natural size; each
    page is then shrunk onto A4, which gives the requested staff height.
    """
    enlarge = VEROVIO_STAFF_MM / staff_mm
    tk = verovio.toolkit(False)
    tk.setResourcePath(RESOURCES)
    tk.setOptions({
        "pageWidth": round(A4_MM[0] * 10 * enlarge),  # Verovio units are tenths of a millimetre
        "pageHeight": round(A4_MM[1] * 10 * enlarge),
        "breaks": "auto",  # reflow instead of copying the scan's system breaks
        "header": "none",  # the Windows build garbles the en-dashes of its page-number header
        "footer": "none",
    })
    if not tk.loadFile(str(musicxml)):
        raise ValueError(f"Verovio could not read {musicxml}")
    width, height = A4_MM[0] * POINTS_PER_MM, A4_MM[1] * POINTS_PER_MM
    pdf = canvas.Canvas(str(dest), pagesize=(width, height))
    pages = tk.getPageCount()
    for n in range(1, pages + 1):
        drawing = svg2rlg(io.StringIO(tk.renderToSVG(n)))
        # svglib converts px to pt on both Verovio's outer <svg> and its inner viewBox,
        # so the music fills only the top-left 75% of the drawing.
        k = width / (drawing.width * SVGLIB_CONTENT_RATIO)
        drawing.scale(k, k)
        renderPDF.draw(drawing, pdf, 0, height - drawing.height * k)
        pdf.showPage()
    pdf.save()
    return pages
