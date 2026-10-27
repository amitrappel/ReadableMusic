"""Web app: upload a scan, wait, correct the lyrics in the browser, download.

Run with `uv run readablemusic-web` and open http://127.0.0.1:8000.
"""

import json
import os
import re
import shutil
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from ..engrave import to_pdf
from ..pipeline import transcribe

STATIC = Path(__file__).parent / "static"
DATA = Path(os.environ.get("READABLEMUSIC_DATA", "work/web"))
KEEP_SECONDS = 24 * 3600
MAX_UPLOAD_BYTES = 50_000_000
MAX_SCORE_BYTES = 20_000_000
SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
JOB_ID = re.compile(r"[0-9a-f]{32}")

app = FastAPI(title="ReadableMusic")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
worker = ThreadPoolExecutor(max_workers=1)  # Audiveris uses all cores; one job at a time


def job_dir(job: str) -> Path:
    if not JOB_ID.fullmatch(job) or not (DATA / job).is_dir():
        raise HTTPException(404, "No such job (results are kept for 24 hours)")
    return DATA / job


def set_status(folder: Path, state: str, **extra) -> None:
    tmp = folder / "status.tmp"
    tmp.write_text(json.dumps({"state": state, **extra}), encoding="utf-8")
    tmp.replace(folder / "status.json")


def run_job(folder: Path, inputs: list[Path]) -> None:
    set_status(folder, "running")
    try:
        results = transcribe(inputs, folder, log=lambda msg: None)
        if not results:
            raise RuntimeError("No music was recognised on these pages.")
        shutil.copy(results[0], folder / "score.musicxml")
        to_pdf(folder / "score.musicxml", folder / "score.pdf")
        set_status(folder, "done")
    except Exception as e:
        (folder / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        set_status(folder, "failed", error=str(e) or type(e).__name__)


def remove_old_jobs() -> None:
    if not DATA.is_dir():
        return
    for folder in DATA.iterdir():
        if folder.is_dir() and time.time() - folder.stat().st_mtime > KEEP_SECONDS:
            shutil.rmtree(folder, ignore_errors=True)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/jobs")
async def create_job(files: list[UploadFile]):
    remove_old_jobs()
    job = uuid.uuid4().hex
    folder = DATA / job
    (folder / "input").mkdir(parents=True)
    inputs, total = [], 0
    for k, upload in enumerate(files):
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in SUFFIXES:
            shutil.rmtree(folder)
            raise HTTPException(400, f"Unsupported file type: {upload.filename}")
        data = await upload.read()
        total += len(data)
        if total > MAX_UPLOAD_BYTES:
            shutil.rmtree(folder)
            raise HTTPException(413, "Upload too large (50 MB at most)")
        path = folder / "input" / f"page-{k:03}{suffix}"
        path.write_bytes(data)
        inputs.append(path)
    if not inputs:
        shutil.rmtree(folder)
        raise HTTPException(400, "No files uploaded")
    set_status(folder, "queued")
    worker.submit(run_job, folder, inputs)
    return RedirectResponse(f"/jobs/{job}", status_code=303)


@app.get("/jobs/{job}")
def job_page(job: str):
    job_dir(job)
    return FileResponse(STATIC / "job.html")


@app.get("/api/jobs/{job}")
def job_status(job: str):
    return json.loads((job_dir(job) / "status.json").read_text(encoding="utf-8"))


@app.get("/jobs/{job}/score.{ext}")
def download(job: str, ext: str):
    if ext not in ("musicxml", "pdf"):
        raise HTTPException(404)
    path = job_dir(job) / f"score.{ext}"
    if not path.is_file():
        raise HTTPException(404, "Not ready")
    media = "application/pdf" if ext == "pdf" else "application/vnd.recordare.musicxml+xml"
    return FileResponse(path, media_type=media, filename=f"score.{ext}")


@app.put("/api/jobs/{job}/score.musicxml")
async def save_score(job: str, request: Request):
    """Store the lyrics-corrected MusicXML from the browser and engrave a new PDF."""
    folder = job_dir(job)
    data = await request.body()
    if len(data) > MAX_SCORE_BYTES or b"<score-partwise" not in data[:2000]:
        raise HTTPException(400, "Not a MusicXML score")
    tmp = folder / "edited.musicxml"
    tmp.write_bytes(data)
    try:
        await run_in_threadpool(to_pdf, tmp, folder / "edited.pdf")
    except ValueError as e:
        raise HTTPException(400, str(e))
    tmp.replace(folder / "score.musicxml")
    (folder / "edited.pdf").replace(folder / "score.pdf")
    return {"saved": True}


def main() -> None:
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
