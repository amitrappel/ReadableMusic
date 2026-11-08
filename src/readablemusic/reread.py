"""Read a score's notes again under the clef, key and time signature the user chose.

Recognition can misread a part's clef (a handwritten treble clef as bass) or miss the key
and time signatures, and each such mistake spoils every note. The notes keep their place
on the staff: under another clef they take the pitch of that place, and under another key
their alterations are worked out again, as a musician reads them, from the printed
accidental, an accidental earlier in the measure, a tie from the note before, or the key.
"""

import re
import xml.etree.ElementTree as ET

STEPS = "CDEFGAB"
CLEFS = {  # name -> (sign, line, octave change)
    "treble": ("G", 2, 0),
    "treble-8": ("G", 2, -1),  # tenor parts
    "bass": ("F", 4, 0),
    "alto": ("C", 3, 0),
}
CLEF_PITCH = {"G": ("G", 4), "F": ("F", 3), "C": ("C", 4)}  # the pitch on the clef's line
ACCIDENTALS = {"sharp": 1, "flat": -1, "natural": 0, "double-sharp": 2, "sharp-sharp": 2,
               "flat-flat": -2, "double-flat": -2}
SHARPS = "FCGDAEB"  # the order in which key signatures add sharps; flats go the other way
ATTRIBUTE_ORDER = ["footnote", "level", "divisions", "key", "time", "staves", "part-symbol", "instruments",
                   "clef", "staff-details", "transpose", "for-part", "directive", "measure-style"]
TIME = re.compile(r"(\d{1,2})/(1|2|4|8|16|32)")


def _bottom_line(clef: tuple[str, int, int]) -> int:
    """The diatonic number (octave * 7 + step) of a clef's bottom staff line."""
    sign, line, octave_change = clef
    step, octave = CLEF_PITCH[sign]
    return octave * 7 + STEPS.index(step) - 2 * (line - 1) + 7 * octave_change


def key_alters(fifths: int) -> dict[str, int]:
    return {s: 1 for s in SHARPS[:fifths]} if fifths >= 0 else {s: -1 for s in SHARPS[::-1][:-fifths]}


def _element(tag: str, *children: tuple[str, str]) -> ET.Element:
    el = ET.Element(tag)
    for name, text in children:
        ET.SubElement(el, name).text = text
    return el


def _place(attributes: ET.Element, el: ET.Element) -> None:
    """Insert el into <attributes> where MusicXML wants it."""
    rank = ATTRIBUTE_ORDER.index(el.tag)
    k = next((k for k, c in enumerate(attributes) if c.tag in ATTRIBUTE_ORDER and ATTRIBUTE_ORDER.index(c.tag) > rank),
             len(attributes))
    attributes.insert(k, el)


def _set_alter(pitch: ET.Element, alter: int) -> None:
    el = pitch.find("alter")
    if alter == 0:
        if el is not None:
            pitch.remove(el)
        return
    if el is None:
        el = ET.Element("alter")
        pitch.insert(1, el)  # right after <step>
    el.text = str(alter)


def _move(holder: ET.Element, step_tag: str, octave_tag: str, shift: int) -> tuple[str, int] | None:
    """Move a pitch, or a rest's display position, by shift staff places."""
    step, octave = holder.find(step_tag), holder.find(octave_tag)
    if step is None or octave is None or step.text not in STEPS:
        return None
    d = int(octave.text) * 7 + STEPS.index(step.text) + shift
    step.text, octave.text = STEPS[d % 7], str(d // 7)
    return step.text, d // 7


def reread(text: str, clefs: dict[str, str], fifths: int | None, time: str | None) -> str:
    """Return the MusicXML text with the parts in clefs (part id -> a name in CLEFS) read in
    that clef throughout, and with the key (fifths) and time signature, where given, for
    the whole score. Parts with several staves keep their clefs."""
    start = re.search(r"<score-partwise\b", text)
    if not start or "<!ENTITY" in text[:start.start()]:
        raise ValueError("Not a partwise MusicXML score")
    root = ET.fromstring(text[start.start():])
    beats = TIME.fullmatch(time) if time else None
    if time and not beats:
        raise ValueError(f"Not a time signature: {time}")
    if fifths is not None and not -7 <= fifths <= 7:
        raise ValueError(f"Not a key signature: {fifths}")
    for part in root.iter("part"):
        measures = part.findall("measure")
        several = any(int(s.text or 1) > 1 for s in part.iter("staves"))
        new_clef = CLEFS[clefs[part.get("id")]] if part.get("id") in clefs and not several else None
        if measures:
            _reread_part(measures, new_clef, fifths, beats)
    return text[:start.start()] + ET.tostring(root, encoding="unicode")


def _reread_part(measures: list[ET.Element], new_clef: tuple | None, fifths: int | None, beats: re.Match | None) -> None:
    clef_now: dict[str, tuple] = {}  # staff number -> clef as read
    key_now = 0
    last_alter: dict[tuple, int] = {}  # (staff, step, octave) -> alteration of the last note there
    repitch = new_clef is not None or fifths is not None
    for m in measures:
        carry: dict[tuple, int] = {}  # accidentals earlier in the measure
        for el in list(m):
            if el.tag == "attributes":
                for c in el.findall("clef"):
                    if c.findtext("sign") in CLEF_PITCH:
                        clef_now[c.get("number", "1")] = (c.findtext("sign"), int(c.findtext("line") or 2),
                                                          int(c.findtext("clef-octave-change") or 0))
                    if new_clef:
                        el.remove(c)
                for k in el.findall("key"):
                    if k.findtext("fifths") is not None:
                        key_now = int(k.findtext("fifths"))
                    if fifths is not None:
                        el.remove(k)
                if beats:
                    for t in el.findall("time"):
                        el.remove(t)
                if not len(el):
                    m.remove(el)
            elif el.tag == "note" and repitch:
                staff = el.findtext("staff") or "1"
                old_clef = clef_now.get(staff, CLEFS["treble"])  # what renderers assume without a clef
                shift = _bottom_line(new_clef) - _bottom_line(old_clef) if new_clef else 0
                if (rest := el.find("rest")) is not None:
                    _move(rest, "display-step", "display-octave", shift)
                    continue
                pitch = el.find("pitch")
                if pitch is None or not (place := _move(pitch, "step", "octave", shift)):
                    continue
                where = (staff, *place)
                printed = ACCIDENTALS.get(el.findtext("accidental"))
                if printed is not None:
                    alter = carry[where] = printed
                elif where in carry:
                    alter = carry[where]
                elif any(t.get("type") == "stop" for t in el.findall("tie")) and where in last_alter:
                    alter = last_alter[where]
                else:
                    alter = key_alters(fifths if fifths is not None else key_now).get(place[0], 0)
                _set_alter(pitch, alter)
                last_alter[where] = alter
    first = measures[0]
    attributes = first.find("attributes")
    if attributes is None:
        attributes = ET.Element("attributes")
        first.insert(next((k for k, c in enumerate(first) if c.tag != "print"), len(first)), attributes)
    if fifths is not None:
        _place(attributes, _element("key", ("fifths", str(fifths))))
    if beats:
        _place(attributes, _element("time", ("beats", beats.group(1)), ("beat-type", beats.group(2))))
    if new_clef:
        sign, line, octave_change = new_clef
        clef = _element("clef", ("sign", sign), ("line", str(line)))
        if octave_change:
            ET.SubElement(clef, "clef-octave-change").text = str(octave_change)
        _place(attributes, clef)
