# Claude reads scans again; chord symbols (round 7, 2026-11-10)

The user read Siyahamba against the original. Siyahamba is a scan at 118 DPI (802 × 1249
pixels for the page): a staff space is about 6 pixels and the staff lines are thick and
blurred.

## Findings

| Bars | Mistake | Cause |
|---|---|---|
| all | chord symbols (G, D7, C) missing | dropped on purpose until now (scope decision of 27 Oct, reversed) |
| 0 | the alto's second D missing | Audiveris: the alto voice read as one quarter for two eighths |
| 1 | no tie; the second chord an A instead of G and B | Audiveris: tie missed, chord a step off with a note lost |
| 2 | no triplet in the upper staff, the tied D missing; the staves out of step | Audiveris: triplet bracket missed; in the lower staff an eighth read as a 16th |

None of them comes from our later steps, and the PDF has no text layer or drawing to
correct them from.

## Changes

- **Claude reads each system of a scan again** (`reader.py`). It gets the system cut from
  the page and Audiveris's reading as text, one line per voice (`G4+B4 2~, G4+B4 8, F#4+A4 8`),
  and writes the system out again in the same form, with its chord symbols. A measure whose
  voices all add up replaces Audiveris's; lyrics stay in their voice at their onset, and
  directions at theirs. Accidentals are printed where the key and the measure do not give
  them; rewritten measures are beamed by music21. Runs only on scans (the pipeline's
  `scanned`: no credits in the PDF's text) and with `ANTHROPIC_API_KEY`.
- **Chord symbols** (`chords.py`). Audiveris reads few (2 of 9 on the first system of נועדת
  לי) and misreads some, so its own stay dropped. On a notation program's PDF they come from
  the text above each system's top staff, placed on the measure and time slot of Audiveris's
  project under them; a score with chord names in fewer than a quarter of its measures has
  rehearsal letters (A, B, C in You Will Be Found), not chords. On scans they come from
  Claude. The PDF prints them as on the page, with b and # for the flat and sharp signs
  the text font lacks.
- **Chord names read as text with ♭ or ♯** are now dropped like the others (`B♭m7/A♭` was
  printed as a direction in נועדת לי).
- **Long credits beside the title** are wrapped (Claude's reading of Siyahamba's credits
  ran into the title).

## Results

Measured before building, on Siyahamba and two chorales with known answers ($0.82):

| Score | Audiveris | With Claude |
|---|---|---|
| Siyahamba | bars 0–2 wrong as reported; 3 of 14 chords | bars 0–2 right; 14 of 14 chords |
| BWV 101.7, shared staves, 118 DPI | 98.3% of notes | 100% |
| BWV 10.7, degraded scan | 61.1% | 64.3% |

BWV 10.7 stays low because Audiveris missed a barline (21 measures for 22), which shifts
every later measure; Claude keeps Audiveris's measures. Inside them it filled four empty
measures and removed invented notes. Lyrics were unchanged once they were kept in their
voice. A system costs about 5 cents; Siyahamba's page $0.21, plus $0.04 for the first-page
check.

Chords from the text: נועדת לי 139, matching the original on page 1 (B♭m, B♭m7/A♭, Gm7♭5,
G♭, F7 on the third beat). No other notation-software sample prints chord symbols.

## Second reading of Siyahamba

| Bars | Mistake | Cause |
|---|---|---|
| 2 | `V1` printed under the notes, `God,` missing | Audiveris's OCR: a lyric line of its own for a misread word |
| 3 | `ll D` and `c1` instead of the first and second endings | Audiveris's OCR of the brackets and chord names; its first ending was lost by `merge_parts`, which copied measures and not the part's brackets |
| all | a note both parts sing has one stem, not two | Claude wrote such measures as one voice of chords |
| 7, 8 | the alto's beamed eighths overlap the soprano's | music21's `makeBeams` also turns stems, and turned the alto's up |
| all | words missing, the footnote and `Tune:` read as lyrics | Audiveris's OCR |

Claude, asked separately, put the two stems of bar 2 on the wrong notes: at 118 DPI it
cannot see them. Audiveris had them, as a second voice.

Changes:

- **Claude reads the text too.** Each event carries its syllables, one slot per line of
  words under the staff (`D4 8 [Si-|We]`); the answer lists the other words printed in the
  music (dynamics become dynamics), the first and second endings and the repeat signs.
  In the measures Claude read these replace Audiveris's. Words that the images of two
  systems both show are printed once, with the lower system.
- **A lone note on a staff two parts share** (most of its notes chords on one stem) is
  written in both voices, which prints its second stem as on the page.
- Beams no longer turn stems; a tie over the barline ends on its pitch in whichever voice
  holds it, and a tie with nothing to end on is dropped (one drew a line over four bars).
- The second voice's triplet bracket is not printed over the first voice's.
- `merge_parts` keeps a first or second ending that every part has over the same
  measures. Audiveris's own, on notation-program PDFs, are in a part or two over measures
  far apart (Hurricane 15, Mamma Mia 27) and stay dropped. The last ending is left open.
- A word that goes on in another voice ends in a printed hyphen: Verovio draws hyphens
  only within a voice, and drew one to the end of the system (15 syllables in 5 samples).
- The first-page check reads the footnotes, which replace OCR's on scans; on a scan its
  clef and key corrections are made before Claude reads the systems, and `fix_clefs` then
  changes clef signs only. Claude's pitches are as printed: moving them under the corrected
  clef put `01 - אתה הצבת` two octaves high.

| Score | Lyrics before | Lyrics now |
|---|---|---|
| BWV 101.7, 118 DPI | 88.0% | 100% |
| BWV 10.7, degraded | 92.8% | 98.7% |

Notes stay at 100% and 64.3%. A system now costs about 7 cents ($1.07 for 17 systems).
Siyahamba matches the original in bars 0–11 but for the open questions below.

## אתה הצבת

A handwritten canon, scanned at 151 DPI. The PDF draws it at 288 DPI, and it is turned by
about one degree. The comparison was made bar by bar against the original, before the user's
review; bars are numbered as in the output, the pickup as 1. Audiveris reads it with the wrong clefs, a 3/8 eighth as a quarter, and lyrics
garbled; Claude's second reading (round 7) had most of it right.

| Bars | Mistake | Cause |
|---|---|---|
| 25 | the last system (one bar, centred) missing | Audiveris: a staff that short is no staff, and once kept, its indent starts a score of its own |
| 13–16, 25 | Audiveris's draft two octaves and a third high | Audiveris: no clef found on staff 4 (and 7), so it reads the notes as treble but writes no clef, and the bass clef before seems to go on |
| 12, 16, 20, 24 | notes a step high, at the right end of the systems | Claude judges notes against level lines; the staff lines rise by about a staff space over a system |
| 9, 10, 23 | single notes a step off (another run) | Claude: in every such case Audiveris had the head right |
| 21 | two bars as one measure | Audiveris: a barline missed |
| 1 | the C on a ledger line as D | the hand drew it close to the staff (Audiveris and Claude) |
| 11, 25 | a quarter for an eighth, an eighth for a sixteenth | Claude, in one run of two: the flags are faint or missing |
| all | slurs, fermatas missing; ①②③ as text or missing | slurs: never kept by `merge_parts`; the rest not asked for |

Changes:

- **Audiveris keeps short staves and does not start a new score at an indented system**
  (`LinesRetriever.minStaffLength=10`, `ProcessingSwitches.indentations=false`; for all
  inputs, not checked on the other samples).
- **The clef each system's notes were read in is written at its start** where Audiveris
  wrote none (`audiveris.header_clefs`, after every export). It changes a score only where
  a staff had no clef and the clef before was another.
- **Each system is turned level** before Claude sees it, by the slope of its staff lines in
  Audiveris's project.
- **Claude marks fermatas (`^`) and slurs (`(` `)`)** in its events; slurs are numbered
  over barlines and systems, and kept by `merge_parts` where Claude rewrote the measures
  (Audiveris's own slurs on notation programs' PDFs are still dropped). Circled numbers
  print as the number in a circle; syllables keep their accents (híz, jéw).
- **A measure that adds up to two bars**, with an event ending at the barline, becomes two.
- **Claude looks again** at a system where a voice does not add up to the time signature
  (the first and last measures may be short): one more request, which in the test fixed
  both measures it was asked about.
- **Audiveris's pitch is kept** for a lone note one step from Claude's lone note, on the
  staff (not on ledger lines), where the voice has as many events in both. Asked to look
  again at such a note, Claude kept its C for the D on the second line.

Result: all 25 measures as on the page but bar 6 (A natural for A flat) and a fermata in
bar 9 that belongs to the "(Finis 𝄐)" under it, which Claude puts on the system above
despite being told. Claude's readings differ from run to run; the second run had other
notes a step off, which the kept pitches mended. $0.30 for the 7 systems, one read twice.

## Still open

- **Barlines Audiveris missed** are not mended; Claude could split a measure that adds up to
  two.
- **`01 - אתה הצבת`:** bar 6's A natural and bar 9's fermata (above); lyric "of" for "ot"
  in bar 13.
- **Claude reads differently each run.** Thinking, or two readings compared, may steady it,
  at two to three times the cost.
- No sample scan has lyrics in Hebrew script, so Claude's reading of them is untested.
- **Memory:** the second reader loads the pages again for its crops; on the server, with a
  key, that doubles the pages held for a moment.
