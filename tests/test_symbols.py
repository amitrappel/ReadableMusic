import re
import zipfile

from reportlab.pdfgen import canvas

from readablemusic.symbols import fix_symbols

# A 200 x 100 pt page read at 2 px per point, with an interline of 20 px.
SHEET = """<sheet last-persistent-id="20"><picture width="400" height="200"/><scale><interline main="20"/></scale>
<page><system><sig><inters>
<head pitch="2" shape="NOTEHEAD_BLACK" staff="1" id="10"><bounds x="118" y="90" w="16" h="14"/></head>
<head pitch="4" shape="NOTEHEAD_BLACK" staff="1" id="11"><bounds x="200" y="150" w="16" h="14"/></head>
<head pitch="4" shape="NOTEHEAD_BLACK" staff="1" id="12"><bounds x="300" y="150" w="16" h="14"/></head>
{alter}</inters><relations>
{relation}</relations></sig></system></page></sheet>"""
FLAT = '<alter pitch="2" shape="FLAT" staff="1" id="13"><bounds x="100" y="80" w="12" h="40"/></alter>\n'
FLAT_HEAD = '<relation source="13" target="10"><alter-head dx="0.3" dy="0" grade="1"/></relation>\n'


def make_pdf(path):
    c = canvas.Canvas(str(path), pagesize=(200, 100))
    c.setFont("Helvetica", 12)
    c.drawString(150, 10, "œ")  # a notehead: the font is laid out like Finale's Maestro
    c.drawString(50, 50, "#")  # sharp, its origin at the height of head 10
    p = c.beginPath()  # tie from head 11 to head 12, arching upwards
    p.moveTo(110, 24)
    p.curveTo(120, 28.5, 139, 28.5, 149, 24)
    p.curveTo(139, 27.5, 120, 27.5, 110, 24)
    c.drawPath(p, fill=1, stroke=0)
    c.save()


def run(tmp_path, sheet):
    pdf, omr = tmp_path / "score.pdf", tmp_path / "score.omr"
    make_pdf(pdf)
    with zipfile.ZipFile(omr, "w") as z:
        z.writestr("sheet#1/sheet#1.xml", sheet)
    fixed = fix_symbols(omr, pdf)
    with zipfile.ZipFile(omr) as z:
        return fixed, z.read("sheet#1/sheet#1.xml").decode()


def test_missing_accidental_and_tie_are_added(tmp_path):
    fixed, sheet = run(tmp_path, SHEET.format(alter="", relation=""))
    assert fixed == (1, 1)
    assert re.search(r'<alter pitch="2" shape="SHARP" [^>]*staff="1" id="21">', sheet)
    assert re.search(r'<relation source="21" target="10">\s*<alter-head', sheet)
    assert re.search(r'<slur above="true" tie="true" [^>]*id="22">', sheet)
    assert re.search(r'<relation source="22" target="11">\s*<slur-head side="LEFT"', sheet)
    assert re.search(r'<relation source="22" target="12">\s*<slur-head side="RIGHT"', sheet)
    assert 'last-persistent-id="22"' in sheet


def test_misread_accidental_is_corrected(tmp_path):
    fixed, sheet = run(tmp_path, SHEET.format(alter=FLAT, relation=FLAT_HEAD))
    assert fixed == (1, 1)
    assert 'shape="SHARP" staff="1" id="13"' in sheet and 'shape="FLAT"' not in sheet


def system(n, staff, head_id, head_x):
    return (f'<system id="{n}"><part id="1"><staff id="{staff}" left="20" right="380"/></part><sig><inters>\n'
            f'<head pitch="0" shape="NOTEHEAD_VOID" staff="{staff}" id="{head_id}">'
            f'<bounds x="{head_x}" y="{90 + 100 * (n - 1)}" w="16" h="14"/></head>\n'
            f'</inters><relations>\n</relations></sig></system>')


def half_tie(c, height, top, end):
    """Half a tie arching downwards, top points below the top of a page height points high,
    at the end or at the start of a staff."""
    x0, x1 = (160, 189) if end else (20, 29)
    y = height - top
    p = c.beginPath()
    p.moveTo(x0, y)
    p.curveTo(x0 + 5, y - 2.5, x1 - 5, y - 2.5, x1, y)
    p.curveTo(x1 - 5, y - 1.5, x0 + 5, y - 1.5, x0, y)
    c.drawPath(p, fill=1, stroke=0)


def test_tie_across_a_page_break_is_added_in_halves(tmp_path):
    pdf, omr = tmp_path / "score.pdf", tmp_path / "score.omr"
    c = canvas.Canvas(str(pdf), pagesize=(200, 100))
    half_tie(c, 100, 48, end=True)  # from the last note of page 1
    c.showPage()
    half_tie(c, 100, 48, end=False)  # to the first note of page 2
    c.save()
    head = '<sheet last-persistent-id="20"><picture width="400" height="200"/><scale><interline main="20"/></scale><page>'
    with zipfile.ZipFile(omr, "w") as z:
        z.writestr("sheet#1/sheet#1.xml", head + system(1, 1, 10, 300) + "</page></sheet>")
        z.writestr("sheet#2/sheet#2.xml", head + system(1, 1, 10, 60) + "</page></sheet>")

    assert fix_symbols(omr, pdf) == (0, 1)
    with zipfile.ZipFile(omr) as z:
        first, second = (z.read(f"sheet#{n}/sheet#{n}.xml").decode() for n in (1, 2))
    assert re.search(r'<relation source="21" target="10">\s*<slur-head side="LEFT"', first)
    assert re.search(r'<relation source="21" target="10">\s*<slur-head side="RIGHT"', second)
    assert "extension" not in first + second  # Audiveris joins halves across pages itself


def test_tie_across_a_system_break_is_linked(tmp_path):
    pdf, omr = tmp_path / "score.pdf", tmp_path / "score.omr"
    c = canvas.Canvas(str(pdf), pagesize=(200, 200))
    half_tie(c, 200, 48, end=True)  # from the last note of the first system
    half_tie(c, 200, 98, end=False)  # to the first note of the second
    c.save()
    sheet = ('<sheet last-persistent-id="20"><picture width="400" height="400"/><scale><interline main="20"/></scale>'
             f'<page>{system(1, 1, 10, 300)}{system(2, 2, 11, 60)}</page></sheet>')
    with zipfile.ZipFile(omr, "w") as z:
        z.writestr("sheet#1/sheet#1.xml", sheet)

    assert fix_symbols(omr, pdf) == (0, 1)
    with zipfile.ZipFile(omr) as z:
        sheet = z.read("sheet#1/sheet#1.xml").decode()
    assert re.search(r'<slur [^>]*right-extension="22"[^>]*id="21"', sheet)
    assert re.search(r'<slur [^>]*left-extension="21"[^>]*id="22"', sheet)
