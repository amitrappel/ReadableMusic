# Real samples, round 1 (2026-10-28)

17 PDFs in `samples/raw` (140 pages): 12 clean exports from notation software, 1 scan
with no text layer, several hymnal-style scans; 5 with Hebrew titles or lyrics.
Run with `uv run python eval/samples.py`; compare the output PDFs with the originals.

## Failures fixed

| Problem | Cause | Fix |
|---|---|---|
| Hebrew-named files failed in seconds | Audiveris's Windows launcher garbles non-ASCII paths; Verovio cannot open them either | Audiveris works on an ASCII copy in a temp folder; Verovio gets the text, not the path |
| Hurricane crashed after recognition | music21 re-notation on write trips over voice numbering | Write with `makeNotation=False`; Audiveris output is already notated |
| A lyrics-only page failed the whole book | Audiveris stops at a page without staves | On failure, retry without pages with almost no staff evidence (not before: noisy music pages look the same) |
| Audiveris hung for hours on one file | — | Time limit of 60 s + 180 s per page |
| Re-export failed on one PDF | Control character in the PDF text | Keep printable characters only; on failure keep the OCR'd lyrics |
| Off-by-one in binarisation | Otsu's threshold belongs to the dark class | `<=` instead of `<`; pure black-and-white pages were invisible before |

## Quality fixes

- **Titles, headers and footers** became lyrics or text directions (copyright lines
  as Bass lyrics). `cleanup.py` now whitens the page above the first and below the last
  staff line, beyond the first band of 3 empty interlines, capped at 6 interlines above
  and 10 below. Staff lines are found column by column (five lines one interline apart),
  so skewed scans and black banners do not mislead it, and pages with too few matches
  are left alone.
- **Chord symbols and long text directions** are removed (`tidy.py`), including chord
  names read as plain text.
- **Lyrics from the PDF text layer** (`textlayer.py`): Audiveris keeps each syllable's
  box in its project file; the PDF characters inside that box replace the OCR'd value,
  then the project is re-exported (5 s). Music-font characters (some programs draw
  notes as text) are ignored. Clean English PDFs were already about 95% right
  (Lida Rose: 19 of 457 syllables changed, e.g. `A11` -> `All`, `'10..` -> `no.`); a
  Hebrew PDF got 353 of its syllables replaced by real Hebrew.
- **Hebrew in the PDF**: bundled David Libre (OFL), which has Latin and Hebrew letters;
  purely Hebrew text is reversed for reportlab, which draws left to right.

The answer-key evaluation did not regress (clean 98.9% notes / 89.8% lyrics,
shared staves 98.0% / 88.7%, bad scans 91.9% / 82.0%).

## Still open

- **Hebrew lyrics need Hebrew OCR in Audiveris.** With the English model, Audiveris
  splits Hebrew lyrics wrongly (items spanning several syllables, syllables a note off);
  the text layer fixes the letters but not the split.
- Fair Phyllis draws barlines between the staves only (Renaissance style); Audiveris
  finds 12 of about 40 measures.
- Irish Blessing: some lyric lines are not detected as text at all.
- Garbage text directions remain where symbols are OCR'd as text (`UL LL u u`).
- Part names are often the placeholder "Voice".
