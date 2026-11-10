"""Let Claude read each system of a scan again, with Audiveris's reading as a draft.

On a poor scan Audiveris puts notes a step off and misses ties, dots, flags and triplets,
and its OCR misreads lyrics and takes marks and footnotes for them (Siyahamba, a 118 DPI
scan). Claude gets each system cut from the page and Audiveris's reading of it as text, one
line per voice, with the syllables sung on each event:

    G4+B4 2~ [hamb'|march-], G4+B4 8, F#4+A4 8. [e-|ing], r 4t, s 4

(sounding pitches joined by +, r a rest, s an invisible space; duration 1 2 4 8 16 32, a
dot each, t in a triplet, ~ tied to the next; a slot for each line of words under the
staff), and writes the system out again in the same form. It also lists the chord symbols,
the other words printed in the music, the first and second endings and the repeat signs.
A measure whose voices all add up replaces Audiveris's, lyrics and words included. On a
staff that two parts share, a lone note among chords is one both sing, and gets the second
voice's stem down as on the page (Claude cannot see on a poor scan which notes have it). Measured on two chorales
with known answers: 98.3% of notes right -> 100% at 118 DPI, 61% -> 64% on a degraded scan,
where a barline Audiveris missed shifts every later measure (the measures are Audiveris's).

Each system is turned level first. Claude also marks fermatas and slurs. Its reading is
then checked against Audiveris's:
- a measure that adds up to two bars is split (a barline missed);
- a voice that does not add up to the time signature is shown to Claude for a second look;
- a lone note a step from Audiveris's lone note on the staff takes Audiveris's pitch, which
  measures heads against the lines that Claude judges by eye (אתה הצבת).

About 7 cents a system; runs only with ANTHROPIC_API_KEY. Any failure keeps Audiveris's reading.
"""

import base64
import io
import json
import math
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction
from math import lcm
from pathlib import Path
from typing import Callable

import music21 as m21
from PIL import Image

from .chords import Chord
from .reread import key_alters

MODEL = "claude-opus-5-5"
MAX_EDGE, MAX_AREA = 2576, 3_700_000  # the largest image the model sees in full detail
MAX_ZOOM = 2.0  # a small system is enlarged at most this much
MIN_TURN = 0.05  # degrees of slope below which a system is not turned level
ABOVE, BELOW, LEFT, RIGHT = 7, 6, 4, 2  # interlines of page kept around a system's staves
DIVISIONS = 24  # per quarter at least, so that triplets of 32nds fit
TYPES = {1: "whole", 2: "half", 4: "quarter", 8: "eighth", 16: "16th", 32: "32nd"}
DENOMINATOR = {name: den for den, name in TYPES.items()}
PITCH = r"[A-G](?:##|#|bb|b)?\d"
EVENT = re.compile(rf"(r|s|{PITCH}(?:\+{PITCH})*) (16|32|1|2|4|8)([.t~^()]*)(?: ?\[([^\]]*)\])?")
SEPARATOR = re.compile(r"\s*(?:,\s*|$)")
ALTER = {"": 0, "#": 1, "##": 2, "b": -1, "bb": -2}
ACCIDENTAL = {0: "natural", 1: "sharp", 2: "double-sharp", -1: "flat", -2: "flat-flat"}
MOVABLE = ("direction", "harmony", "sound")  # placed by their onset among the notes
DUET_CHORDS = 0.3  # share of a staff's notes on one stem in chords from which two parts share it
TEXT = ("words", "dynamics")  # the directions that Claude's reading replaces
UNMARKED = {"fermata": False, "slurs": (0, 0)}  # the marks of an event that another voice prints
UNITS = {1: "wholes", 2: "halves", 4: "quarters", 8: "eighths", 16: "sixteenths", 32: "32nds"}
DYNAMICS = re.compile(r"p{1,4}|f{1,4}|mp|mf|sf|sfz|sfp|fp|fz|rfz")

PROMPT = """The image shows one system of an a cappella choir score. Below is an optical
music recognition draft of it, which has mistakes: notes a step off, missed ties, dots,
flags, triplets, notes missed or invented, and lyrics misread, missed or made up from
other text. Read the image carefully and write out the whole system again, correcting the
draft.

Format, one string per voice: events separated by ", ". An event is pitches, a duration and
the syllables sung on it:
- pitches: sounding pitches with the key signature and accidentals applied, e.g. "F#4",
  "Bb3" (an accidental holds for later notes on its line or space to the end of the
  measure); notes sharing one stem are joined by "+" ("G4+B4"); "r" is a rest; "s" is an
  invisible space where a voice prints nothing. A note with a short line of its own through
  it is on that ledger line (C4 is the first below a treble staff), even where the hand
  drew it close to the staff.
- duration: 1 whole, 2 half, 4 quarter, 8 eighth, 16 sixteenth, 32; then "." for each dot,
  "t" if the note is in a triplet (three in the time of two), "~" if it is tied to the next
  note of the same voice (also across the barline, and at the end of the system), "^" if
  it has a fermata, ")" if a slur ends on it and "(" if one starts on it. A slur is a curve
  over or under notes of other pitches; one that runs off the end of the system starts
  with "(" there, and ends with ")" where the short curve at the start of the next ends.
- syllables: in brackets, one slot for each line of words printed under the staff, top
  line first, separated by "|": "D4 8 [Si-|We]", or "E4 4 [|kha-]" for a syllable on the
  second line only. Copy each syllable letter by letter, accents included ("híz", "jéw").
  End a syllable with "-" when its word goes on to the next syllable; leave out verse
  numbers. Leave out the brackets where no syllable starts.
Example: "G4+B4 2~( [hamb'|march-], G4+B4 8), F#4+A4 8.^ [e-|ing], r 4t, D4 4t, D4 4t~"

Look at every stem. A staff has one voice, or two where its parts are drawn apart: then
voice 1 has the stems up and voice 2 the stems down, with "s" where a voice prints nothing.
Every voice of a measure must add up to the same length (the time signature; the first
measure may be a shorter pickup). Keep the draft's measures and staves; where a measure
of the draft holds two on the page (it missed a barline), write both into it. Put each
syllable on the voice whose notes it is printed under, on voice 1 when both voices sing it.

Also list:
- every chord symbol printed above the staves ("G", "D7", "Bbm7/Ab"), as printed;
- every other word or mark printed in the music, as printed: dynamics ("p", "mf"), tempo
  and expression ("Slowly", "rit."), instructions ("Last time, end"), with the staff it
  belongs to and whether it is above or below that staff, and circled numbers as "①".
  A fermata printed among words, as in "(Finis 𝄐)", stands over a note of the staff below
  the words: put "^" on that note, and write the words without it ("(Finis)"). Leave out titles, credits, part
  names, page and measure numbers, footnotes, and text of the systems above and below,
  which the edges of the image may show;
- the first and second endings, brackets over measures with a number ("1.", "2."): the
  number as printed, the first and last measure under the bracket in this system, and
  whether the bracket ends with a hook down;
- the repeat signs, barlines with two dots: the measure, and whether it starts a repeated
  passage (dots after the barline) or ends one (dots before it).
Give each position as the measure and the quarter notes from its start (0 at the start,
1.5 halfway through the second quarter).

Draft:
"""

