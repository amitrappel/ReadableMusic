import xml.etree.ElementTree as ET
import zipfile

from readablemusic.audiveris import header_clefs

SHEET = """<sheet><picture width="100" height="100"/>
<system id="1"><part id="1"><staff id="1" left="0" right="9"><lines/><header start="0" stop="5"><clef>9</clef></header>
<inters><clef kind="BASS" pitch="-2" shape="F_CLEF" staff="1" id="9"/></inters></staff></part></system>
<system id="2"><part id="1"><staff id="2" left="0" right="9"><lines/><header start="0" stop="0"/></staff></part></system>
<system id="3"><part id="1"><staff id="3" left="0" right="9"><lines/><header start="0" stop="5"><clef>11</clef></header>
<inters><clef kind="BASS" pitch="-2" shape="F_CLEF" staff="3" id="11"/></inters></staff></part></system>
</sheet>"""


def test_a_staff_without_a_clef_gets_the_treble_clef_audiveris_read_it_in(tmp_path):
    omr, mxl = tmp_path / "book.omr", tmp_path / "book.mxl"
    with zipfile.ZipFile(omr, "w") as z:
        z.writestr("sheet#1/sheet#1.xml", SHEET)
    measures = ("<measure number='1'><attributes><clef><sign>F</sign><line>4</line></clef></attributes></measure>"
                "<measure number='2'><print new-system='yes'/></measure>"
                "<measure number='3'><print new-system='yes'/></measure>")
    with zipfile.ZipFile(mxl, "w") as z:
        z.writestr("book.xml", f"<?xml version='1.0'?><score-partwise><part id='P1'>{measures}</part></score-partwise>")
    assert header_clefs(mxl, omr) == 2
    with zipfile.ZipFile(mxl) as z:
        root = ET.fromstring(z.read("book.xml").decode()[len("<?xml version='1.0'?>"):])
    assert [(m.findtext("attributes/clef/sign"), m.findtext("attributes/clef/line")) for m in root.iter("measure")] == [
        ("F", "4"), ("G", "2"), ("F", "4")]
    assert header_clefs(mxl, omr) == 0
