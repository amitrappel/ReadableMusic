# Bar-by-bar review: accidentals, ties and lyrics from the PDF drawing (round 6, 2026-11-08)

The user reads Fly Me to the Moon against the original from bar 1 and reports every
difference. Each one is traced to Audiveris's own reading (the `.mxl` in `work/`) or to a
later step, and fixed where it arises.

## Findings

| Bars | Mistake | Cause |
|---|---|---|
| 1 | `(swing)` missing | Audiveris did not read it, and page-text sorting left short text just above the first staff in the picture without keeping it |
| 7 alto | lyric `doo` missing | the sharp touches the lyric; OCR boxed `oo` and took it for a verse number, which is linked to no note |
| 7 alto | sharp missing | the same collision: Audiveris took the sharp into the text |
| 11–12 tenor | tie missing | a long flat tie along the top staff lines; Audiveris found no curve |
| 13–14 tenor | tie missing | the tie crosses a page break and is drawn in two halves; Audiveris found neither |

## Changes

- **Accidentals and ties from the PDF drawing** (`symbols.py`). Notation programs print
  accidentals as characters of a music font, with the origin at the height of the note,
  and draw ties as flat filled curves. Each accidental is matched to the notehead to its
  right at that height; a missing one is added to Audiveris's project and a misread one
  gets the printed shape. A curve whose ends land on two noteheads of one staff and pitch,
  with no notehead between, becomes a tie. Half a tie at the end of a staff is paired with
  the half at the start of the next system in the same part and pitch; on one page the
  halves are linked as Audiveris links them, across pages Audiveris joins them on export.
  The project is then exported again. Fonts read: Finale's Maestro and fonts laid out like
  it (`œ` notehead, `#` sharp), and SMuFL fonts (Leland, Finale Maestro).
- **Whole words from the text layer.** A syllable takes the letters next to it in the
  PDF's text order, so a letter that OCR lost to a touching symbol comes back (`iss` →
  `kiss`, `foun` → `found`); a space ends the word.
- **Words read as verse numbers.** Audiveris reads `o`, `oo`, `lo`, `l` and Hebrew `ו` as
  numbers and drops them from the lyrics. Where the text layer has letters there, the item
  becomes a syllable of the chord above it, unless that chord already has one in the line.
- **Directions above the staves.** Short text just above a page's first staff (at most 4
  words, not chord symbols) is whitened like the credits and printed above the measure
  under it, placed with the measure widths Audiveris exports. Text-layer PDFs only: on
  scans OCR there can be high notes.
- **Spacing** (user's request): staves 16 units apart instead of 12, systems 16 instead
  of 4, lyric word space 2.0 instead of 1.2. Fly Me to the Moon keeps 4 pages, with 4
  systems a page instead of 5.

- **Clef, key and time in the browser** (`reread.py`, "Clef, key and time" in the editor).
  A clef or key misread for a whole part spoils every note, and on a handwritten score
  Audiveris cannot be relied on for either (אתה הצבת: treble read as bass, 3 flats and 3/8
  not read). The user picks the clef of each one-staff part, the key and the time; the
  notes keep their staff places and are read again on the server, their alterations
  worked out from printed accidentals, earlier ones in the measure, ties and the key.

- **Claude checks the first system** (`vision.py`, only with `ANTHROPIC_API_KEY`). Claude
  Opus 5.5 gets the first page and, enlarged, the start of its first system, and returns
  each staff's clef, the key, the time and the credits as JSON. Where it differs from the
  recognised score, the score is read again as above: clefs when its staves match the
  score's one for one (percussion staves left out), key and time only when the score does
  not change them later. On scans its credits replace the OCR's.

  Measured on page 1 of all 18 samples before building it (no answer key: every
  difference checked by eye). On the whole page alone it found the 3 real mistakes and
  miscounted Mamma Mia's 6 sharps as 7; with the enlargement it made no mistake. About
  10,000 tokens in and 200 out: 4.5 cents a score.

  | Sample | Corrected |
  |---|---|
  | אתה הצבת | bass → treble, key 0 → 3 flats, no time → 3/8; title, subtitle, composer where OCR had none |
  | Fair Phyllis | tenor treble → treble-8 |
  | Dr. Doolittle | tenor treble → treble-8; credits `Dr. Doglittle`, `Lyrics & wmusic` → `Dr. Doolittle`, `Words and music` |
  | the other 15 | nothing: Claude agreed |

## Results

All 18 samples run. Every added accidental and tie was cropped from the original and
checked by eye; none was wrong.

| Sample | Accidentals | Ties | Syllables no longer verse numbers | Words completed |
|---|---|---|---|---|
| Fly Me to the Moon | 9 | 9 | 3 | 4 |
| Irish Blessing | 5 | 0 | 0 | 0 |
| Lida Rose | 10 | 0 | 2 | 0 |
| Hurricane | 0 | 15 | 47 | 9 |
| Mamma Mia | 0 | 3 | 10 | 0 |
| Michtav le-achi | 0 | 10 | 47 | 5 |
| Somethin' Stupid | 0 | 21 | 3 | 0 |
| VCT Radioactive | 0 | 1 | 23 | 0 |
| You Will Be Found | 0 | 44 | 12 | 17 |
| נועדת לי | 2 | 5 | 39 | 2 |
| ניגע אל החלום | 0 | 0 | 102 | 2 |
| Fair Phyllis | 0 | 0 | 18 | 4 |

Directions printed: `(swing)` (Fly Me to the Moon) and `Intro` (Irish Blessing). The
answer-key evaluation is unaffected: its pages are images, which have no text layer or
drawing to read.

## Still open

- **אתה הצבת (handwritten)** after choosing treble, 3 flats and 3/8 has the right pitches
  but: eighths whose flags were missed are quarters, so most bars are too long; some notes
  sit a step off (the C upbeat as D) and naturals are missed; the canon entry marks ②→
  and ③→ are read as notes; the hand-lettered lyrics are garbled; title and credits are
  missing (all but the rhythm can be fixed in the editor).

- **Part names on scans:** Dr. Doolittle's `T.` and `B.` are not read, so its parts are
  named from their range (tenor as Soprano, bass as Baritone). Claude returns the labels;
  they are not used yet.
- **Syllables Audiveris did not detect at all** are still missing, though the text layer
  has them (Fly Me to the Moon, alto bar 15: `me`).
- **Fonts not read:** MuseScore 2 (`MScore-20`, Somethin' Stupid) and LilyPond
  (`Emmentaler`, Fair Phyllis) use their own codes for accidentals; Ave verum corpus draws
  every symbol as a path. Their ties are read.
- **Slurs** are not added, only ties.
- **Fair Phyllis** draws barlines between the staves only; Audiveris finds 12 of about 40
  measures.