AGAIN = """Look again at these measures, at the flags, beams, dots and rests of their notes,
and write out the whole system again:
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "measures": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "number": {"type": "string"},
                "staves": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"staff": {"type": "integer"},
                                   "voices": {"type": "array", "items": {"type": "string"}}},
                    "required": ["staff", "voices"], "additionalProperties": False}},
            },
            "required": ["number", "staves"], "additionalProperties": False}},
        "chords": {"type": "array", "items": {
            "type": "object",
            "properties": {"measure": {"type": "string"}, "quarters": {"type": "number"},
                           "symbol": {"type": "string"}},
            "required": ["measure", "quarters", "symbol"], "additionalProperties": False}},
        "texts": {"type": "array", "items": {
            "type": "object",
            "properties": {"measure": {"type": "string"}, "quarters": {"type": "number"},
                           "staff": {"type": "integer"}, "above": {"type": "boolean"}, "text": {"type": "string"}},
            "required": ["measure", "quarters", "staff", "above", "text"], "additionalProperties": False}},
        "endings": {"type": "array", "items": {
            "type": "object",
            "properties": {"number": {"type": "string"}, "first": {"type": "string"}, "last": {"type": "string"},
                           "hook": {"type": "boolean"}},
            "required": ["number", "first", "last", "hook"], "additionalProperties": False}},
        "repeats": {"type": "array", "items": {
            "type": "object",
            "properties": {"measure": {"type": "string"}, "starts": {"type": "boolean"}},
            "required": ["measure", "starts"], "additionalProperties": False}},
    },
    "required": ["measures", "chords", "texts", "endings", "repeats"], "additionalProperties": False,
}


# Audiveris's reading as text

def _pitch(note: ET.Element) -> str:
    p = note.find("pitch")
    alter = int(float(p.findtext("alter") or 0))
    return p.findtext("step") + {0: "", 1: "#", 2: "##", -1: "b", -2: "bb"}.get(alter, "") + p.findtext("octave")


def _length(note: ET.Element, divisions: int) -> str:
    if (kind := note.findtext("type")) in DENOMINATOR:
        den = DENOMINATOR[kind]
    else:
        q = Fraction(int(note.findtext("duration") or 0), divisions)
        den = next((d for d in TYPES if q >= Fraction(4, d)), 32)
    text = str(den) + "." * len(note.findall("dot"))
    modification = note.find("time-modification")
    if modification is not None and (modification.findtext("actual-notes"), modification.findtext("normal-notes")) == ("3", "2"):
        text += "t"
    return text + ("~" if any(t.get("type") == "start" for t in note.findall("tie")) else "")


def _spaces(duration: int, divisions: int) -> list[str]:
    out, left = [], Fraction(duration, divisions)
    for den in TYPES:
        while left >= Fraction(4, den):
            out.append(f"s {den}")
            left -= Fraction(4, den)
    return out


def _syllables(note: ET.Element) -> str:
    """' [Si-|We]' for a note with lyrics on lines 1 and 2, '' for one without."""
    lines = {}
    for lyric in note.findall("lyric"):
        text = "".join(t.text or "" for t in lyric.findall("text")).strip()
        if text and (lyric.get("number") or "1").isdigit():
            lines[int(lyric.get("number") or 1)] = text + ("-" if lyric.findtext("syllabic") in ("begin", "middle") else "")
    return f" [{'|'.join(lines.get(n, '') for n in range(1, max(lines) + 1))}]" if lines else ""


def voices_of(measure: ET.Element, divisions: int, syllables: bool = False) -> dict[str, list[str]]:
    """Voice -> events of a one-staff measure; a forward belongs to the voice after it."""
    voices: dict[str, list[str]] = {}
    pending = 0
    for el in measure:
        if el.tag == "forward":
            pending += int(el.findtext("duration") or 0)
        if el.tag != "note" or el.find("grace") is not None:
            continue
        v = el.findtext("voice") or "1"
        if el.find("chord") is not None and voices.get(v) and el.find("pitch") is not None:
            voices[v][-1] = voices[v][-1].replace(" ", f"+{_pitch(el)} ", 1)
            continue
        if pending:
            voices.setdefault(v, []).extend(_spaces(pending, divisions))
            pending = 0
        what = ("s" if el.get("print-object") == "no" else "r") if el.find("rest") is not None else _pitch(el)
        voices.setdefault(v, []).append(f"{what} {_length(el, divisions)}" + (_syllables(el) if syllables else ""))
    return voices


def _running(part: ET.Element, tag: str, default: int) -> list[int]:
    """The value of an attribute (divisions, key fifths) in force in each measure."""
    out, value = [], default
    for m in part.findall("measure"):
        if (text := m.findtext(f"attributes/{tag}")) is not None:
            value = int(text)
        out.append(value)
    return out


def systems_of(root: ET.Element) -> list[list[int]]:
    """Measure indices of each system, from Audiveris's new-system and new-page marks."""
    systems: list[list[int]] = []
    for k, m in enumerate(root.find("part").findall("measure")):
        mark = m.find("print")
        if not systems or (mark is not None and "yes" in (mark.get("new-system"), mark.get("new-page"))):
            systems.append([])
        systems[-1].append(k)
    return systems


def draft(parts: list[ET.Element], measures: list[int]) -> str:
    lines = []
    for k in measures:
        lines.append(f"Measure {parts[0].findall('measure')[k].get('number')}:")
        for s, part in enumerate(parts, 1):
            voices = voices_of(part.findall("measure")[k], _running(part, "divisions", 1)[k], syllables=True)
            lines += [f"  staff {s} voice {v}: {', '.join(events)}" for v, events in voices.items()]
            if not voices:
                lines.append(f"  staff {s}: (empty)")
    return "\n".join(lines)


