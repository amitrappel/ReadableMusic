# Phase 2 progress: web MVP (2026-10-27)

Run with `uv run readablemusic-web` and open http://127.0.0.1:8000.

## What it does

1. **Upload** (`/`): a PDF or page images. Limits: 50 MB, PDF and common image types.
2. **Wait** (`/jobs/<id>`): the page polls the job status. One conversion runs at a time.
   Results are deleted after 24 hours.
3. **Correct the lyrics** in the browser:
   - Click a note or syllable: a small box opens with one field per verse.
     `Tab`/`Shift+Tab` move to the next/previous note of the same voice, `Enter` closes,
     `Esc` cancels. A trailing `-` means the word continues on the next note.
     An empty field removes the syllable; typing under a note without one adds it.
   - "Edit a line as text": the lyrics of one part, voice and verse as plain text
     (`Hel-lo world`), for fast retyping. The syllable count must match the notes
     that already have lyrics, and a live counter shows it.
4. **Save**: the edited MusicXML goes to the server, which engraves a new PDF.
   The MusicXML and PDF downloads then include the corrections.

## Decisions taken after research

- **FastAPI + plain HTML/JS, no build step.** Verovio's browser build (6.3.0, the same
  version as the Python package) loads from jsDelivr as one script.
- **Edits happen in the browser, on the MusicXML itself.** The page parses the file with
  `DOMParser`, edits `<lyric>` elements, and sends the whole file back. This replaced
  the first idea (send edit lists, apply them with music21): less code, and no lossy
  round-trip. To map clicks to notes, the page numbers the `<note>` elements of the copy
  it renders (`n0`, `n1`, ...); Verovio keeps those ids in its SVG.
- **Job runner: one worker thread inside the server**, with status in a JSON file per job.
  Audiveris uses all cores, so running jobs one at a time loses nothing. A real queue
  (Redis/RQ) waits for the deployment phase.

## Fixed along the way

- Verovio sets its font path only in the thread that imports it, so engraving failed in
  worker threads. `engrave.py` now sets the path on each toolkit.

## Testing

- `tests/test_web.py`: upload, status, downloads, saving an edit, bad input, failed jobs
  (with recognition replaced by a tiny generated score).
- Checked by hand in Edge, driven by Playwright, on a 2-page chorale: click edit, `Tab`,
  line edit, save, and the saved MusicXML and new PDF.

## Known issues

- Part names are often the placeholder "Voice" when OCR missed the staff labels.
- The edit box can cover the staff below the clicked note.
- The line editor cannot add syllables that OCR missed; add those by clicking the note.
- No protection against abuse yet (rate limits, CAPTCHA); needed before going public.
