# Real samples, round 2 (2026-11-01)

Driven by feedback on "Mamma Mia 2.0": five voices came out as twelve parts, and the
credits (composer, arranger, ...) were lost.

## Parts

The first system names the singers (Shani, Yael, Salit, Guy, Doron) and the later ones
the voices (S, Mezzo, A, T, B). Audiveris joins staves of different systems only when
their names match, and it misread some names ("hdezzo", "13"), so it made 19 parts;
our merge, which matched names, still left 12.

- Systems that show as many staves as the fullest system are now matched **by position**,
  whatever their names. Names only place the staves of systems with hidden staves, matched
  against every name a voice has had so far.
- The name on the first system becomes the part name and the most common other name the
  abbreviation, which engravers print on the later systems: `Shani` / `S`.
- In PDFs with text, the part names come from the text layer too (`hdezzo` -> `Mezzo`).
  Audiveris exports names from its book-level part list, so that is renamed as well.

Other samples gained full names with abbreviations (`Tenor 1` / `T1`), and האדון הרופא,
which shows 3 staves in every system, now has 3 parts instead of 4.

## Credits

The page is blanked above the music before recognition, so credits are read from the PDF
text layer (`credits.py`): runs of text above the first staff of page 1 are classified by
their label (Music by, Words, arr., מילים, לחן, עיבוד, ...), the largest centred line is the
title, other centred lines are subtitles, an unlabeled name on the right is the composer.
Just above the first staff only labeled lines count, since tempo marks and section names
sit there. Copyright lines anywhere below the first staff go to `<rights>`.

They are written as MusicXML data (`work-title`, `creator`, `rights`) and as `credit`
lines, which Verovio prints in the page header (title in bold, enlarged). Text directions
or lyrics that repeat a credit (running titles on later pages) or a copyright are removed.

Scans have no text layer and get no credits yet: that needs Tesseract, which we do not
ship (Audiveris bundles it inside Java).

## Lyrics

- In PDFs with text, a lyric syllable with no text under it is a symbol read as text
  (double sharps as `x`) and is removed.
- Words that OCR left open (`pa...` marked as the start of a word) are closed; they were
  drawn as a row of hyphens up to the next syllable, sometimes measures later.
- Text drawn invisibly (the OCR layer scanners add) is no longer taken as the PDF's text;
  האדון הרופא had its lyrics "corrected" with that layer's OCR errors.

## Still open

- Lyrics a staff away: "tum" under Doron at the bottom of a system became directions above
  the next system's top staff.
- Syllables split differently from the PDF (`pa m-pa` for `pa oom-pa`).
- Credits for scans (Tesseract), and Hebrew PDFs with broken final letters (ם read as a
  control character).