# The systems on the page

def page_systems(omr: Path) -> list[tuple[int, int, tuple[int, int, int, int], float]]:
    """(sheet, picture width, box around the staves, slope of the staff lines) of every
    system, in order."""
    out = []
    with zipfile.ZipFile(omr) as z:
        sheets = sorted((n for n in z.namelist() if re.fullmatch(r"sheet#\d+/sheet#\d+\.xml", n)),
                        key=lambda n: int(re.search(r"#(\d+)", n).group(1)))
        for n, name in enumerate(sheets):
            xml = z.read(name).decode("utf-8")
            width, height = map(int, re.search(r'<picture width="(\d+)" height="(\d+)"', xml).groups())
            d = int(re.search(r'<interline [^>]*main="(\d+)"', xml).group(1))
            for system in re.findall(r"<system .*?</system>", xml, re.S):
                lines = "".join(re.findall(r"<lines>.*?</lines>", system, re.S))
                ys = [float(y) for y in re.findall(r'y="(\d+(?:\.\d+)?)"', lines)]
                ends = [(int(a), int(b)) for a, b in re.findall(r'<staff id="\d+" left="(\d+)" right="(\d+)"', system)]
                slopes = []
                for line in re.findall(r"<line\b.*?</line>", lines, re.S):
                    (x1, y1), *_, (x2, y2) = [tuple(map(float, p)) for p in
                                              re.findall(r'<point x="([\d.]+)" y="([\d.]+)"', line)]
                    slopes.append((y2 - y1) / (x2 - x1) if x2 > x1 else 0.0)
                out.append((n, width, (max(0, min(a for a, _ in ends) - LEFT * d), max(0, int(min(ys) - ABOVE * d)),
                                       min(width, max(b for _, b in ends) + RIGHT * d),
                                       min(height, int(max(ys) + BELOW * d))),
                            sum(slopes) / len(slopes) if slopes else 0.0))
    return out


def level(img: Image.Image, slope: float) -> Image.Image:
    """The system turned so that its staff lines are level. Claude places notes against
    level lines: on a page turned by one degree it read the notes at the right end of a
    system a step too high (אתה הצבת)."""
    angle = math.degrees(math.atan(slope))
    return img.rotate(angle, Image.BICUBIC, fillcolor="white") if abs(angle) > MIN_TURN else img


def _image(img: Image.Image) -> dict:
    k = min(MAX_ZOOM, MAX_EDGE / max(img.size), (MAX_AREA / (img.width * img.height)) ** 0.5)
    buf = io.BytesIO()
    img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS).save(buf, "PNG")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                        "data": base64.standard_b64encode(buf.getvalue()).decode()}}


# Claude's reading written back

def parse_event(text: str, divisions: int) -> dict:
    m = EVENT.fullmatch(text.strip())
    if not m:
        raise ValueError(f"not an event: {text!r}")
    what, den, marks, words = m.groups()
    dots, triplet = marks.count("."), "t" in marks
    if dots > 2:
        raise ValueError(f"{text!r} has {dots} dots")
    nominal = Fraction(4, int(den)) * (2 - Fraction(1, 2 ** dots))
    duration = nominal * (Fraction(2, 3) if triplet else 1) * divisions
    if duration.denominator != 1:
        raise ValueError(f"{text!r} does not fit {divisions} divisions")
    rest = what in ("r", "s")
    return {"rest": rest, "hidden": what == "s", "pitches": [] if rest else what.split("+"),
            "type": TYPES[int(den)], "dots": dots, "triplet": triplet, "tie": "~" in marks,
            "fermata": "^" in marks, "slurs": (marks.count("("), marks.count(")")),
            "duration": int(duration), "nominal": nominal,
            "lyrics": {} if rest else {n: s.strip() for n, s in enumerate((words or "").split("|"), 1) if s.strip()}}


def shared(events: list[dict]) -> list[list[dict]]:
    """The two voices of a measure that two parts sing on one staff, written as one voice.
    A lone note is sung by both and drawn with a stem up and a stem down, so the second
    voice has it too, and an invisible space where the first has a chord or a rest."""
    if not any(len(ev["pitches"]) == 1 for ev in events):
        return [events]
    second = []
    for k, ev in enumerate(events):
        if len(ev["pitches"]) == 1:
            after = events[k + 1]["pitches"] if k + 1 < len(events) else []
            second.append({**ev, "tie": ev["tie"] and after == ev["pitches"], "lyrics": {}, **UNMARKED})
        else:
            second.append({**ev, "rest": True, "hidden": True, "pitches": [], "tie": False, "lyrics": {}, **UNMARKED})
    return [events, second]


def parse_voice(text: str, divisions: int) -> list[dict]:
    """The events of a voice; a comma between the brackets of syllables parts nothing."""
    events, at = [], len(text) - len(text.lstrip())
    while at < len(text):
        m = EVENT.match(text, at)
        after = SEPARATOR.match(text, m.end()) if m else None
        if not after:
            raise ValueError(f"not an event: {text[at:at + 40]!r}")
        events.append(parse_event(m.group(0), divisions))
        at = after.end()
    return events


def _note(ev: dict, voice: int, pitch: str | None, chord: bool, tie_stop: bool, tie_start: bool,
          accidental: int | None) -> ET.Element:
    """A note of an event; the first of its notes carries the event's fermata and slurs,
    which apply() numbers."""
    n = ET.Element("note", {"print-object": "no"} if ev["hidden"] else {})
    if chord:
        ET.SubElement(n, "chord")
    if pitch:
        step, alter, octave = re.fullmatch(r"([A-G])(##|#|bb|b)?(\d)", pitch).groups()
        p = ET.SubElement(n, "pitch")
        ET.SubElement(p, "step").text = step
        if ALTER[alter or ""]:
            ET.SubElement(p, "alter").text = str(ALTER[alter or ""])
        ET.SubElement(p, "octave").text = octave
    else:
        ET.SubElement(n, "rest")
    ET.SubElement(n, "duration").text = str(ev["duration"])
    ties = (["stop"] if tie_stop else []) + (["start"] if tie_start else [])
    for kind in ties:
        ET.SubElement(n, "tie", type=kind)
    ET.SubElement(n, "voice").text = str(voice)
    ET.SubElement(n, "type").text = ev["type"]
    for _ in range(ev["dots"]):
        ET.SubElement(n, "dot")
    if accidental is not None:
        ET.SubElement(n, "accidental").text = ACCIDENTAL[accidental]
    if ev["triplet"]:
        modification = ET.SubElement(n, "time-modification")
        ET.SubElement(modification, "actual-notes").text = "3"
        ET.SubElement(modification, "normal-notes").text = "2"
    starts, stops = (0, 0) if chord else ev.get("slurs", (0, 0))
    fermata = ev.get("fermata") and not chord
    if ties or starts or stops or fermata:
        notations = ET.SubElement(n, "notations")
        for kind in ties:
            ET.SubElement(notations, "tied", type=kind)
        for kind in ["stop"] * stops + ["start"] * starts:
            ET.SubElement(notations, "slur", type=kind)
        if fermata:
            ET.SubElement(notations, "fermata", type="upright")
    return n


