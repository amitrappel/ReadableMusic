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
  one from its clef and range (a guess), and a staff holding two voices is named for both
  (`Soprano, Alto`).
- **Footnotes on page 1:** `Original part names: Soprano – Shani, ...`, notes, copyright.
  They are `miscellaneous-field` and `rights` in the MusicXML. Verovio cannot print them,
  so the PDF step draws them in a bottom margin, and the browser editor shows them under
  the score.
- **Page numbers:** drawn by the PDF step from page 2 on.
- **Mixed Hebrew and Latin text** is ordered with `python-bidi`, replacing the reversal of
  purely Hebrew text.
