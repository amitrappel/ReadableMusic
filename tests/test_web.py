import io
import os
import re
import threading
from collections import defaultdict
from concurrent.futures import BrokenExecutor

import music21 as m21
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from readablemusic import audiveris, web
from readablemusic.pipeline import PoorImage


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (8, 8)).save(buffer, "png")
    return buffer.getvalue()


class Inline:
    def submit(self, fn, *args):
        fn(*args)


def fake_transcribe(inputs, out_dir, log=print, check=False):
    note = m21.note.Note("C4", quarterLength=4)
    note.lyric = "hel"
    part = m21.stream.Part([m21.stream.Measure([note])])
    dest = out_dir / "page.musicxml"
    m21.stream.Score([part]).write("musicxml", dest)
    return [dest]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "DATA", tmp_path)
    monkeypatch.setattr(web, "worker", Inline())
    monkeypatch.setattr(web, "isolated", lambda fn, *args: fn(*args))
    monkeypatch.setattr(web, "transcribe", fake_transcribe)
    monkeypatch.setattr(web, "slots", threading.BoundedSemaphore(web.MAX_WAITING))
    monkeypatch.setattr(web, "recent_jobs", defaultdict(list))
    return TestClient(web.app)


def upload(client, name="scan.png", data=None, code=""):
    response = client.post("/jobs", files=[("files", (name, data or png(), "image/png"))], data={"code": code},
                           follow_redirects=False)
    return response


def test_upload_converts_and_serves_results(client):
    response = upload(client)
    assert response.status_code == 303
    job = response.headers["location"].rsplit("/", 1)[1]
    assert client.get(f"/api/jobs/{job}").json() == {"state": "done"}
    assert client.get(f"/jobs/{job}").status_code == 200
    assert b"<lyric" in client.get(f"/jobs/{job}/score.musicxml").content
    assert client.get(f"/jobs/{job}/score.pdf").content.startswith(b"%PDF")


def test_edited_score_replaces_results(client):
    job = upload(client).headers["location"].rsplit("/", 1)[1]
    xml = client.get(f"/jobs/{job}/score.musicxml").text.replace(">hel<", ">hello<")
    assert client.put(f"/api/jobs/{job}/score.musicxml", content=xml.encode()).json() == {"saved": True}
    assert ">hello<" in client.get(f"/jobs/{job}/score.musicxml").text


def test_rejects_bad_input(client):
    assert upload(client, "notes.exe").status_code == 400
    assert client.get("/api/jobs/../../etc").status_code == 404
    assert client.get("/api/jobs/" + "0" * 32).status_code == 404
    job = upload(client).headers["location"].rsplit("/", 1)[1]
    assert client.put(f"/api/jobs/{job}/score.musicxml", content=b"<html/>").status_code == 400


def test_failed_job_reports_error(client, monkeypatch):
    monkeypatch.setattr(web, "transcribe", lambda *a, **k: [])
    job = upload(client).headers["location"].rsplit("/", 1)[1]
    status = client.get(f"/api/jobs/{job}").json()
    assert status["state"] == "failed" and "No music" in status["error"]


def test_failure_message_hides_server_paths(client, monkeypatch):
    def fail(*a, **k):
        raise audiveris.AudiverisError("Audiveris failed (exit 1), see /data/x/audiveris.log")
    monkeypatch.setattr(web, "transcribe", fail)
    job = upload(client).headers["location"].rsplit("/", 1)[1]
    status = client.get(f"/api/jobs/{job}").json()
    assert status["state"] == "failed" and "/data" not in status["error"]


def test_inputs_are_deleted_after_a_successful_job(client, tmp_path):
    job = upload(client).headers["location"].rsplit("/", 1)[1]
    assert not (tmp_path / job / "input").exists()


def test_a_poor_scan_stops_and_is_read_anyway_when_asked(client, monkeypatch, tmp_path):
    def poor(inputs, out_dir, log=print, check=False):
        if check:
            raise PoorImage(["Blurred."], 0.32)
        return fake_transcribe(inputs, out_dir)
    monkeypatch.setattr(web, "transcribe", poor)
    job = upload(client).headers["location"].rsplit("/", 1)[1]
    assert client.get(f"/api/jobs/{job}").json() == {"state": "poor", "problems": ["Blurred."], "cost": 0.32}
    assert (tmp_path / job / "input").is_dir()
    assert client.post(f"/api/jobs/{job}/anyway", content=b"{}").json() == {"queued": True}
    assert client.get(f"/api/jobs/{job}").json() == {"state": "done"}
    assert client.post(f"/api/jobs/{job}/anyway", content=b"{}").status_code == 409