def _printed(voices: list[list[dict]], tied_in: dict[int, set], fifths: int) -> set[tuple[int, int, str]]:
    """(voice, event, pitch) of the notes that need a printed accidental: the key and the
    notes before them in the measure do not give their alteration."""
    key = key_alters(fifths)
    notes = []  # (onset, voice, event, pitch, tied from the note before)
    for v, events in enumerate(voices, 1):
        t, tied = 0, tied_in.get(v, set())
        for k, ev in enumerate(events):
            notes += [(t, v, k, p, p in tied) for p in ev["pitches"]]
            tied = set(ev["pitches"]) if ev["tie"] else set()
            t += ev["duration"]
    state, out = {}, set()
    for t, v, k, pitch, tied in sorted(notes):
        step, alter, octave = re.fullmatch(r"([A-G])(##|#|bb|b)?(\d)", pitch).groups()
        place, alter = (step, octave), ALTER[alter or ""]
        if not tied and alter != state.get(place, key.get(step, 0)):
            out.add((v, k, pitch))
        state[place] = alter
    return out


def _voice(events: list[dict], voice: int, tied_in: set, printed: set) -> tuple[list, list, list]:
    """One voice's (onset, note)s with its triplets bracketed and its ties; the (onset,
    event, first note) of its sounding events; and its triplets as (onset, end, the tuplet
    element that starts the bracket, whether every event in it is an invisible space)."""
    out, firsts, triplets, t, group = [], [], [], 0, []
    for k, ev in enumerate(events):
        # A tie goes on to the same pitch in the voice's next note, or over the barline.
        tied = {p for p in ev["pitches"] if ev["tie"] and (k + 1 == len(events) or p in events[k + 1]["pitches"])}
        notes = [_note(ev, voice, p, j > 0, p in tied_in, p in tied,
                       ALTER[re.fullmatch(r"[A-G](##|#|bb|b)?\d", p).group(1) or ""] if (voice, k, p) in printed else None)
                 for j, p in enumerate(ev["pitches"] or [None])]
        tied_in = tied
        if ev["pitches"]:
            firsts.append((t, ev, notes[0]))
        if ev["triplet"]:
            group.append((ev["nominal"], notes[0], t, ev["hidden"]))
            if sum(g[0] for g in group) == 3 * min(g[0] for g in group):
                brackets = []
                for (_, first, _, _), kind in ((group[0], "start"), (group[-1], "stop")):
                    notations = first.find("notations")
                    if notations is None:
                        notations = ET.SubElement(first, "notations")
                    brackets.append(ET.SubElement(notations, "tuplet", type=kind))
                triplets.append((group[0][2], t + ev["duration"], brackets[0], all(g[3] for g in group)))
                group = []
        out += [(t, n) for n in notes]
        t += ev["duration"]
    return out, firsts, triplets


def _onsets(measure: ET.Element) -> list[tuple[int, ET.Element]]:
    """(onset, element) of the measure's contents; chord notes share their first note's onset."""
    out, t, last = [], 0, 0
    for el in measure:
        if el.tag == "backup":
            t -= int(el.findtext("duration"))
        elif el.tag == "forward":
            t += int(el.findtext("duration"))
        elif el.tag == "note" and el.find("grace") is None:
            if el.find("chord") is not None:
                out.append((last, el))
                continue
            last = t
            out.append((t, el))
            t += int(el.findtext("duration") or 0)
        else:
            out.append((t, el))
    return out


def ties_out(measure: ET.Element) -> dict[int, set]:
    """Pitches that the last event of each voice (by order of appearance) ties on."""
    last: dict[str, list] = {}
    for el in measure:
        if el.tag == "note" and el.find("grace") is None:
            v = el.findtext("voice") or "1"
            if el.find("chord") is None:
                last[v] = []
            last.setdefault(v, []).append(el)
    return {k: {_pitch(n) for n in notes if n.find("pitch") is not None
                and any(t.get("type") == "start" for t in n.findall("tie"))}
            for k, notes in enumerate(last.values(), 1)}


def _is_text(el: ET.Element) -> bool:
    return el.tag == "direction" and all(c.tag in TEXT for kind in el.findall("direction-type") for c in kind)


def direction(text: str, above: bool) -> ET.Element:
    """A direction printing text, as dynamics where it is one ('mf'); a circled number ('①',
    which the text font lacks) as the number in a circle."""
    d = ET.Element("direction", placement="above" if above else "below")
    kind = ET.SubElement(d, "direction-type")
    if DYNAMICS.fullmatch(text):
        ET.SubElement(ET.SubElement(kind, "dynamics"), text)
    elif len(text) == 1 and "①" <= text <= "⑳":
        ET.SubElement(kind, "words", enclosure="circle").text = str(ord(text) - ord("①") + 1)
    else:
        ET.SubElement(kind, "words").text = text
    return d


def _sing(built: list[tuple[list, list, list]], open_words: dict[int, bool]) -> int:
    """Give the notes their syllables, line by line in time; open_words says which lines
    end on an unfinished word, and is kept up. Return how many."""
    sung = sorted(((line, t, v, text, note) for v, (_, firsts, _) in enumerate(built, 1)
                   for t, ev, note in firsts for line, text in ev["lyrics"].items()), key=lambda x: x[:3])
    count = 0
    for line, _, _, text, note in sung:
        if not (word := text.strip("-‐– ")):
            continue
        before, after = open_words.get(line, False), text.rstrip().endswith("-")
        lyric = ET.SubElement(note, "lyric", number=str(line))
        ET.SubElement(lyric, "syllabic").text = ("middle" if before else "begin") if after else ("end" if before else "single")
        ET.SubElement(lyric, "text").text = word
        open_words[line] = after
        count += 1
    return count


