import music21 as m21
from reportlab.pdfgen import canvas

from readablemusic.engrave import to_pdf
from readablemusic.pagetext import (Bounds, Item, drop_repeated_text, header_lines, read_page_text,
                                    write_page_text)

BOUNDS = Bounds(top=130, first=150, last=700, bottom=760)  # on a page 800 pt high


def make_pdf(path):
    c = canvas.Canvas(str(path), pagesize=(600, 800))
    c.setFont("Helvetica", 24)
    c.drawCentredString(300, 740, "Mamma Mia")
    c.setFont("Helvetica", 11)
    c.drawString(40, 700, "Words and Music by: ABBA")
    c.drawRightString(560, 700, "arr. Ron Gang")
    c.drawRightString(560, 686, "and Shani Wahrman")
    c.drawString(40, 662, "Swing")  # tempo mark just above the first staff: music
    c.drawString(100, 400, "oom pa")  # among the staves: music
    c.drawCentredString(300, 70, "© 2011")  # right under the music, in the area kept for recognition
    c.drawCentredString(300, 20, "Sung at the 2011 festival")
    c.showPage()
    c.setFont("Helvetica", 11)
    c.drawString(40, 770, "Mamma Mia")  # running title
    c.drawRightString(560, 770, "2")  # page number
    c.drawString(40, 750, "Bridge")  # above the first staff, but music
    c.drawCentredString(300, 20, "*sing softly")
    c.save()


def test_text_is_sorted_by_place_and_content(tmp_path):
    pdf = tmp_path / "score.pdf"
    make_pdf(pdf)
    items = read_page_text(pdf, [BOUNDS, BOUNDS])
    found = [(i.kind, i.text, i.page) for i in items]
    assert found == [
        ("title", "Mamma Mia", 0),
        ("composer", "Words and Music by: ABBA", 0),
        ("lyricist", "Words and Music by: ABBA", 0),
        ("arranger", "arr. Ron Gang and Shani Wahrman", 0),
        ("rights", "© 2011", 0),
        ("note", "Sung at the 2011 festival", 0),
        ("furniture", "Mamma Mia", 1),
        ("furniture", "2", 1),
        ("music", "Bridge", 1),
        ("note", "*sing softly", 1),
    ]
    assert header_lines(items) == [
        ("title", "center", "Mamma Mia"),
        ("composer", "right", "Words and music: ABBA"),
        ("arranger", "right", "Arrangement: Ron Gang and Shani Wahrman"),
    ]


def test_output_has_standard_header_and_footnotes(tmp_path):
    items = [Item("title", "Mamma Mia", 0, (0, 0, 0, 0), 24), Item("composer", "Music by ABBA", 0, (0, 0, 0, 0), 11),
             Item("rights", "© 2011", 0, (0, 0, 0, 0), 9), Item("note", "Sung in 2011", 0, (0, 0, 0, 0), 9),
             Item("furniture", "MAMMA MIA", 1, (0, 0, 0, 0), 9)]
    m = m21.stream.Measure([m21.expressions.TextExpression("MAMMA MlA"), m21.note.Note("C4", quarterLength=4)])
    score = m21.stream.Score([m21.stream.Part([m])])
    drop_repeated_text(score, items)
    assert not score.recurse().getElementsByClass(m21.expressions.TextExpression)
    dest = tmp_path / "score.musicxml"
    score.write("musicxml", dest, makeNotation=False)
    write_page_text(dest, items, ["Original part names: Soprano – Shani"])
    xml = dest.read_text(encoding="utf-8")
    assert "<work-title>Mamma Mia</work-title>" in xml
    assert '<creator type="composer">ABBA</creator>' in xml and "Music: ABBA</credit-words>" in xml
    assert "<rights>© 2011</rights>" in xml
    assert '<miscellaneous-field name="footnote">Sung in 2011</miscellaneous-field>' in xml
    assert "Original part names: Soprano – Shani" in xml
    assert to_pdf(dest, tmp_path / "score.pdf") == 1
    m21.converter.parse(dest)  # still valid enough to read
