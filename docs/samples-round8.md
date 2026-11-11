# Claude reads a phone photo itself (round 8, 2026-11-11)

נערה במשקפים, page 1: a phone photo (JPEG, 1338 × 1916 pixels, a staff space of about 14
pixels) of a handwritten arrangement, at a slight angle, its left edge with the part labels
cut off. Six staves on the first system, then two (treble and bass), with words in Hebrew
letters under both: the first sample with Hebrew lyrics.

## Audiveris alone

Audiveris found 11 of the 12 staves (not the bass staff of the last system) and the
measures of the first two systems, but only 61 of some 250 noteheads; the score was nearly
all rests, 14 measures for 21. Claude's reading of each system did not run: Audiveris's
score had 3 systems for the 4 on the page.

## Changes

- **Claude reads the systems itself** (`fresh.py`) where Audiveris's reading is too poor to
  correct: its systems are not those on the page, or it holds more rests than notes. Each
  system is cut from the full width of the page down to the next, so that it holds a staff
  Audiveris missed; Claude writes out its staves (label, clef, key, time) and its measures,
  numbered on from the system before, in the format of the draft reading. The score is
  built as Audiveris exports one, a part for each staff of each system, shown only in its
  own, and `merge_parts` gives the staves to voices.
- **Hebrew syllables** are copied in Hebrew letters, without vowel points, with "-" at the
  end where the word goes on, whichever side the hand drew it.

## Result ($0.35, plus $0.05 for the first-page check)

All 12 staves, with their clefs (the tenor's treble 8 included), and 21 measures, the
systems starting at measures 1, 5, 10 and 16 as numbered on the page; 104 syllables.

| Where | Mistake | Cause |
|---|---|---|
| from 5 | the lower staff given to the tenor, whose first system then went into bass clef | the labels are cut off; without them `merge_parts` matched the staves by range |
| title | "נערה ברושקניירים" | Claude's reading of the handwriting (another run: "נערה בחשקנורים") |
| 5–9 | some notes a step or two off; "אי" for "א-", "סח" for "עם" | Claude, on a staff space of 14 pixels |
| all | no hairpins | not asked for |

Not yet compared with the page bar by bar.

## A check before paying for Claude's reading

The web app now stops a scan or photo that looks too poor to read well before Claude reads
its systems, says why, and offers to upload a better image or to read it anyway; the
command line does so with `--check`. A run stopped keeps Claude's first-page reading, so
that reading it anyway does not pay for it twice. It stops where:

- an uploaded image has fewer than 7 pixels between staff lines, before Audiveris runs
  (the scans read well had 8 and more);
- Audiveris's reading is too poor to correct (`poor`), the case that sends the systems to
  Claude to read itself; or
- Claude, in its first-page check, finds the page "poor" ("clear", "partly" or "poor",
  with what in the image makes it hard).

Pixels alone do not tell the photo from the scans that were read well:

| Sample | Kind | Interline at its own size | Gray share of the ink | Read |
|---|---|---|---|---|
| אתה הצבת | scan, 151 dpi | 12.3 px | 0.42 | well |
| Siyahamba | scan, 118 dpi | 8.3 px | 0.59 | well |
| האדון הרופא | scan, 300 dpi | 17.3 px | 0.20 | well |
| נערה במשקפים | phone photo | 14.4 px | 0.60 | Audiveris little of it |

On נערה במשקפים the check stopped at $0.04: Audiveris read little, and Claude found the
page "partly" legible (part names cut off at the left edge, a slight angle); it put
reading it anyway at $0.32 (8 cents a system; $0.35 when it ran).

Evening out the light (dividing by the paper's brightness) left the notes as they were
and made Audiveris fail on the page, so there is no such step; pages are only scaled to an
interline of 24 pixels, as before.
