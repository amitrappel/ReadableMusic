import re
import zipfile

from reportlab.pdfgen import canvas

from readablemusic.textlayer import fix_text

# A 200 x 100 pt page rendered 2 px per point, so the picture is 400 px wide.
SHEET = """<sheet><page><picture width="400" height="200"/>
<lyric-item kind="Syllable" syllabic="SINGLE" value="wor1d" id="1">
  <bounds x="100" y="80" w="64" h="22"/>
</lyric-item>
<lyric-item kind="Syllable" syllabic="SINGLE" value="-" id="2">
  <bounds x="300" y="80" w="10" h="22"/>
</lyric-item>
<sentence role="PartName"><bounds x="20" y="20" w="70" h="22"/></sentence>
<word value="hdezzo" id="3"><bounds x="20" y="20" w="70" h="22"/></word>
</page></sheet>"""
BOOK = '<book><logical-part id="2" name="hdezzo"/><logical-part id="3" name="S"/></book>'


def test_fix_text_takes_text_from_pdf(tmp_path):
    pdf = tmp_path / "score.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(200, 100))
    c.setFont("Helvetica", 12)
    c.drawString(50, 50, "world")
    c.drawString(12, 82, "Mezzo")
    c.save()
    omr = tmp_path / "score.omr"
    with zipfile.ZipFile(omr, "w") as z:
        z.writestr("book.xml", BOOK)
        z.writestr("sheet#1/sheet#1.xml", SHEET)

    assert fix_text(omr, pdf) == 3
    with zipfile.ZipFile(omr) as z:
        sheet = z.read("sheet#1/sheet#1.xml").decode()
        assert 'value="world"' in sheet and 'value="Mezzo"' in sheet and 'value="-"' not in sheet
        assert z.read("book.xml").decode() == BOOK.replace("hdezzo", "Mezzo")


# A sharp touching 'doo' hid the d: OCR boxed 'oo' and took it for a verse number.
VERSE_NUMBER = """<sheet><picture width="400" height="200"/><scale><interline main="20"/></scale>
<page><system><sig><inters>
<head-chord staff="6" id="7"><bounds x="104" y="40" w="16" h="30"/></head-chord>
<lyric-line number="1" staff="6" id="8"><bounds x="90" y="80" w="80" h="22"/></lyric-line>
<lyric-item kind="Number" value="oo" staff="6" id="9"><bounds x="110" y="80" w="22" h="22"/></lyric-item>
</inters><relations>
<relation source="8" target="9"><containment grade="1"/></relation>
</relations></sig></system></page></sheet>"""


def test_fix_text_turns_a_word_read_as_verse_number_into_a_syllable(tmp_path):
    pdf = tmp_path / "score.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(200, 100))
    c.setFont("Helvetica", 12)
    c.drawString(50, 50, "doo")
    c.save()
    omr = tmp_path / "score.omr"
    with zipfile.ZipFile(omr, "w") as z:
        z.writestr("book.xml", BOOK)
        z.writestr("sheet#1/sheet#1.xml", VERSE_NUMBER)

    assert fix_text(omr, pdf) == 1
    with zipfile.ZipFile(omr) as z:
        sheet = z.read("sheet#1/sheet#1.xml").decode()
    assert 'kind="Syllable" syllabic="SINGLE" value="doo"' in sheet
    assert re.search(r'<relation source="7" target="9">\s*<chord-syllable', sheet)
