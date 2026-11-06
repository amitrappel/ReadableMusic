# Text first, standard output (round 3, 2026-11-06)

Two decisions by the project owner: separating text from music is a preliminary step, and
the output does not imitate the original's layout but restructures every score into one
readable standard form.

## Text first

`pagetext.py` runs before recognition and sorts every line in a PDF's text layer:

| Group | What | Where it goes |
|---|---|---|
| Credits | title, subtitle, composer, lyricist, arranger, unlabeled names | standard header |
| Rights and notes | copyright, text under the music of page 1, `*` footnotes | footnotes on page 1 |
| Furniture | page numbers, dates, versions, catalogue numbers, running titles | dropped |
| Music | tempo marks, `Verse 2`, `cresc.`, lyrics | left on the page for recognition |

Text outside the music on later pages is furniture only if it repeats a credit or recurs
from page to page; otherwise it is music. Blanking the margins used to delete such text
(`Chorus 3`, `Bridge`), so it now spares those boxes, and whitens credits and furniture
inside the band it keeps ("Music by: ABBA", "©2011" right under a system).

Scans have no text layer: they still get only the geometric blanking, and no credits,
until Tesseract is added.

## Standard form

- **Header:** title (bold) and subtitles centred; `Music:`, `Words and music:` and
  `Arrangement:` on the right; `Words:` and unlabeled names on the left.
- **Part names:** standard voice names only (Soprano, Mezzo-soprano, Alto, Tenor, Baritone,
  Bass), numbered when a type occurs twice, abbreviated after the first system (S, Mz, A,
  T, Bar, B). Roles such as Lead and Solo stay. A part with no voice type anywhere gets
  one from its clef and range (a guess), and a staff holding two voices in at least a
  quarter of its measures is named for both (`Soprano, Alto`). Four staves with no names
  at all are S, A, T, B from the top, and a lone unnamed staff is just `Voice`. Names on
  two lines (`Tenor` over `Lead`) come from the PDF text, since Audiveris reads only the
  lower line. `Piano` is Audiveris's default for any braced pair, so it stays only on
  parts with chords of three or more notes.
- **Footnotes on page 1:** `Original part names: Soprano – Shani, ...`, notes, copyright.
  They are `miscellaneous-field` and `rights` in the MusicXML. Verovio cannot print them,
  so the PDF step draws them in a bottom margin, and the browser editor shows them under
  the score.
- **Page numbers:** drawn by the PDF step from page 2 on.
- **Mixed Hebrew and Latin text** is ordered with `python-bidi`, replacing the reversal of
  purely Hebrew text.

## Results

All 18 samples run. Note counts match round 2 on the 17 samples it covered, and the Bach
evaluation is unchanged (notes/lyrics: satb 98.9/89.8, shared 98.0/88.7, bad 91.9/82.0).
Lyric syllables mostly rise, for example +149 on You Will Be Found.

Part names were then checked against the originals and fixed by recomputing them from
saved recognition output, with one full run (Irish Blessing).

## Still open

- **Scans** have no credits and keep guessed names. Dr. Doolittle comes out as `Soprano,
  Alto`, `Soprano`, `Baritone` where the page says `S. A.`, `T.`, `B.`.
- **ניגע אל החלום:** the solo staff exists on only two systems, so the merge shifts the
  voices by one: the sopranos sit under `Alto` and so on down. Its PDF also loses final
  letters in the credits.
- **Somethin' Stupid:** the octave-treble clefs are read as plain treble, so the two
  voices are named Soprano and sound an octave high.
- **Michtav le-achi:** a solo staff with no label is a guessed `Tenor`.
- **אתה הצבת:** the handwritten treble clef is read as a bass clef, so its pitches are wrong.
- **Unlabeled credits** follow the usual layout (a name on the right is the composer),
  which Somethin' Stupid does not follow: `Music: Billy Strange`.
