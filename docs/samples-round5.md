# OCR resolution, stray lyric lines, misread clefs (round 5, 2026-11-07)

## Changes

- **Credits on scans** are read with Tesseract (`tesserocr`, `eng` and `heb` data in
  `tools/tessdata`); letters a PDF's text layer loses are repaired the same way.
- **Title, credits and part names** can be edited in the browser ("Edit title and parts").
- **OCR resolution:** Audiveris now tells Tesseract the scans are 300 dpi. Left unset,
  Tesseract works as at 70 dpi and misses whole lyric lines (Irish Blessing: 24 of 62
  syllables).
- **Marks read as lyrics:** at that resolution fermatas come out as an `m` on a lyric line
  of their own, which pushed the real words to verse 2 in that system. A system's lyric
  line of at most two lone Latin letters is dropped and the verses renumbered from 1.
  A lone Hebrew letter is a sung syllable and stays.
- **Misread clefs:** a run of at most 12 measures in a clef other than its part's main
  one is reread under the main clef when that brings its notes at least 3 semitones
  nearer the rest of the part, or when it is an octave-up treble clef. Longer runs are
  real changes (Lida Rose's treble pages) and stay.

## Results

All 18 samples run; note counts are unchanged. Evaluation (notes/lyrics):

| Set | Round 3 | Round 5 |
|---|---|---|
| satb | 98.9 / 89.8 | 98.9 / 89.6 |
| shared | 98.0 / 88.7 | 98.0 / 95.5 |
| bad | 91.9 / 82.0 | 91.6 / 86.6 |

Clefs were reread in 13 stretches: All My Loving (5), Dr. Doolittle (6), נועדת לי (1),
אתה הצבת (1).

## Still open

- **A clef misread on every system** cannot be found this way, since there is nothing to
  compare with. Dr. Doolittle's tenor staff is read as treble (it is octave treble), and
  אתה הצבת's handwritten treble clef as bass, so the whole song is a 13th low. Its one
  system read as octave treble now follows the rest. Both need a clef choice per part in
  the browser, which the editor does not have yet.
- **Scans:** אתה הצבת has no credits, Siyahamba's footnote is a fragment, and Dr.
  Doolittle's title reads `Doglittle`.
- **Dr. Doolittle names:** `Soprano, Alto`, `Soprano`, `Baritone` where the page says
  `S. A.`, `T.`, `B.`; fixable in the browser.

## Next steps

1. **Clef per part in the browser.** Add a clef choice (treble, octave treble, bass, …) to
   each part row of the "Edit title and parts" panel. Changing it rereads the part's notes
   on the same staff positions, as `readablemusic.clefs.moved` does in Python. This fixes
   אתה הצבת (bass → treble) and Dr. Doolittle's tenor (treble → octave treble).
2. **Hosting.** The `hosting` branch's Dockerfile must fetch `heb.traineddata` (and
   `eng.traineddata`) into `tools/tessdata`, as `scripts/fetch_tools.py` does locally;
   without it credits on scans are not read. Merge `master` into `hosting` after that.
3. **Smaller fixes:** credits on אתה הצבת, Siyahamba's footnote fragment, the title
   `Doglittle`.
4. **Lyric coverage** below 75% of letters remains on Michtav, ניגע and Hurricane; measure
   again with this round's OCR resolution before choosing what to try.

## How this round was checked

- `uv run pytest -q` (43 tests).
- `uv run python eval/run.py`: the Bach evaluation above.
- `uv run python eval/samples.py [name ...]` into `work/samples` (delete a sample's PDF to
  rerun it). `work/samples-round4` holds the run before this round for comparison.
- The local server must be restarted to pick up pipeline changes.
