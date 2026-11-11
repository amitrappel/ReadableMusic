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

## A sharper photo, and the user's corrections

A second photo, 3000 × 4000 pixels, with 29 pixels between staff lines: the check stopped it
again (Audiveris lost a system of the handwriting), Claude reading the page "partly".

| Report | Cause | Change |
|---|---|---|
| parts are S1 S2 A1 A2 T B; from bar 5 the lower staff went to the tenor | the edge cut the labels ("p1", "o2", "nor", "ss"); read one system at a time, Claude named them "" or now Alto 2, now Soprano 2 | Claude names the staves of all systems at once, from their left ends side by side (3 cents) |
| the tenor's clef is treble-8 | the bass staff, given to the tenor, gave it its clef | as above |
| no crescendo in bar 1, no diminuendo in bar 4 | Claude was not asked for hairpins; a start in the middle of a note, which music21 hangs on the next note, reversed one | hairpins are asked for, and start on the note sounding, or on the next measure's first where they start on a measure's last note and reach the barline |
| "דו" for "או" in bars 1–4; credits misread | the hand writes Hebrew in cursive | the prompts say so; the first-page check sees the top of the page enlarged, in two halves |
| many notes wrong from bar 5 | Claude's reading of the handwriting | none found (below) |

On 40 notes of bars 5–8 and 10–12 checked against the photo line by line, five readings of
systems 2 and 3 got 24 to 34 right, mostly a step or a third off, in other places each time.
Higher effort read worse (24) at more cost; the system cut in two enlarged halves (32) got
bars 5–8 right but not 10–11. The title now reads right; the composer's name, in small
cursive, is still missed or misread.
