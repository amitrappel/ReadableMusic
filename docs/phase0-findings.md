# Phase 0 findings (2026-10-27)

## Samples

Five arrangements, 86 pages (`samples/raw/`, not in git). All are clean PDFs
exported from notation software, not scans. Large modern a cappella scores:
8-12 staves per system (solo, divided SATB, often two voices per staff), plus a
vocal percussion staff and chord symbols. Lyrics are English or transliterated
Hebrew in Latin letters. Most PDFs contain the lyrics as real text with
positions; some pages have them as outlines (no text).

Decisions after review:
- Inputs: both clean PDFs and real scans/photos.
- Lyrics: English (Latin script) first; Hebrew script later.
- Percussion staves and chord symbols: ignored.

## Engine research

Audiveris remains the choice. As of October 2026 it is the only free engine
that handles full multi-staff pages, writes MusicXML and reads lyrics. Neural
alternatives do not fit 10-staff vocal scores: homr (pitch and rhythm only, simple
music), SMT (piano, outputs **kern), LEGATO (outputs ABC; weights unclear).
Latest Audiveris is **5.11.0** (July 2026).

Setup notes:
- The Windows console MSI can be unpacked without installing:
  `msiexec /a <msi> /qn TARGETDIR=<dir>`; run `Audiveris/Audiveris.exe -batch -transcribe -export -output <dir> -- <image>`.
- No OCR languages are bundled in that package. Download `eng.traineddata` from
  `tesseract-ocr/tessdata` and set `TESSDATA_PREFIX` to its folder, otherwise
  lyrics are silently skipped.

## Results on clean pages (one page per sample)

- 20-70 s per page on this PC, depending on resolution.
- All systems, staves and measures found on all five pages. Full-measure rests correct.
- Stemmed notes, beams, 16ths and lyrics: mostly correct. Lyrics need fixing
  (OCR typos like `tlf`/`tif`, `D00n`/`Doon`; some syllables with extender lines missed).
- Hurricane: whole notes often read as rests. Not seen in the other samples.
- Part names from OCR are unreliable on later pages (`SI`, `82`, `BZ`); take them from page 1.
- Two-note chords on one staff: second note sometimes dropped.
- Staff spacing ("interline") matters most. Target **about 20-30 px**: 300 DPI gave
  13-17 px on the densest scores, and 450 DPI did not improve results further.

## Results on synthetic bad scans

Pages were degraded to 200 DPI, skewed 1.8°, given a shadow, grain, specks,
blur and JPEG compression, then compared with the clean-page result.

| Page | Interline | Notes matching clean result |
|---|---|---|
| נועדת לי p4, as is | 14 px | 61-98% per part |
| נועדת לי p4, upscaled 2x | 28 px | 84-100% per part |
| Michtav p2, as is | 11 px | collapses (wrong part count) |
| Michtav p2, upscaled 2x | 23 px | still collapses (15 parts instead of 9) |

Michtav has 1 px staff lines, which almost vanish after degrading. Upscaling alone
is not enough there; real cleanup (binarisation, line repair) is needed.

## Consequences for Phase 1

1. Two input routes:
   - **Clean PDF**: render at a DPI chosen so the interline is about 20-25 px, and take lyrics
     from the PDF text layer where present (exact, no OCR). OCR only for outlined pages.
   - **Scan/photo**: measure interline, upscale to target, then cleanup. Michtav-degraded
     is the benchmark page for cleanup work.
2. Evaluation needs ground truth. Exact MusicXML exported from the arrangers'
   notation files would be ideal; otherwise hand-corrected pages.
3. Lyrics correction in the browser stays essential: OCR lyrics are about 60-90% right.
4. Process the whole PDF as one Audiveris book, not page by page, so that time and key
   signatures and part names carry over.
