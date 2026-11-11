import pytest
from PIL import Image, ImageDraw

from readablemusic import pipeline
from readablemusic.pipeline import PoorImage, _keep, _kept, _problems, transcribe
from readablemusic.vision import Reading


def staves(path, interline: int) -> None:
    """A page of staves with interline pixels between their lines."""
    img = Image.new("L", (40 * interline, 60 * interline), 255)
    draw = ImageDraw.Draw(img)
    for top in range(2 * interline, 55 * interline, 8 * interline):
        for k in range(5):
            draw.line((interline, top + k * interline, 39 * interline, top + k * interline), fill=0)
    img.save(path)


def test_an_image_with_too_few_pixels_is_stopped_before_audiveris(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline.audiveris, "transcribe", lambda *a: pytest.fail("Audiveris ran"))
    staves(tmp_path / "small.png", 5)
    with pytest.raises(PoorImage, match="5 pixels apart") as stop:
        transcribe([tmp_path / "small.png"], tmp_path, check=True)
    assert stop.value.cost is None


def test_a_scan_is_poor_where_audiveris_reads_little_or_claude_little():
    partly = Reading([], 0, "", {}, legibility="partly", problems=("part names cut off at the left",))
    assert _problems(partly, "") == []
    assert _problems(partly, "4 systems on the page, 3 in the score") == [
        "Audiveris, which recognises the music, could read little of it.", "Part names cut off at the left"]
    assert _problems(Reading([], 0, "", {}), "61 notes and 200 rests") == [
        "Audiveris, which recognises the music, could read little of it."]
    assert _problems(Reading([], 0, "", {}, legibility="poor"), "") == ["Claude could not read much of the page."]
    assert _problems(None, "") == []


def test_the_first_page_reading_kept_by_a_stopped_run_goes_to_the_next_of_the_same_pages(tmp_path):
    reading = Reading(["treble"], -2, "3/4", {"title": "A"}, ("note",), "partly", ("blur",))
    page = tmp_path / "page.png"
    page.write_bytes(b"one")
    _keep(tmp_path, [page], reading)
    assert _kept(tmp_path, [page]) == reading
    assert _kept(tmp_path, [page]) is None
    _keep(tmp_path, [page], reading)
    page.write_bytes(b"another")
    assert _kept(tmp_path, [page]) is None
