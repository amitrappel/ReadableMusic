import xml.etree.ElementTree as ET

import pytest

from readablemusic.staves import TENOR, TREBLE, BASS, Voice, groups, restaff

HEAD = '<?xml version="1.0" encoding="utf-8"?>\n'


def note(step, octave, length=1, voice=1, chord=False, words=None, hidden=False):
    attrs = ' print-object="no"' if hidden else ""
    what = "<rest/>" if hidden else f"<pitch><step>{step}</step><octave>{octave}</octave></pitch>"
    lyric = f'<lyric number="1"><syllabic>single</syllabic><text>{words}</text></lyric>' if words else ""
    kind = {1: "quarter", 2: "half", 4: "whole"}[length]
    return (f"<note{attrs}>{'<chord/>' if chord else ''}{what}<duration>{length}</duration><voice>{voice}</voice>"
            f"<type>{kind}</type>{lyric}</note>")


def attributes(sign, line):
    return (f"<attributes><divisions>1</divisions><key><fifths>0</fifths></key><time><beats>4</beats>"
            f"<beat-type>4</beat-type></time><clef><sign>{sign}</sign><line>{line}</line></clef></attributes>")


# SATB on two staves. The sopranos and altos sing "la" on one stem, "di" in unison, and the
# altos go their own way under "da"; the tenors and basses hold an octave, without words.
SCORE = HEAD + f"""<score-partwise version="4.0"><part-list>
<score-part id="P1"><part-name>Soprano, Alto</part-name><part-abbreviation>S A</part-abbreviation></score-part>
<score-part id="P2"><part-name>Tenor, Bass</part-name><part-abbreviation>T B</part-abbreviation></score-part>
</part-list>
<part id="P1"><measure number="1">{attributes("G", 2)}
<direction placement="above"><direction-type><words>Kanon</words></direction-type></direction>
{note("C", 5, words="la")}{note("A", 4, chord=True)}{note("G", 4, words="di")}{note("B", 4, 2, words="da")}
<backup><duration>4</duration></backup>
{note("", 0, voice=2, hidden=True)}{note("", 0, voice=2, hidden=True)}{note("E", 4, voice=2)}{note("F", 4, voice=2)}
</measure></part>
<part id="P2"><measure number="1">{attributes("F", 4)}{note("C", 4, 4)}{note("C", 3, 4, chord=True)}</measure></part>
</score-partwise>"""


def parts(xml):
    root = ET.fromstring(xml[xml.index("<score-partwise"):])
    names = [sp.findtext("part-name") for sp in root.iter("score-part")]
    return root, names, root.findall("part")


def sung(part, voice=None):
    return [(n.findtext("pitch/step") + n.findtext("pitch/octave"), n.findtext("lyric/text"))
            for n in part.iter("note") if n.find("pitch") is not None and (voice is None or n.findtext("voice") == voice)]


def test_shared_staves_are_spread_one_voice_a_staff():
    root, names, (s, a, t, b) = parts(restaff(SCORE, 4))
    assert names == ["Soprano", "Alto", "Tenor", "Bass"]
    assert sung(s) == [("C5", "la"), ("G4", "di"), ("B4", "da")]
    # The altos sing their own notes to the words sung above them at the same time.
    assert sung(a) == [("A4", "la"), ("G4", "di"), ("E4", "da"), ("F4", None)]
    # Alone, the tenors read the treble clef an octave down, and sing the words of the staff above.
    assert t.findtext("measure/attributes/clef/clef-octave-change") == "-1"
    assert sung(t) == [("C4", "la")] and sung(b) == [("C3", "la")]
    assert b.findtext("measure/attributes/clef/sign") == "F"
    assert s.find(".//words").text == "Kanon" and a.find(".//words") is None
    assert not any(n.get("print-object") for n in a.iter("note"))


def test_voices_are_gathered_two_a_staff_with_stems_up_and_down():
    root, names, (upper, lower) = parts(restaff(restaff(SCORE, 4), 2))
    assert names == ["Soprano, Alto", "Tenor, Bass"]
    assert [x for x, _ in sung(upper, "1")] == ["C5", "G4", "B4"]
    assert [x for x, _ in sung(upper, "2")] == ["A4", "G4", "E4", "F4"]
    stems = {(n.findtext("voice"), n.findtext("stem")) for n in upper.iter("note") if n.find("pitch") is not None}
    assert stems == {("1", "up"), ("2", "down")}
    # The words both sing are printed once.
    assert [w for _, w in sung(upper, "2")] == [None] * 4
    assert lower.findtext("measure/attributes/clef/sign") == "F"


def test_three_staves_keep_the_tenors_and_basses_together():
    root, names, staves = parts(restaff(SCORE, 3))
    assert names == ["Soprano", "Alto", "Tenor, Bass"]
    assert sung(staves[2]) == [("C4", None), ("C3", None)]  # the part as it was
    assert restaff(SCORE, 2).count("<note") == SCORE.count("<note")


def test_neighbours_in_one_clef_share_a_staff_first():
    def voice(clef):
        return Voice("", "", None, None, clef)
    satb = [voice(TREBLE), voice(TREBLE), voice(TENOR), voice(BASS)]
    assert groups(satb, 2) == [[0, 1], [2, 3]]
    assert groups(satb, 3) == [[0], [1], [2, 3]]
    assert groups(satb[:2] + satb[3:], 2) == [[0, 1], [2]]  # S A | B
    with pytest.raises(ValueError):
        groups(satb, 1)
