import music21 as m21
import pytest
from fastapi.testclient import TestClient

from readablemusic import web


class Inline:
    def submit(self, fn, *args):
        fn(*args)


def fake_transcribe(inputs, out_dir, log=print):
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
    monkeypatch.setattr(web, "transcribe", fake_transcribe)
    return TestClient(web.app)


def upload(client, name="scan.png"):
    response = client.post("/jobs", files=[("files", (name, b"fake", "image/png"))], follow_redirects=False)
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
