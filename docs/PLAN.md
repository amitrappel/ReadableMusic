# Plan

## Scope

- Input: **a cappella** sheets, both clean PDFs exported from notation software
  and scanned or photographed pages (image or PDF, multi-page).
  Voices may each have their own staff, or share a staff (e.g. S+A on one staff,
  stems up/down). Printed music only; handwriting is out of scope.
  Percussion staves and chord symbols are ignored.
- Output: MusicXML and an engraved PDF. Lyrics in English (Latin script) first,
  Hebrew script later, **without niqqud** (vowel points are stripped).
- Users fix recognition errors **in the browser**, without installing anything.
  Version 1 focuses on lyrics correction; note correction is a later phase.
- Free for users, built only on free/open-source software. The code is public
  under AGPL-3.0 (required by Audiveris).

## Status

- Phase 0 is done; see [phase0-findings.md](phase0-findings.md).
- Phase 1 (CLI pipeline) is working; see [phase1-progress.md](phase1-progress.md).
- Phase 2 (web MVP) is working locally; see [phase2-progress.md](phase2-progress.md).

## Working rule

Each task starts with a short research step that questions the initial choice
below. The choices here are starting hypotheses, not decisions.

## Pipeline (initial hypotheses)

```
Upload -> pages -> image cleanup -> OMR -> MusicXML (notes)
                                     |
                                     +-> lyric text positions -> OCR (rough)
                                                                  |
                         browser correction of lyrics  <----------+
                                     |
                         merge lyrics into MusicXML -> engrave PDF
```

1. **Pages**: render PDF pages to images (pypdfium2).
2. **Image cleanup** (OpenCV): upscale, deskew, dewarp, even out lighting,
   adaptive binarisation, despeckle, crop.
3. **OMR**: Audiveris (batch mode). Fallback candidate: homr.
4. **Lyrics, quick and dirty**: take the lyric lines and their positions,
   OCR them roughly (Tesseract heb+eng, or Audiveris's own OCR), strip niqqud,
   attach syllables to the nearest notes. Accuracy is not the goal here;
   the correction screen is.
5. **Correction screen** (browser): show the rendered score with each lyric
   syllable as an editable box under its note; per-line text field for fast
   retyping of a whole line, which is then re-split onto the notes; RTL-aware
   input for Hebrew; per-verse and per-voice selection.
6. **Engraving**: MuseScore CLI or Verovio, with a bundled Hebrew font.

## Architecture (initial hypotheses)

- Python package `readablemusic` (uv), usable as a CLI before any web code.
- FastAPI backend, background job queue, files auto-deleted after 24 h.
- Lightweight frontend with a score renderer (Verovio or OpenSheetMusicDisplay)
  for preview and lyric editing.
- Docker image for the worker (Java + Audiveris + OCR + engraver + fonts).
- Abuse protection: size/page limits, rate limits, free CAPTCHA.

## Phases

0. **Trial**: collect samples (see [samples/README.md](../samples/README.md)),
   run Audiveris with and without cleanup, check shared-staff voices, check
   Hebrew lyric output end-to-end through to the PDF.
1. **CLI pipeline**: cleanup, OMR wrapper, rough lyrics, PDF, evaluation script.
2. **Web MVP**: upload, job status, lyric correction screen, downloads.
3. **Quality**: confidence warnings, scanning tips, fallback engine,
   simple note correction in the browser.
4. **Deployment**: hosting and compute, discussed separately.

## Risks

- Very poor scans produce wrong notes; mitigated by cleanup, preview and
  warnings, and later by note correction.
- Two voices on one staff are a known weak spot for OMR; to be measured in Phase 0.
- Hebrew text order in the PDF; verified early in Phase 0.
