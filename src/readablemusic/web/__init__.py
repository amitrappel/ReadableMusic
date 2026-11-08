"""Web app: upload a scan, wait, correct the lyrics in the browser, download.

Run with `uv run readablemusic-web` and open http://127.0.0.1:8000.
"""

import asyncio
import html
import json
import multiprocessing
import os
import re
import shutil
import threading
import time
import traceback
import uuid
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from xml.etree.ElementTree import ParseError

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from ..engrave import to_pdf
from ..pages import page_count
from ..pipeline import transcribe
from ..reread import CLEFS, reread

STATIC = Path(__file__).parent / "static"
DATA = Path(os.environ.get("READABLEMUSIC_DATA", "work/web"))
KEEP_SECONDS = 24 * 3600
MAX_UPLOAD_BYTES = 50_000_000
MAX_SCORE_BYTES = 20_000_000
MAX_PAGES = 30
MAX_WAITING = 5  # jobs queued or running; further uploads are turned away
JOBS_PER_HOUR = 10  # from one address
SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
JOB_ID = re.compile(r"[0-9a-f]{32}")

app = FastAPI(title="ReadableMusic")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
worker = ThreadPoolExecutor(max_workers=1)  # Audiveris uses all cores; one job at a time
slots = threading.BoundedSemaphore(MAX_WAITING)
recent_jobs: dict[str, list[float]] = defaultdict(list)
engraving = asyncio.Semaphore(1)  # a large score takes much memory and CPU


def error_response(request: Request, status: int, detail: str):
    if request.method == "POST" and not request.url.path.startswith("/api/"):
        # the upload is a plain form post, so the browser shows this as a page
        page = f'<link rel="stylesheet" href="/static/style.css"><main class="narrow"><h1>ReadableMusic</h1>' \
               f'<p>{html.escape(detail)}</p><p><a href="/">Back</a></p></main>'
        return HTMLResponse(page, status)
    return JSONResponse({"detail": detail}, status)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return error_response(request, exc.status_code, str(exc.detail))


@app.middleware("http")
async def limit_body(request: Request, call_next):
    """Turn big uploads away before parsing them, which writes the whole body to temporary files."""
    if request.method in ("POST", "PUT"):
        length = request.headers.get("content-length", "")
        if not length.isdigit():
            return error_response(request, 411, "The upload must state its length")
        if int(length) > MAX_UPLOAD_BYTES + 1_000_000:  # room for the multipart headers
            return error_response(request, 413, "Upload too large (50 MB at most)")
    return await call_next(request)


def job_dir(job: str) -> Path:
    if not JOB_ID.fullmatch(job) or not (DATA / job).is_dir():
        raise HTTPException(404, "No such job (results are kept for 24 hours)")
    return DATA / job


def set_status(folder: Path, state: str, **extra) -> None:
    tmp = folder / "status.tmp"
    tmp.write_text(json.dumps({"state": state, **extra}), encoding="utf-8")
    tmp.replace(folder / "status.json")


def isolated(fn, *args):
    """Run fn in a new process: running out of memory then costs one job and not the whole
    server, and the server holds on to none of the job's memory afterwards."""
    with ProcessPoolExecutor(1, mp_context=multiprocessing.get_context("spawn")) as pool:
        return pool.submit(fn, *args).result()


def convert(folder: Path, inputs: list[Path]) -> None:
    results = transcribe(inputs, folder, log=lambda msg: None)
    if not results:
        raise RuntimeError("No music was recognised on these pages.")
    shutil.copy(results[0], folder / "score.musicxml")
    to_pdf(folder / "score.musicxml", folder / "score.pdf")


