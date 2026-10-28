import zipfile

from reportlab.pdfgen import canvas

from readablemusic.textlayer import fix_lyrics

# A 200 x 100 pt page rendered 2 px per point, so the picture is 400 px wide.
SHEET = """<sheet><page><picture width="400" height="200"/>
<lyric-item kind="Syllable" syllabic="SINGLE" value="wor1d" id="1">
  <bounds x="100" y="80" w="64" h="22"/>
</lyric-item>
<lyric-item kind="Syllable" syllabic="SINGLE" value="-" id="2">
  <bounds x="300" y="80" w="10" h="22"/>
</lyric-item>
</page></sheet>"""


def test_fix_lyrics_takes_text_from_pdf(tmp_path):
    pdf = tmp_path / "score.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(200, 100))
    c.setFont("Helvetica", 12)
    c.drawString(50, 50, "world")
    c.save()
    omr = tmp_path / "score.omr"
    with zipfile.ZipFile(omr, "w") as z:
        z.writestr("book.xml", "<book/>")
        z.writestr("sheet#1/sheet#1.xml", SHEET)

    assert fix_lyrics(omr, pdf) == 1
    with zipfile.ZipFile(omr) as z:
        sheet = z.read("sheet#1/sheet#1.xml").decode()
        assert 'value="world"' in sheet and 'value="-"' in sheet
        assert z.read("book.xml") == b"<book/>"
