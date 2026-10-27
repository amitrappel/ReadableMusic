"""Turn the input files (PDFs and/or images) into page images scaled for OMR."""

import statistics
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from .scale import TARGET_INTERLINE, estimate_interline, staff_evidence

PROBE_DPI = 200
MIN_DPI, MAX_DPI = 150, 800
MIN_SCALE, MAX_SCALE = 0.5, 3.0
MAX_PIXELS = 19_000_000  # Audiveris rejects pages above 20 megapixels


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


def load_pages(inputs: list[Path]) -> list[Image.Image]:
    """Load all pages of all inputs, in order, as grayscale images with the target interline."""
    pages: list[Image.Image] = []
    images: list[Image.Image] = []
    for path in inputs:
        if path.suffix.lower() == ".pdf":
            pages.extend(_load_pdf(path))
        else:
            loaded = _load_image(path)
            images.extend(loaded)
            pages.extend(loaded)
    if images:
        # One scale for all scanned pages, from the page with the most staff evidence:
        # a mostly empty page gives an unreliable estimate.
        interline, support = max(map(staff_evidence, images), key=lambda e: e[1])
        k = min(max(TARGET_INTERLINE / interline, MIN_SCALE), MAX_SCALE) if support else 1.0
        scaled = {id(img): _resize(img, k) for img in images}
        pages = [scaled.get(id(p), p) for p in pages]
    return [_resize(p, min(1.0, (MAX_PIXELS / (p.width * p.height)) ** 0.5)) for p in pages]


def _resize(img: Image.Image, k: float) -> Image.Image:
    if abs(k - 1) < 0.01:
        return img
    return img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)


def _load_image(path: Path) -> list[Image.Image]:
    pages = []
    with Image.open(path) as img:
        for frame in range(getattr(img, "n_frames", 1)):
            img.seek(frame)
            pages.append(img.convert("L"))
    return pages


def save_tiff(pages: list[Image.Image], dest: Path) -> Path:
    """Write pages as one multi-page TIFF, which Audiveris loads as a single book."""
    pages[0].save(dest, save_all=True, append_images=pages[1:], compression="tiff_lzw")
    return dest