def _close_ties(measure: ET.Element, following: ET.Element | None) -> None:
    """Drop the ties that the measure's last notes start where no note at the start of the
    following measure ends them, which the engraver would draw on to a later note."""
    ended = set() if following is None else         {_pitch(n) for t, n in _onsets(following) if t == 0 and n.tag == "note" and n.find("pitch") is not None
         and n.find("tie[@type='stop']") is not None}
    last: dict[str, list] = {}
    for el in measure:
        if el.tag == "note" and el.find("grace") is None:
            if el.find("chord") is None:
                last[el.findtext("voice") or "1"] = []
            last.setdefault(el.findtext("voice") or "1", []).append(el)
    for n in (n for notes in last.values() for n in notes if n.find("pitch") is not None):
        if _pitch(n) not in ended:
            for tie in n.findall("tie[@type='start']"):
                n.remove(tie)
            for notations in n.findall("notations"):
                for tied in notations.findall("tied[@type='start']"):
                    notations.remove(tied)


def replace(measure: ET.Element, voices: list[list[dict]], tied_in: dict[int, set], fifths: int,
            texts: list[tuple[int, ET.Element]] = (), open_words: dict[int, bool] | None = None) -> int:
    """Put the voices in place of the measure's notes, with their syllables, and texts
    ((onset, direction)) in place of its words; other directions stay at their onsets.
    Return the number of syllables."""
    old = _onsets(measure)
    for el in [c for c in measure if _is_text(c)]:
        measure.remove(el)
    children = list(measure)
    music = [k for k, c in enumerate(children) if c.tag in ("note", "backup", "forward")]
    first, last = (music[0], music[-1]) if music else (len(children), len(children))
    movable = sorted([(t, el) for t, el in old if el.tag in MOVABLE and not _is_text(el)
                      and first < children.index(el) <= last] + list(texts), key=lambda x: x[0])
    for el in [children[k] for k in music] + [el for _, el in movable if el in children]:
        measure.remove(el)
    printed = _printed(voices, tied_in, fifths)
    built = [_voice(events, v, tied_in.get(v, set()), printed) for v, events in enumerate(voices, 1)]
    # A bracket of spaces, or the second voice's over the same notes as the first's, is not printed.
    spans = {(a, b) for a, b, _, _ in built[0][2]}
    for v, (_, _, triplets) in enumerate(built, 1):
        for a, b, bracket, hidden in triplets:
            if hidden or (v > 1 and (a, b) in spans):
                bracket.set("bracket", "no")
                bracket.set("show-number", "none")
    sung = _sing(built, {} if open_words is None else open_words)
    out = []
    for v, (notes, _, _) in enumerate(built, 1):
        if v > 1:
            backup = ET.Element("backup")
            ET.SubElement(backup, "duration").text = str(sum(int(n.findtext("duration")) for _, n in built[v - 2][0]
                                                             if n.find("chord") is None))
            out.append(backup)
        for t, n in notes:
            if v == 1 and n.find("chord") is None:
                while movable and movable[0][0] <= t:
                    out.append(movable.pop(0)[1])
            out.append(n)
        if v == 1:
            out += [el for _, el in movable]
    for k, el in enumerate(out):
        measure.insert(first + k, el)
    return sung


def _barline(measure: ET.Element, location: str) -> ET.Element:
    """The measure's barline at location, made if it has none: a left one before the
    measure's notes, a right one at its end."""
    found = next((b for b in measure.findall("barline") if b.get("location", "right") == location), None)
    if found is None:
        found = ET.Element("barline", location=location)
        if location == "left":
            measure.insert(next((k for k, c in enumerate(measure) if c.tag not in ("print", "attributes")),
                                len(measure)), found)
        else:
            measure.append(found)
    return found


def add_endings(parts: list[ET.Element], endings: list[tuple[str, int, int, bool]], read: set[int]) -> int:
    """Bracket the first and second endings, (number, first and last measure index, hook
    down at the end), in every part, in place of Audiveris's in the measures read; one cut
    by a system break is joined again. Return how many."""
    for part in parts:
        for k, m in enumerate(part.findall("measure")):
            for barline in m.findall("barline") if k in read else []:
                for ending in barline.findall("ending"):
                    barline.remove(ending)
                if not len(barline):
                    m.remove(barline)
    joined: list[list] = []
    for number, a, b, hook in sorted(endings, key=lambda e: e[1]):
        if joined and joined[-1][0] == number and joined[-1][2] + 1 >= a:
            joined[-1][2:] = [max(b, joined[-1][2]), hook]
        elif not joined or a > joined[-1][2]:
            joined.append([number, a, b, hook])
    for part in parts:
        measures = part.findall("measure")
        for number, a, b, hook in joined:
            for k, location, kind in ((a, "left", "start"), (b, "right", "stop" if hook else "discontinue")):
                barline = _barline(measures[k], location)
                repeat = barline.find("repeat")
                ending = ET.Element("ending", number=number, type=kind)
                barline.insert(list(barline).index(repeat) if repeat is not None else len(barline), ending)
    return len(joined)


def add_repeats(parts: list[ET.Element], repeats: list[tuple[int, bool]]) -> int:
    """Print the repeat signs, (measure index, whether it starts the repeated passage),
    where Audiveris saw none. Return how many were added."""
    added = 0
    for k, starts in sorted(set(repeats)):
        location, way, style = ("left", "forward", "heavy-light") if starts else ("right", "backward", "light-heavy")
        if any(b.get("location", "right") == location and b.find(f"repeat[@direction='{way}']") is not None
               for b in parts[0].findall("measure")[k].findall("barline")):
            continue
        for part in parts:
            barline = _barline(part.findall("measure")[k], location)
            if (bar_style := barline.find("bar-style")) is None:
                bar_style = ET.Element("bar-style")
                barline.insert(0, bar_style)
            bar_style.text = style
            ET.SubElement(barline, "repeat", direction=way)
        added += 1
    return added


