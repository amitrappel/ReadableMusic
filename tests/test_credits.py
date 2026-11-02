import music21 as m21
from reportlab.pdfgen import canvas

from readablemusic.credits import Credit, add_credits, drop_credit_text, name, read_credits


def test_read_credits_classifies_header_and_footer(tmp_path):
    pdf = tmp_path / "score.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(600, 800))
    c.setFont("Helvetica", 24)
    c.drawCentredString(300, 740, "Mamma Mia")
    c.setFont("Helvetica", 11)
    c.drawString(40, 700, "Words and Music by: ABBA")
    c.drawRightString(560, 700, "arr. Ron Gang")
    c.drawRightString(560, 686, "and Shani Wahrman")
    c.drawString(40, 662, "Swing")  # tempo mark just above the first staff
    c.drawCentredString(300, 30, "© 2011")
    c.save()

    # First staff line at 150 pt from the top, kept area from 130 to 760.
    credits = read_credits(pdf, (150, 130, 760))
    found = [(c.kind, c.text, c.justify) for c in credits]
    assert found == [
        ("title", "Mamma Mia", "center"),
        ("composer", "Words and Music by: ABBA", "left"),
        ("lyricist", "Words and Music by: ABBA", "left"),
        ("arranger", "arr. Ron Gang and Shani Wahrman", "right"),
        ("rights", "© 2011", "center"),
    ]
    assert [name(c) for c in credits[1:4]] == ["ABBA", "ABBA", "Ron Gang and Shani Wahrman"]


def test_add_credits_writes_data_and_page_text(tmp_path):
    m = m21.stream.Measure([m21.expressions.TextExpression("MAMMA MlA"), m21.note.Note("C4", quarterLength=4)])
    score = m21.stream.Score([m21.stream.Part([m])])
    credits = [Credit("title", "Mamma Mia", "center", 24), Credit("composer", "Music by ABBA", "left", 11),
               Credit("arranger", "arr. Ron Gang", "right", 11), Credit("rights", "© 2011", "center", 9)]
    drop_credit_text(score, credits)
    assert not score.recurse().getElementsByClass(m21.expressions.TextExpression)
    dest = tmp_path / "score.musicxml"
    score.write("musicxml", dest, makeNotation=False)
    add_credits(dest, credits)
    xml = dest.read_text(encoding="utf-8")
    assert "<work-title>Mamma Mia</work-title>" in xml
    assert '<creator type="composer">ABBA</creator>' in xml and '<creator type="arranger">Ron Gang</creator>' in xml
    assert "<rights>© 2011</rights>" in xml
    assert xml.count("<credit ") == 3  # the copyright is data only
    m21.converter.parse(dest)  # still valid enough to read
