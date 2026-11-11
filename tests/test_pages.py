from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from readablemusic.pages import MAX_RENDER_PIXELS, _load_image, _render, page_count


def test_huge_declared_page_is_rendered_within_the_pixel_limit():
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(14400, 14400)  # the largest page PDF allows, 200 inches square
    image = _render(page, 800)
    assert image.width * image.height <= MAX_RENDER_PIXELS * 1.01


def test_small_page_keeps_the_requested_dpi():
    pdf = pdfium.PdfDocument.new()
    image = _render(pdf.new_page(72, 72), 300)
    assert (image.width, image.height) == (300, 300)


def test_page_count(tmp_path: Path):
    pdf = pdfium.PdfDocument.new()
    pdf.new_page(72, 72)
    pdf.new_page(72, 72)
    pdf.save(tmp_path / "a.pdf")
    Image.new("L", (8, 8)).save(tmp_path / "a.png")
    frames = [Image.new("L", (8, 8)) for _ in range(3)]
    frames[0].save(tmp_path / "a.tif", save_all=True, append_images=frames[1:])
    assert page_count(tmp_path / "a.pdf") == 2
    assert page_count(tmp_path / "a.png") == 1
    assert page_count(tmp_path / "a.tif") == 3


def test_a_photo_stored_on_its_side_is_turned_upright(tmp_path: Path):
    img = Image.new("L", (400, 300), 255)
    exif = img.getexif()
    exif[0x0112] = 6  # turn 90 degrees clockwise to view, as phones tag a portrait photo
    img.save(tmp_path / "photo.jpg", exif=exif)
    assert _load_image(tmp_path / "photo.jpg")[0].size == (300, 400)