def _rescale(root: ET.Element) -> None:
    """Give every part at least DIVISIONS divisions per quarter."""
    for part in root.findall("part"):
        for m, d in zip(part.findall("measure"), _running(part, "divisions", 1)):
            if (k := lcm(d, DIVISIONS) // d) > 1:
                for el in m.iter():
                    if el.tag in ("duration", "divisions"):
                        el.text = str(int(el.text) * k)


def _ask(client, image: Image.Image, text: str, log, answer: dict | None = None, wrong: list[str] = ()) -> dict | None:
    """Claude's reading of a system; with answer and what is wrong in it, its second look."""
    messages = [{"role": "user", "content": [_image(image), {"type": "text", "text": PROMPT + text}]}]
    if answer:
        messages += [{"role": "assistant", "content": json.dumps({k: v for k, v in answer.items() if k != "cost"},
                                                                 ensure_ascii=False)},
                     {"role": "user", "content": AGAIN + "\n".join(wrong)}]
    response = client.messages.create(
        model=MODEL, max_tokens=32000, messages=messages,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
    cost = (response.usage.input_tokens * 4 + response.usage.output_tokens * 20) / 1e6
    if response.stop_reason != "end_turn":
        log(f"Claude did not read a system ({response.stop_reason}, ${cost:.3f})")
        return None
    return {"cost": cost, **json.loads(next(b.text for b in response.content if b.type == "text"))}


def _bare(voice: str) -> str:
    """A voice's events without their syllables, as voices_of writes them."""
    return ", ".join(e for e in re.split(r"\s*,\s*", re.sub(r"\s*\[[^\]]*\]", "", voice)) if e.strip())


def _bottoms(part: ET.Element) -> list[int]:
    """The diatonic step (C4 = 28) of the bottom line under the clef in force in each measure."""
    out, value = [], 30
    for m in part.findall("measure"):
        if (clef := m.find("attributes/clef")) is not None and clef.findtext("line", "").isdigit():
            base = {"G": 32, "F": 24, "C": 28}.get(clef.findtext("sign"))
            if base is not None:
                value = base - 2 * (int(clef.findtext("line")) - 1) + 7 * int(clef.findtext("clef-octave-change") or 0)
        out.append(value)
    return out


def _step(pitch: str) -> int:
    return "CDEFGAB".index(pitch[0]) + 7 * int(pitch[-1])


def measured(events: list[dict], drafted: list[str], bottom: int) -> int:
    """Take the draft's pitch for a lone note of Claude's one step from the draft's lone
    note, on the staff: Audiveris measures a head against the staff lines, which Claude
    judges by eye, and in אתה הצבת it was right in all 11 such notes. Not on ledger lines,
    where Audiveris read a C drawn close to the staff as D. Claude's events and the draft's
    are paired in order, when there are as many. Return the notes changed."""
    drafted = [e.split(" ")[0].split("+") for e in drafted if e.split(" ")[0] not in ("r", "s")]
    sounding = [ev for ev in events if ev["pitches"]]
    if len(sounding) != len(drafted):
        return 0
    changed = 0
    for ev, theirs in zip(sounding, drafted):
        if len(ev["pitches"]) == len(theirs) == 1 and abs(_step(ev["pitches"][0]) - _step(theirs[0])) == 1 \
                and any(bottom <= _step(x) <= bottom + 8 for x in (ev["pitches"][0], theirs[0])):
            ev["pitches"] = theirs
            changed += 1
    return changed


def doubts(answer: dict, parts: list[ET.Element], numbers: dict[str, int]) -> list[str]:
    """What to have Claude look at again in its reading of a system: measures that are not
    in the format, and voices that do not add up to the time signature. The first and last
    measures may be short, and a measure may hold two where Audiveris missed a barline."""
    divisions = [_running(part, "divisions", 1) for part in parts]
    bars, last = [_bars(part) for part in parts], len(parts[0].findall("measure")) - 1
    out = []
    for got in answer.get("measures", []):
        if (k := numbers.get(got["number"])) is None:
            continue
        for staff in got["staves"]:
            s = staff["staff"]
            if not 1 <= s <= len(parts):
                continue
            for v, text in enumerate(staff["voices"], 1):
                where = f"measure {got['number']}, staff {s}, voice {v}"
                try:
                    events = parse_voice(text, divisions[s - 1][k])
                except ValueError as e:
                    out.append(f"- {where}: {e}")
                    continue
                total, bar = sum(Fraction(ev["duration"], divisions[s - 1][k]) for ev in events), bars[s - 1][k]
                ends = {sum(Fraction(ev["duration"], divisions[s - 1][k]) for ev in events[:j + 1]) for j in range(len(events))}
                n = total / bar if bar else Fraction(1)
                if n == 1 or (n < 1 and k in (0, last)) or (n.denominator == 1 and all(j * bar in ends for j in range(1, int(n)))):
                    continue
                time = parts[s - 1].findall("measure")
                beats = next((m.findtext("attributes/time/beats") for m in reversed(time[:k + 1])
                              if m.find("attributes/time") is not None), None)
                kind = next((m.findtext("attributes/time/beat-type") for m in reversed(time[:k + 1])
                             if m.find("attributes/time") is not None), None)
                unit = Fraction(4, int(kind)) if kind and kind.isdigit() else Fraction(1)
                name = UNITS.get(int(kind) if kind and kind.isdigit() else 4, "quarters")
                out.append(f"- {where}: its notes add up to {total / unit} {name}, but a measure of "
                           f"{beats}/{kind} has {bar / unit}")
    return out


def _bars(part: ET.Element) -> list[Fraction]:
    """Quarters in a whole measure of the time signature in force in each measure (0 without one)."""
    out, value = [], Fraction(0)
    for m in part.findall("measure"):
        beats, kind = m.findtext("attributes/time/beats"), m.findtext("attributes/time/beat-type")
        if beats and kind and beats.isdigit() and kind.isdigit():
            value = Fraction(4 * int(beats), int(kind))
        out.append(value)
    return out


def _slice(events: list[dict], start: Fraction, end: Fraction, divisions: int) -> list[dict]:
    out, t = [], Fraction(0)
    for ev in events:
        if start <= t < end:
            out.append(ev)
        t += Fraction(ev["duration"], divisions)
    return out


def split(parts: list[ET.Element], read: dict, divisions: list[list[int]]) -> tuple[dict, dict]:
    """Put back the barlines Audiveris missed (אתה הצבת, bar 21): a measure whose every voice,
    as Claude read it, adds up to two or more measures of the time signature, with an event
    ending at each barline, becomes that many measures. Return read by the new measure
    indices, and where each measure went: index -> (new index, quarters a bar, bars)."""
    bars = [_bars(part) for part in parts]
    cuts = {}
    for k, (_, voices) in read.items():
        counts = set()
        for s, vs in voices.items():
            bar = bars[s - 1][k]
            for v in vs:
                ends, t = set(), Fraction(0)
                for ev in v:
                    t += Fraction(ev["duration"], divisions[s - 1][k])
                    ends.add(t)
                n = t / bar if bar else Fraction(0)
                counts.add(int(n) if n.denominator == 1 and n >= 2 and all(j * bar in ends for j in range(1, int(n)))
                           else None)
        if len(counts) == 1 and (n := counts.pop()):
            cuts[k] = n
    moved, shift = {}, 0
    for k in range(len(parts[0].findall("measure"))):
        moved[k] = (k + shift, bars[0][k], cuts.get(k, 1))
        shift += cuts.get(k, 1) - 1
    if not cuts:
        return read, moved
    added = set()
    for k in sorted(cuts, reverse=True):
        for part in parts:
            m = part.findall("measure")[k]
            new = [ET.Element("measure", number="") for _ in range(cuts[k] - 1)]
            at = list(part).index(m)
            for j, el in enumerate(new, 1):
                part.insert(at + j, el)
                added.add(id(el))
            for barline in m.findall("barline"):
                if barline.get("location", "right") == "right":
                    m.remove(barline)
                    new[-1].append(barline)
    for part in parts:
        offset, last = 0, None
        for m in part.findall("measure"):
            if id(m) in added:
                offset += 1
                m.set("number", str(last + 1) if last is not None else "")
            elif (number := m.get("number", "")).isdigit():
                m.set("number", str(int(number) + offset))
            last = int(m.get("number")) if m.get("number", "").isdigit() else last
    out = {}
    for k, (staves, voices) in read.items():
        at, bar, n = moved[k]
        if n == 1:
            out[at] = staves, voices
            continue
        for j in range(n):
            out[at + j] = ({s: [""] * len(vs) for s, vs in staves.items()},
                           {s: [_slice(v, j * bar, (j + 1) * bar, divisions[s - 1][k]) for v in vs]
                            for s, vs in voices.items()})
    return out, moved


def number_slurs(parts: list[ET.Element]) -> None:
    """Number the slurs of Claude's reading, which may end in a later measure or system, by
    how many are open in their voice; drop those that never start or never end."""
    for part in parts:
        open_: dict[str, list[tuple[ET.Element, ET.Element]]] = {}
        for m in part.findall("measure"):
            for n in m.findall("note"):
                if (notations := n.find("notations")) is None:
                    continue
                stack = open_.setdefault(n.findtext("voice") or "1", [])
                for slur in [x for x in notations.findall("slur") if x.get("number") is None]:
                    if slur.get("type") == "stop":
                        if stack:
                            slur.set("number", stack.pop()[1].get("number"))
                        else:
                            notations.remove(slur)
                    else:
                        slur.set("number", str(len(stack) + 1))
                        stack.append((notations, slur))
        for notations, slur in (x for stack in open_.values() for x in stack):
            notations.remove(slur)


def apply(parts: list[ET.Element], systems: list[list[int]], answers: list[dict | None], log=print) -> tuple[set, list[Chord]]:
    """Write Claude's answers, one per system (None where there is none), into the parts.
    Return the (part, measure) indices rewritten and the chord symbols by measure index."""
    divisions = [_running(p, "divisions", 1) for p in parts]
    first_part = parts[0].findall("measure")
    numbered = [{first_part[k].get("number"): k for k in measures} for measures in systems]
    read = {}  # measure -> (Claude's voices as written, parsed) per staff
    for numbers, answer in zip(numbered, answers):
        for got in (answer or {}).get("measures", []):
            k = numbers.get(got["number"])
            staves = {s["staff"]: [v for v in s["voices"] if v.strip()] for s in got["staves"]}
            if k is None or sorted(staves) != list(range(1, len(parts) + 1)):
                continue
            try:
                voices = {s: [parse_voice(v, divisions[s - 1][k]) for v in vs] for s, vs in staves.items()}
            except ValueError as e:
                log(f"Measure {got['number']} kept as recognised: {e}")
                continue
            if len({Fraction(sum(ev["duration"] for ev in v), divisions[s - 1][k])
                    for s, vs in voices.items() for v in vs}) != 1:
                log(f"Measure {got['number']} kept as recognised: its voices do not add up")
                continue
            read[k] = staves, voices
    taken = 0
    for k, (staves, voices) in read.items():
        for s, vs in voices.items():
            drafted = voices_of(parts[s - 1].findall("measure")[k], divisions[s - 1][k])
            if len(vs) == 1 and len(drafted) == 1:
                taken += measured(vs[0], next(iter(drafted.values())), _bottoms(parts[s - 1])[k])
    if taken:
        log(f"Kept {taken} pitch(es) of Audiveris's a step from Claude's")
    read, moved = split(parts, read, divisions)
    if (cut := sum(n - 1 for _, _, n in moved.values())):
        log(f"Added {cut} barline(s) that Audiveris missed")

    def place(k: int, q: float = math.inf) -> tuple[int, float]:
        """Where a position in measure k of Audiveris's reading is now; by default its last bar."""
        at, bar, bars = moved[k]
        j = (bars - 1 if q == math.inf else min(int(Fraction(q) // bar), bars - 1)) if bars > 1 else 0
        return at + j, (0.0 if q == math.inf else q - float(j * bar))

    divisions = [_running(p, "divisions", 1) for p in parts]
    fifths = [_running(p, "key/fifths", 0) for p in parts]
    chords, endings, repeats, found = [], [], [], []  # found: (system, measure, quarters, staff, above, text)
    for s, (numbers, answer) in enumerate(zip(numbered, answers)):
        if not answer:
            continue
        chords += [Chord(*place(numbers[c["measure"]], c["quarters"]), c["symbol"]) for c in answer["chords"]
                   if c["measure"] in numbers]
        endings += [(", ".join(re.findall(r"\d+", e["number"])), place(numbers[e["first"]], 0)[0],
                     place(numbers[e["last"]])[0], e["hook"])
                    for e in answer["endings"] if e["first"] in numbers and e["last"] in numbers
                    and re.search(r"\d", e["number"]) and numbers[e["first"]] <= numbers[e["last"]]]
        repeats += [(place(numbers[r["measure"]], 0 if r["starts"] else math.inf)[0], r["starts"])
                    for r in answer.get("repeats", []) if r["measure"] in numbers]
        found += [(s, *place(numbers[t["measure"]], t["quarters"]), t["staff"], t["above"], t["text"].strip())
                  for t in answer["texts"] if t["measure"] in numbers and 1 <= t["staff"] <= len(parts) and t["text"].strip()]
    texts: dict[tuple[int, int], list] = {}  # (part, measure) -> (quarters, direction)
    for s, k, q, staff, above, text in found:
        # Words between two systems, which both images show, are the lower system's.
        if not above and staff == len(parts) and any(s2 == s + 1 and a2 and st2 == 1 and t2.casefold() == text.casefold()
                                                     for s2, _, _, st2, a2, t2 in found):
            continue
        texts.setdefault((staff - 1, k), []).append((q, direction(text, above)))
    # A staff that two parts share holds chords on one stem; Claude cannot tell from a poor
    # scan which notes have a second stem, but there a lone note is one both parts sing.
    duets = []
    for s in range(1, len(parts) + 1):
        notes = [ev for staves, voices in read.values() for ev in voices[s][0] if ev["pitches"]]
        duets.append(bool(notes) and sum(len(ev["pitches"]) > 1 for ev in notes) >= DUET_CHORDS * len(notes))
    rewritten, changed, sung, words = set(), 0, 0, 0
    open_words: list[dict[int, bool]] = [{} for _ in parts]  # per part, the lines that end in a word cut short
    for k in sorted(read):
        staves, voices = read[k]
        for p, part in enumerate(parts):
            m = part.findall("measure")[k]
            changed += list(voices_of(m, divisions[p][k]).values()) != [_bare(v).split(", ") for v in staves[p + 1]]
            ours = shared(voices[p + 1][0]) if duets[p] and len(voices[p + 1]) == 1 else voices[p + 1]
            length = sum(ev["duration"] for ev in ours[0])
            here = [(min(max(round(q * divisions[p][k]), 0), length), el) for q, el in texts.get((p, k), [])]
            words += len(here)
            # A tie over the barline ends on its pitch, in whichever voice Claude put it.
            held = set().union(*ties_out(part.findall("measure")[k - 1]).values()) if k else set()
            sung += replace(m, ours, {v: held for v in range(1, len(ours) + 1)}, fifths[p][k], here, open_words[p])
            rewritten.add((p, k))
    for p, part in enumerate(parts):
        measures = part.findall("measure")
        for k, m in enumerate(measures):
            if (p, k) in rewritten or (p, k + 1) in rewritten:
                _close_ties(m, measures[k + 1] if k + 1 < len(measures) else None)
    number_slurs(parts)
    added = add_endings(parts, endings, {moved[k][0] + j for numbers, answer in zip(numbered, answers) if answer
                                         for k in numbers.values() for j in range(moved[k][2])}), add_repeats(parts, repeats)
    log(f"Claude's reading: {changed} staff measure(s) with other notes, {sung} syllable(s), {words} word(s), "
        f"{added[0]} ending(s), {added[1]} repeat sign(s) added")
    return rewritten, chords


def read_again(mxl: Path, omr: Path, load_sheets: Callable[[], list[Image.Image]], log=print) -> tuple[set, list[Chord]]:
    """Correct Audiveris's MusicXML file in place, system by system; load_sheets gives the
    pages Audiveris read, as it read them. Return the (part, measure) indices rewritten,
    for beaming, and the chord symbols by measure index."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return set(), []
    try:
        import anthropic

        with zipfile.ZipFile(mxl) as z:
            name = next(n for n in z.namelist() if n.endswith(".xml") and not n.startswith("META-INF"))
            text = z.read(name).decode("utf-8")
        start = text.index("<score-partwise")
        root = ET.fromstring(text[start:])
        parts = root.findall("part")
        if any(int(s.text or 1) > 1 for part in parts for s in part.iter("staves")):
            log("Not read again by Claude: a part is written on several staves")
            return set(), []
        systems, places = systems_of(root), page_systems(omr)
        if len(systems) != len(places):
            log(f"Not read again by Claude: {len(places)} systems on the pages, {len(systems)} in the score")
            return set(), []
        _rescale(root)
        sheets = load_sheets()
        client = anthropic.Anthropic(timeout=600.0)
        answers, again = [], 0
        first_part = parts[0].findall("measure")
        for measures, (sheet, width, box, slope) in zip(systems, places):
            page = sheets[sheet]
            image, written = level(page.crop(tuple(round(v * page.width / width) for v in box)), slope), draft(parts, measures)
            answer = _ask(client, image, written, log)
            if answer and (wrong := doubts(answer, parts, {first_part[k].get("number"): k for k in measures})):
                second = _ask(client, image, written, log, answer, wrong)
                again += 1
                if second:
                    answer = {**second, "cost": answer["cost"] + second["cost"]}
            answers.append(answer)
        log(f"Claude read {len(systems)} system(s) again, {again} of them twice (${sum(a['cost'] for a in answers if a):.2f})")
        rewritten, chords = apply(parts, systems, answers, log)
        if rewritten:
            with zipfile.ZipFile(mxl, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr(name, text[:start] + ET.tostring(root, encoding="unicode"))
                z.writestr("META-INF/container.xml", '<?xml version="1.0" encoding="UTF-8"?><container>'
                           f'<rootfiles><rootfile full-path="{name}"/></rootfiles></container>')
        return rewritten, chords
    except Exception as e:  # the score is complete without this step
        log(f"Could not have Claude read the systems again: {e}")
        return set(), []


def open_endings(musicxml: Path) -> None:
    """Leave open the end of an ending that no repeat sign closes, as the last ending is
    printed; music21 writes the end of every ending as closed."""
    def open_(barline: re.Match) -> str:
        return barline.group(0) if 'direction="backward"' in barline.group(0) else \
            barline.group(0).replace('type="stop"', 'type="discontinue"')
    text = musicxml.read_text(encoding="utf-8")
    musicxml.write_text(re.sub(r"<barline\b(?:(?!</barline>).)*<ending\b[^>]*type=\"stop\"(?:(?!</barline>).)*</barline>",
                               open_, text, flags=re.S), encoding="utf-8")


def beam(score: m21.stream.Score, rewritten: set) -> None:
    """Beam the rewritten measures, which Claude's reading leaves without beams. The stems
    are left to the engraver, which turns them up in the first voice and down in the second."""
    parts = list(score.parts)
    for p, k in rewritten:
        measures = parts[p].getElementsByClass(m21.stream.Measure) if p < len(parts) else []
        if k < len(measures):
            try:
                measures[k].makeBeams(inPlace=True, setStemDirections=False)
            except Exception:  # an overfull or odd measure keeps its flags
                pass