def test_claude_reads_only_with_the_code_where_one_is_set(client, monkeypatch, tmp_path):
    seen = []

    def record(inputs, out_dir, log=print, check=False):
        seen.append(os.environ.get("ANTHROPIC_API_KEY"))
        return fake_transcribe(inputs, out_dir)
    monkeypatch.setattr(web, "transcribe", record)
    monkeypatch.setattr(web, "CODE", "tenor")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    assert upload(client, code="bass").status_code == 403 and list(tmp_path.iterdir()) == []
    upload(client, code="tenor")
    upload(client)
    assert seen == ["key", None]


def test_rejects_unreadable_files_and_too_many_pages(client, monkeypatch):
    assert upload(client, data=b"not an image").status_code == 400
    monkeypatch.setattr(web, "MAX_PAGES", 0)
    response = upload(client)
    assert response.status_code == 400 and "Too long" in response.text


def test_rejected_uploads_leave_nothing_behind(client, tmp_path):
    upload(client, data=b"not an image")
    upload(client, "notes.exe")
    assert list(tmp_path.iterdir()) == []


def test_big_upload_is_refused_before_parsing(client, monkeypatch):
    monkeypatch.setattr(web, "MAX_UPLOAD_BYTES", 0)
    response = client.post("/jobs", content=b"x" * 2_000_000, headers={"content-type": "multipart/form-data; boundary=b"})
    assert response.status_code == 413


def test_upload_without_a_length_is_refused(client):
    def chunks():
        yield b"x"
    response = client.post("/jobs", content=chunks(), headers={"content-type": "multipart/form-data; boundary=b"})
    assert response.status_code == 411


def test_full_queue_turns_uploads_away(client, monkeypatch, tmp_path):
    monkeypatch.setattr(web, "slots", threading.BoundedSemaphore(1))
    web.slots.acquire()
    response = upload(client)
    assert response.status_code == 503 and "busy" in response.text
    assert list(tmp_path.iterdir()) == []
    assert not web.recent_jobs["testclient"]  # waiting for a free slot does not use up the hourly allowance


def test_rate_limit_counts_the_address_the_proxy_saw(client, monkeypatch):
    monkeypatch.setattr(web, "JOBS_PER_HOUR", 1)
    def post(address):
        return client.post("/jobs", files=[("files", ("a.png", png(), "image/png"))], follow_redirects=False,
                           headers={"x-real-ip": address})
    assert post("1.1.1.1").status_code == 303
    assert post("1.1.1.1").status_code == 429
    assert post("2.2.2.2").status_code == 303


def test_slot_is_released_after_a_failed_job(client, monkeypatch):
    monkeypatch.setattr(web, "slots", threading.BoundedSemaphore(1))
    monkeypatch.setattr(web, "transcribe", lambda *a, **k: [])
    assert upload(client).status_code == 303
    assert upload(client).status_code == 303


def test_form_errors_are_escaped_pages_and_api_errors_are_json(client):
    response = upload(client, "<script>.exe")
    assert response.status_code == 400 and "<script>" not in response.text and "Back" in response.text
    assert client.get("/api/jobs/" + "0" * 32).json()["detail"].startswith("No such job")


def test_isolated_runs_elsewhere_and_outlives_a_crash():
    assert web.isolated(os.getpid) != os.getpid()
    with pytest.raises(BrokenExecutor):
        web.isolated(os._exit, 1)
    assert web.isolated(os.getpid) != os.getpid()


def test_score_is_reread_in_the_chosen_clef_key_and_time(client):
    job = upload(client).headers["location"].rsplit("/", 1)[1]
    xml = client.get(f"/jobs/{job}/score.musicxml").text
    part = re.search(r'<part id="([^"]+)"', xml).group(1)
    choice = {"score": xml, "clefs": {part: "bass"}, "fifths": -3, "time": "3/8"}
    response = client.post(f"/api/jobs/{job}/reread", json=choice)
    assert response.status_code == 200
    out = response.text
    # C4 on the first ledger line below a treble staff is E2 below a bass staff; the key flats it.
    assert re.search(r"<step>E</step>\s*<alter>-1</alter>\s*<octave>2</octave>", out)
    assert "<fifths>-3</fifths>" in out and "<beat-type>8</beat-type>" in out and "<sign>F</sign>" in out
    bad = client.post(f"/api/jobs/{job}/reread", json={**choice, "clefs": {part: "soprano"}})
    assert bad.status_code == 400 and "detail" in bad.json()


def test_voices_are_moved_onto_the_staves_chosen(client):
    from test_staves import SCORE
    job = upload(client).headers["location"].rsplit("/", 1)[1]
    response = client.post(f"/api/jobs/{job}/staves", json={"score": SCORE, "staves": 4})
    assert response.status_code == 200
    assert response.text.count("<score-part ") == 4 and "<part-name>Tenor</part-name>" in response.text
    bad = client.post(f"/api/jobs/{job}/staves", json={"score": SCORE, "staves": 1})
    assert bad.status_code == 400 and "detail" in bad.json()