def run_job(folder: Path, inputs: list[Path]) -> None:
    set_status(folder, "running")
    start = time.time()
    try:
        isolated(convert, folder, inputs)
        set_status(folder, "done")
        shutil.rmtree(folder / "input", ignore_errors=True)  # the corrections only need the score
        shutil.rmtree(folder / "work", ignore_errors=True)
        print(f"Job {folder.name} done in {time.time() - start:.0f} s", flush=True)
    except Exception as e:
        traceback.print_exc()
        (folder / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        # Other exceptions' messages can hold server paths.
        error = str(e) if type(e) is RuntimeError else "Recognition failed. A sharper scan or fewer pages may help."
        set_status(folder, "failed", error=error)
    finally:
        slots.release()


def remove_old_jobs() -> None:
    if not DATA.is_dir():
        return
    for folder in DATA.iterdir():
        if folder.is_dir() and time.time() - folder.stat().st_mtime > KEEP_SECONDS:
            shutil.rmtree(folder, ignore_errors=True)


def remove_old_jobs_forever() -> None:
    while True:
        remove_old_jobs()
        time.sleep(3600)


def client_address(request: Request) -> str:
    # Railway's edge overwrites this header with the address it saw, so clients cannot forge it.
    return request.headers.get("x-real-ip") or request.client.host


def too_many_jobs(address: str) -> bool:
    hour_ago = time.time() - 3600
    recent_jobs[address] = [t for t in recent_jobs[address] if t > hour_ago]
    return len(recent_jobs[address]) >= JOBS_PER_HOUR


async def save_uploads(files: list[UploadFile], folder: Path) -> list[Path]:
    inputs, total = [], 0
    for k, upload in enumerate(files):
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in SUFFIXES:
            raise HTTPException(400, f"Unsupported file type: {upload.filename}")
        data = await upload.read()
        total += len(data)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Upload too large (50 MB at most)")
        path = folder / f"page-{k:03}{suffix}"
        path.write_bytes(data)
        inputs.append(path)
    if not inputs:
        raise HTTPException(400, "No files uploaded")
    try:
        pages = sum([await run_in_threadpool(page_count, path) for path in inputs])
    except Exception:  # the PDF and image libraries raise many kinds
        raise HTTPException(400, "Could not read these files. Are they unprotected PDFs or images?")
    if pages > MAX_PAGES:
        raise HTTPException(400, f"Too long: {pages} pages ({MAX_PAGES} at most)")
    return inputs


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/jobs")
async def create_job(files: list[UploadFile], request: Request):
    address = client_address(request)
    if too_many_jobs(address):
        raise HTTPException(429, f"At most {JOBS_PER_HOUR} conversions an hour; please try again later.")
    job = uuid.uuid4().hex
    folder = DATA / job
    (folder / "input").mkdir(parents=True)
    try:
        inputs = await save_uploads(files, folder / "input")
    except HTTPException:
        shutil.rmtree(folder)
        raise
    if not slots.acquire(blocking=False):
        shutil.rmtree(folder)
        raise HTTPException(503, "The server is busy; please try again in a few minutes.")
    recent_jobs[address].append(time.time())
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
        async with engraving:
            await run_in_threadpool(to_pdf, tmp, folder / "edited.pdf")
    except ValueError as e:
        raise HTTPException(400, str(e))
    tmp.replace(folder / "score.musicxml")
    (folder / "edited.pdf").replace(folder / "score.pdf")
    return {"saved": True}


@app.post("/api/jobs/{job}/reread")
async def reread_score(job: str, request: Request):
    """Return the browser's score read again under the clefs, key and time signature chosen:
    {"score": MusicXML, "clefs": {part id: clef name}, "fifths": int or null, "time": "3/8" or null}."""
    job_dir(job)
    try:
        choice = await request.json()
        score, clefs = choice["score"], choice.get("clefs") or {}
        fifths, time_signature = choice.get("fifths"), choice.get("time") or None
        if (not isinstance(score, str) or len(score) > MAX_SCORE_BYTES or not isinstance(clefs, dict)
                or any(c not in CLEFS for c in clefs.values()) or not isinstance(fifths, (int, type(None)))
                or not isinstance(time_signature, (str, type(None)))):
            raise ValueError("Bad choice")
        xml = await run_in_threadpool(reread, score, clefs, fifths, time_signature)
    except (ValueError, KeyError, TypeError, ParseError) as e:
        raise HTTPException(400, f"Could not read the score again: {e}")
    return Response(xml, media_type="application/vnd.recordare.musicxml+xml")


def main() -> None:
    import uvicorn
    threading.Thread(target=remove_old_jobs_forever, daemon=True).start()
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
