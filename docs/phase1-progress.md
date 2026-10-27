# Phase 1 progress (2026-10-27)

## Pipeline (`uv run readablemusic INPUT... -o OUT`)

1. **Pages** (`pages.py`): PDFs rendered with pypdfium2 at a DPI chosen so staff lines
   are about 24 px apart; scans rescaled to the same target, with one scale per document
   taken from the page with the most staff evidence. Pages capped below Audiveris's
   20-megapixel limit. All pages go to Audiveris as one multi-page TIFF (one "book"), so
   time signatures and part names carry over.
2. **OMR** (`audiveris.py`): Audiveris 5.11.0 batch mode. `scripts/fetch_tools.py` puts
   Audiveris and the English OCR data in `tools/` on Windows.
3. **Part merge** (`parts.py`): Audiveris joins staves across systems only when their
   OCR'd names match exactly, so a 9-staff score came out as 46 parts. Each system's
   visible staves are now aligned, in order, to one list of voices with a fuzzy name match
   ("B l" = "Bl" = "B1", "Tenorl" = "T1", unnamed staves follow order). Percussion
   staves are dropped. Clef and key are restated only where they change.
4. **Lyrics clean-up** (`lyrics.py`): Unicode normalisation (OCR ligatures like "ﬁ")
   and niqqud removal.
5. **PDF** (`engrave.py`): Verovio lays out A4 pages with 5 mm staves, svglib/reportlab
   writes a vector PDF.

## Decisions taken after research

- Audiveris reads PDFs itself, but rendering ourselves lets one route serve PDFs and
  scans and lets us choose the DPI per document.
- Engraver: Verovio, not MuseScore. Lighter on a server, and the same engine runs in
  the browser for the correction screen. Verovio keeps MusicXML note ids in its SVG,
  so a clicked syllable can be traced to its note.
- Lyrics from the PDF text layer: postponed. OCR is already 90-99% on clean pages and the
  correction screen covers the rest.

## Evaluation (`eval/`)

Answer keys come from six Bach chorales bundled with music21, rendered with Verovio as
four staves, as two shared staves (S+A, T+B), and as synthetic bad scans.

| Variant | Notes F1 | Lyrics |
|---|---|---|
| Clean, 4 staves | 98.6% | 89.9% |
| Shared staves | 98.1% | 88.8% |
| Bad scans | 90.8% | 80.2% |

Lyric averages are pulled down by one piece (bwv104.6) whose verse numbering differs
between halves; the recognised text itself is good. Run with
`uv run python eval/build_set.py 6` then `uv run python eval/run.py`.

## Known issues

- Staff labels are not printed in the PDF; merged part names can be raw OCR (`T11`).
- Page header text is sometimes OCR'd as a text direction inside the music.
- Mostly empty, noisy scanned pages are still weak (bwv10.7 bad scan: 61% notes).
- Two-note chords on one staff sometimes lose a note.
- About 50 s per page on this PC.
