import music21 as m21
from reportlab.pdfgen import canvas

from readablemusic.engrave import to_pdf
from readablemusic.ocr import restores_letters
from readablemusic.pagetext import (Bounds, Item, Line, add_directions, drop_repeated_text, header_lines,
                                    measure_places, read_page_text, sort_text, write_page_text)

BOUNDS = Bounds(top=130, first=150, last=700, bottom=760)  # on a page 800 pt high


def make_pdf(path):
    c = canvas.Canvas(str(path), pagesize=(600, 800))
    c.setFont("Helvetica", 24)
    c.drawCentredString(300, 740, "Mamma Mia")
    c.setFont("Helvetica", 11)
    c.drawString(40, 700, "Words and Music by: ABBA")
    c.drawRightString(560, 700, "arr. Ron Gang")
    c.drawRightString(560, 686, "and Shani Wahrman")
    c.drawString(40, 662, "Swing")  # tempo mark just above the first staff
    c.drawString(300, 662, "Am7 D7")  # chord symbols there: music
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
        ("direction", "Swing", 0),
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


PAGE = Bounds(100, 120, 700, 720)


def _kinds(*lines):
    items = sort_text([[Line(text, box) for text, box in lines]], [PAGE], [600])
    return [(i.kind, i.name) for i in items]


def test_a_label_alone_takes_the_name_beside_it():
    assert _kinds(("Arr.", (400, 40, 430, 52)), ("Tzvi Sherf", (440, 40, 520, 52))) == [("arranger", "Tzvi Sherf")]


def test_a_label_alone_takes_the_name_under_it():
    kinds = _kinds(("Arrangement by", (20, 40, 140, 52)), ("Words and Music by", (400, 40, 560, 52)),
                   ("Deke Sharon", (20, 56, 120, 68)), ("John Lennon", (400, 56, 500, 68)))
    assert sorted(kinds) == [("arranger", "Deke Sharon"), ("composer", "John Lennon"), ("lyricist", "John Lennon")]


def test_a_spoiled_label_is_still_a_label():
    kinds = _kinds(("Lyrics & wmusic", (300, 40, 420, 52)), ("Shalom Chanoch", (430, 40, 560, 52)))
    assert sorted(kinds) == [("composer", "Shalom Chanoch"), ("lyricist", "Shalom Chanoch")]


def test_hebrew_words_and_music_gives_both_roles_in_either_spelling():
    for label in ("מילים ולחן", "מלים ולחן"):
        kinds = _kinds((f"{label}: שלום חנוך", (300, 40, 500, 52)))
        assert sorted(kinds) == [("composer", "שלום חנוך"), ("lyricist", "שלום חנוך")]


def test_a_verse_above_the_music_is_a_note_not_a_credit():
    assert _kinds(("Maria aiparthene kosmu pantos Kiria, Animfevte.", (100, 60, 500, 72))) == \
        [("note", "Maria aiparthene kosmu pantos Kiria, Animfevte.")]


def test_a_reading_restores_letters_only_if_it_keeps_all_the_others():
    assert restores_letters("ניגע אל החלו", "ניגע אל החלום")
    assert restores_letters("עיבוד: שר צבי :", "עיבוד: צבי שרף")  # words out of order in the PDF
    assert not restores_letters("ניגע אל החלום", "ניגע אל החלום")
    assert not restores_letters("ניגע אל החלו", "ניגע אל החלם")


def test_directions_go_above_the_measure_under_them():
    measures = []
    for number in (1, 2, 3):
        m = m21.stream.Measure([m21.note.Note("C4", quarterLength=4)], number=number)
        m.layoutWidth = 100  # tenths of an interline
        measures.append(m)
    measures[0].insert(0, m21.layout.SystemLayout(leftMargin=50))
    measures[2].insert(0, m21.layout.PageLayout(isNew=True))
    measures[2].insert(0, m21.layout.SystemLayout(leftMargin=50))
    score = m21.stream.Score([m21.stream.Part(measures)])
    places = measure_places(score, interline=20)  # 2 pixels per tenth
    assert places == [(1, 0, 0, 100, 300), (2, 0, 0, 300, 500), (3, 1, 0, 100, 300)]
    items = [Item("direction", "Swing", 0, (160, 0, 200, 10), 10), Item("direction", "Slower", 1, (10, 0, 40, 10), 10)]
    assert add_directions(score, items, places, [0.5, 0.5]) == 2  # half a point per pixel

    def words(n):
        return [e.content for e in score.parts[0].measure(n).getElementsByClass(m21.expressions.TextExpression)]
    assert (words(1), words(2), words(3)) == ([], ["Swing"], ["Slower"])
