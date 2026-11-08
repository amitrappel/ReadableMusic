import xml.etree.ElementTree as ET

import pytest

from readablemusic.reread import key_alters, reread

HEAD = ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 '
        'Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n')


def note(step, octave, accidental=None, tie=None):
    t = f'<tie type="{tie}"/>' if tie else ""
    acc = f"<accidental>{accidental}</accidental>" if accidental else ""
    return f"<note><pitch><step>{step}</step><octave>{octave}</octave></pitch><duration>1</duration>{t}{acc}</note>"


# A part read in the bass clef with no key, which is a treble part in three flats.
SCORE = HEAD + f"""<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list>
<part id="P1">
<measure number="1"><attributes><divisions>1</divisions><clef><sign>F</sign><line>4</line></clef></attributes>
{note("D", 3)}{note("D", 3, accidental="natural")}{note("D", 3)}
<note><rest><display-step>D</display-step><display-octave>3</display-octave></rest><duration>1</duration></note>
{note("A", 2, accidental="sharp", tie="start")}</measure>
<measure number="2">{note("A", 2, tie="stop")}{note("A", 2)}{note("D", 3)}{note("G", 2)}</measure>
<measure number="3"><attributes><clef><sign>G</sign><line>2</line><clef-octave-change>1</clef-octave-change></clef></attributes>
{note("B", 5)}</measure>
</part></score-partwise>"""


def parse(xml):
    return ET.fromstring(xml[xml.index("<score-partwise"):])


def pitches(xml):
    return [p.findtext("step") + {"-1": "b", "1": "#"}.get(p.findtext("alter"), "") + p.findtext("octave")
            for p in parse(xml).iter("pitch")]


def test_key_alters():
    assert key_alters(-3) == {"B": -1, "E": -1, "A": -1}
    assert key_alters(2) == {"F": 1, "C": 1}


def test_clef_and_key_are_reread_as_a_musician_would():
    out = reread(SCORE, {"P1": "treble"}, -3, "3/8")
    assert out.startswith(HEAD)
    # D3 on the middle line of a bass staff is B4 in treble. The natural holds to the end
    # of the measure, the tie carries the sharp over the barline, the key does the rest;
    # measure 3's clef, misread an octave high, is read as treble too.
    assert pitches(out) == ["Bb4", "B4", "B4", "F#4", "F#4", "F4", "Bb4", "Eb4", "Bb4"]
    root = parse(out)
    first = root.find("part/measure/attributes")
    assert [c.tag for c in first] == ["divisions", "key", "time", "clef"]
    assert first.findtext("key/fifths") == "-3" and first.findtext("time/beat-type") == "8"
    assert len(root.findall(".//clef")) == 1 and root.find("part/measure[3]/attributes") is None
    assert root.find(".//rest/display-step").text == "B"


def test_key_alone_keeps_the_clefs():
    out = reread(SCORE, {}, 1, None)
    assert pitches(out) == ["D3", "D3", "D3", "A#2", "A#2", "A2", "D3", "G2", "B5"]
    assert parse(out).findtext("part/measure/attributes/key/fifths") == "1"
    assert out.count("<clef>") == 2 and "<time>" not in out


def test_bad_choices_are_refused():
    with pytest.raises(ValueError):
        reread(SCORE, {}, None, "3/7")
    with pytest.raises(ValueError):
        reread(SCORE, {}, 9, None)
    with pytest.raises(ValueError):
        reread('<!DOCTYPE x [<!ENTITY a "aaaa">]><score-partwise/>', {}, None, None)
