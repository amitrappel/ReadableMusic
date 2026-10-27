"""Turn the input files (PDFs and/or images) into page images scaled for OMR."""

import statistics
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from .scale import TARGET_INTERLINE, estimate_interline

PROBE_DPI = 200
MIN_DPI, MAX_DPI = 150, 800
MIN_SCALE, MAX_SCALE = 0.5, 3.0


def load_pages(inputs: list[Path]) -> list[Image.Image]:
    """Load all pages of all inputs, in order, as grayscale images with the target interline."""
    pages: list[Image.Image] = []
    for path in inputs:
        if path.suffix.lower() == ".pdf":
            pages.extend(_load_pdf(path))
        else:
            pages.extend(_load_image(path))
    return pages


def _load_pdf(path: Path) -> list[Image.Image]:
    pdf = pdfium.PdfDocument(path)
    dpi = _pdf_dpi(pdf)
    scale = dpi / 72
    return [pdf[i].render(scale=scale, grayscale=True).to_pil().convert("L") for i in range(len(pdf))]


def _pdf_dpi(pdf: pdfium.PdfDocument) -> int:
    """Choose one DPI for the whole PDF from the interline of its first few pages."""
    found = []
    for i in range(min(len(pdf), 3)):
        probe = pdf[i].render(scale=PROBE_DPI / 72, grayscale=True).to_pil()
        if (interline := estimate_interline(probe)) is not None:
            found.append(interline)
    if not found:
        return 300
    dpi = PROBE_DPI * TARGET_INTERLINE / statistics.median(found)
    return round(min(max(dpi, MIN_DPI), MAX_DPI))


def _load_image(path: Path) -> list[Image.Image]:
    pages = []
    with Image.open(path) as img:
        for frame in range(getattr(img, "n_frames", 1)):
            img.seek(frame)
            page = img.convert("L")
            interline = estimate_interline(page)
            if interline is not None:
                k = min(max(TARGET_INTERLINE / interline, MIN_SCALE), MAX_SCALE)
                page = page.resize((round(page.width * k), round(page.height * k)), Image.LANCZOS)
            pages.append(page)
    return pages


def save_tiff(pages: list[Image.Image], dest: Path) -> Path:
    """Write pages as one multi-page TIFF, which Audiveris loads as a single book."""
    pages[0].save(dest, save_all=True, append_images=pages[1:], compression="tiff_lzw")
    return dest
