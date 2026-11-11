import xml.etree.ElementTree as ET

from PIL import Image

from readablemusic.vision import Reading, ask, correct, corrections, system_start


def staff(id, left, top, stop):
    lines = "".join(f'<line><point x="{left}" y="{top + 20 * k}"/><point x="2000" y="{top + 20 * k}"/></line>'
                    for k in range(5))
    return f'<staff id="{id}" left="{left}" right="2000"><lines>{lines}</lines><header start="{left}" stop="{stop}"/></staff>'


SHEET = f"""<sheet><picture width="2400" height="3000"/><scale><interline main="20"/></scale>
<page><system id="1"><part id="1">{staff(1, 300, 500, 420)}{staff(2, 300, 700, 700)}</part></system>
<system id="2"><part id="1">{staff(3, 100, 1500, 900)}</part></system></page></sheet>"""


def test_the_start_of_the_first_system_is_cropped_wide_enough_for_a_key():
    width, box = system_start(SHEET)
    # From the page edge; past the longest header, or 14 interlines when a key was missed.
    assert width == 2400 and box == (0, 500 - 100, 700 + 40, 780 + 100)
    assert system_start("<sheet><picture width='1' height='1'/></sheet>") is None


def score(*parts, key=None, times=("4/4",)):
    def measure(n, clef):
        key_el = f"<key><fifths>{key}</fifths></key>" if key is not None and n == 1 else ""
        time_el = "".join(f"<time><beats>{t.split('/')[0]}</beats><beat-type>{t.split('/')[1]}</beat-type></time>"
                          for t in times[n - 1:n])
        sign, line, octave = clef
        clef_el = (f"<clef><sign>{sign}</sign><line>{line}</line>"
                   + (f"<clef-octave-change>{octave}</clef-octave-change>" if octave else "") + "</clef>") if n == 1 else ""
        return (f'<measure number="{n}"><attributes><divisions>1</divisions>{key_el}{time_el}{clef_el}</attributes>'
                f"<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note></measure>")
    body = "".join(f'<part id="P{k}">{measure(1, c)}{measure(2, c)}</part>' for k, c in enumerate(parts, 1))
    names = "".join(f'<score-part id="P{k}"><part-name>V</part-name></score-part>' for k in range(1, len(parts) + 1))
    return f'<?xml version="1.0"?>\n<score-partwise version="4.0"><part-list>{names}</part-list>{body}</score-partwise>'


TREBLE, TENOR, BASS = ("G", 2, 0), ("G", 2, -1), ("F", 4, 0)


def test_differences_are_corrected():
    xml = score(TREBLE, TREBLE, BASS, key=0)
    seen = Reading(["treble", "treble-8", "bass", "other"], -3, "3/8", {})
    # The percussion staff at the bottom is dropped from the score, so it is left out.
    assert corrections(xml, seen) == ({"P2": "treble-8"}, -3, "3/8")
    assert corrections(xml, Reading(["treble", "treble", "bass"], 0, "4/4", {})) == ({}, None, None)


def test_doubtful_readings_change_nothing():
    xml = score(TREBLE, BASS, key=2, times=("4/4", "3/4")).replace(
        '<measure number="2"><attributes><divisions>1</divisions>',
        '<measure number="2"><attributes><divisions>1</divisions><key><fifths>-1</fifths></key>', 1)
    # Staves that do not match one for one, a key or time the score changes later, no time printed.
    assert corrections(xml, Reading(["bass"], 2, "", {})) == ({}, None, None)
    assert corrections(xml, Reading(["treble", "bass"], 3, "2/2", {})) == ({}, None, None)


def test_on_a_scan_a_key_that_one_part_changes_is_claudes():
    # האדון הרופא: Audiveris missed the tenor's flats on its second system.
    second = '<measure number="2"><attributes><divisions>1</divisions>'
    changed = second + "<key><fifths>0</fifths></key>"
    xml = score(TREBLE, TENOR, key=-4)
    at = xml.index('<part id="P2">')
    one = xml[:at] + xml[at:].replace(second, changed)
    seen = Reading(["treble", "treble-8"], -4, "4/4", {})
    assert corrections(one, seen)[1] is None
    assert corrections(one, seen, scan=True)[1] == -4
    # A key that every part changes at once is printed.
    assert corrections(xml.replace(second, changed), seen, scan=True)[1] is None


def test_the_score_is_read_again(tmp_path):
    path = tmp_path / "score.musicxml"
    path.write_text(score(BASS, key=0), encoding="utf-8")
    assert correct(path, Reading(["treble"], -3, "3/8", {})) == "part P1 in treble, key -3, time 3/8"
    root = ET.fromstring(path.read_text(encoding="utf-8").split("\n", 1)[1])
    assert root.findtext(".//clef/sign") == "G" and root.findtext(".//key/fifths") == "-3"
    assert root.findtext(".//pitch/step") == "A" and root.findtext(".//pitch/octave") == "5"  # C4 in bass -> A5...
    assert correct(path, Reading(["treble"], -3, "3/8", {})) == ""


def test_nothing_is_sent_without_a_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ask(Image.new("L", (10, 10)), tmp_path / "missing.omr") is None


def test_on_a_scan_each_system_takes_the_clefs_of_the_first():
    # Audiveris read the tenor's treble 8 as a C clef on the second system, and the top staff
    # of the second system as a part of its own, which it puts first (P1), with an 8 above.
    def measure(n, clef, shown, system):
        sign, line, octave = clef
        clef_el = (f"<clef><sign>{sign}</sign><line>{line}</line>"
                   + (f"<clef-octave-change>{octave}</clef-octave-change>" if octave else "") + "</clef>")
        mark = '<print new-system="yes"/>' if system else "<print/>"
        details = f'<staff-details print-object="{"yes" if shown else "no"}"/>'
        return (f'<measure number="{n}">{mark}<attributes><divisions>1</divisions>{clef_el}{details}</attributes>'
                f"<note><pitch><step>E</step><octave>5</octave></pitch><duration>4</duration></note></measure>")
    parts = {"P1": [(("G", 2, 1), False), (("G", 2, 1), True)],
             "P2": [(("G", 2, 0), True), (("G", 2, 0), False)],
             "P3": [(("G", 2, -1), True), (("C", 3, 0), True)]}
    body = "".join(f'<part id="{p}">' + "".join(measure(n, c, s, n > 1) for n, (c, s) in enumerate(ms, 1)) + "</part>"
                   for p, ms in parts.items())
    names = "".join(f'<score-part id="{p}"><part-name>V</part-name></score-part>' for p in parts)
    xml = f'<score-partwise version="4.0"><part-list>{names}</part-list>{body}</score-partwise>'
    reading = Reading(["treble", "treble-8"], 0, "4/4", {})
    assert corrections(xml, reading)[0] == {}  # the first measure has three parts for two staves
    # P1 is the top staff where it is shown, P3 the tenor's in both systems.
    assert corrections(xml, reading, scan=True)[0] == {"P1": "treble", "P3": "treble-8"}
