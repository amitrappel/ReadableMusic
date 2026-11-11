"""Spread the voices of a score over more staves, or gather them onto fewer (the editor's
Staves choice).

A staff that two parts share is named after both, "Soprano, Alto" (standardize_names in
parts.py). Its upper voice is voice 1 of the MusicXML with the top notes of its chords; the
lower one is voice 2 where that is printed, and elsewhere voice 1's bottom notes, or its
single notes, which both sing. Two voices put on one staff become voices 1 and 2, stems up
and down, and the lower keeps only the words the upper does not sing at the same time, on
lines of their own. Neighbours that read in one clef share a staff first, from the bottom:
SATB on two staves is S A | T B, on three S | A | T B. Each staff then prints the
accidentals its notes call for (print_accidentals, which the pipeline also runs).
"""

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from math import lcm

from .reader import _onsets, _running
from .reread import _element, _place, key_alters

NOTE_ORDER = ["grace", "cue", "chord", "pitch", "unpitched", "rest", "duration", "tie", "instrument", "footnote",
              "level", "voice", "type", "dot", "accidental", "time-modification", "stem", "notehead",
              "notehead-text", "staff", "beam", "notations", "lyric", "play", "listen"]
SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SIGNS = {-2: "flat-flat", -1: "flat", 0: "natural", 1: "sharp", 2: "double-sharp"}
ITEMS = ("direction", "harmony", "sound", "figured-bass")  # placed by their onset, in no voice
BEAMED = ("eighth", "16th", "32nd", "64th", "128th")
TREBLE, BASS, TENOR = ("G", "2", "0"), ("F", "4", "0"), ("G", "2", "-1")
SLURS = 6  # numbers MusicXML gives slurs open at once in a part

Event = tuple[int, int, list[ET.Element]]  # onset, duration and the notes of one chord


@dataclass
class Voice:
    name: str
    short: str
    part: ET.Element  # the part it is read from
    side: int | None  # None for a whole part, 0 or 1 for the upper or lower voice of a shared staff
    clef: tuple[str, str, str]  # (sign, line, octave change) on a staff of its own

    @property
    def low(self) -> bool:
        """Sung in the bass clef on a shared staff: a bass, or a tenor, who reads treble 8 alone."""
        return self.clef[0] == "F" or self.clef[2] == "-1"


def _first_clef(part: ET.Element) -> tuple[str, str, str]:
    clef = part.find("measure/attributes/clef")
    if clef is None:
        return TREBLE
    return clef.findtext("sign") or "G", clef.findtext("line") or "2", clef.findtext("clef-octave-change") or "0"


def voices_of(root: ET.Element) -> list[Voice]:
    """The voices of a score from top to bottom; editor.js counts them the same way."""
    names = {sp.get("id"): (sp.findtext("part-name") or "", sp.findtext("part-abbreviation") or "")
             for sp in root.iter("score-part")}
    out = []
    for part in root.findall("part"):
        name, short = names.get(part.get("id"), ("", ""))
        clef, both, shorts = _first_clef(part), name.split(", "), short.split()
        if len(both) != 2:
            out.append(Voice(name, short, part, None, clef))
            continue
        for side in (0, 1):
            own = TENOR if clef[0] == "F" and side == 0 else clef
            out.append(Voice(both[side], shorts[side] if len(shorts) == 2 else "", part, side, own))
    return out


def groups(voices: list[Voice], count: int) -> list[list[int]]:
    """The voices on each of count staves: pairs of neighbours that read in one clef first,
    from the bottom, then any neighbours."""
    n = len(voices)
    if not (n + 1) // 2 <= count <= n:
        raise ValueError(f"{n} voice(s) go on {(n + 1) // 2} to {n} staves, not {count}")
    pairs: list[int] = []  # the upper voice of each pair
    for alike in (True, False):
        for i in range(n - 1, 0, -1):
            taken = {j for p in pairs for j in (p, p + 1)}
            if len(pairs) < n - count and not {i - 1, i} & taken and (not alike or voices[i - 1].low == voices[i].low):
                pairs.append(i - 1)
    if len(pairs) < n - count:  # single voices left between the pairs: pair from the top
        pairs = list(range(0, 2 * (n - count), 2))
    out, i = [], 0
    while i < n:
        out.append([i, i + 1] if i in pairs else [i])
        i += len(out[-1])
    return out


def _unify(root: ET.Element) -> None:
    """One number of divisions a quarter in every measure, so that measures can be joined."""
    parts = root.findall("part")
    running = [_running(part, "divisions", 1) for part in parts]
    whole = lcm(*{d for r in running for d in r})
    for part, divisions in zip(parts, running):
        for m, d in zip(part.findall("measure"), divisions):
            for el in m.iter():
                if el.tag in ("duration", "offset") and whole != d:
                    el.text = str(round(float(el.text) * whole / d))
                elif el.tag == "divisions":
                    el.text = str(whole)


def _insert(note: ET.Element, el: ET.Element) -> None:
    """Put el into a note where MusicXML wants it."""
    rank = NOTE_ORDER.index(el.tag)
    k = next((k for k, c in enumerate(note) if c.tag in NOTE_ORDER and NOTE_ORDER.index(c.tag) > rank), len(note))
    note.insert(k, el)


def _events(measure: ET.Element) -> dict[str, list[Event]]:
    """The events of each voice of a measure."""
    out: dict[str, list[Event]] = {}
    for t, el in _onsets(measure):
        if el.tag != "note":
            continue
        voice = el.findtext("voice") or "1"
        if el.find("chord") is not None and out.get(voice):
            out[voice][-1][2].append(el)
        else:
            length = 0 if el.find("grace") is not None else int(el.findtext("duration") or 0)
            out.setdefault(voice, []).append((t, length, [el]))
    return out


def _height(note: ET.Element) -> int:
    pitch = note.find("pitch")
    return (12 * int(pitch.findtext("octave")) + SEMITONES[pitch.findtext("step")]
            + round(float(pitch.findtext("alter") or 0)))


def _sounding(first: ET.Element, tone: ET.Element) -> ET.Element:
    """A copy of a chord's first note, with its words and marks, sounding tone of the chord."""
    note = copy.deepcopy(first)
    if tone is first:
        return note
    for tag in ("pitch", "tie", "accidental"):
        for el in note.findall(tag):
            note.remove(el)
        for el in tone.findall(tag):
            _insert(note, copy.deepcopy(el))
    notations = note.find("notations")
    for el in [] if notations is None else notations.findall("tied"):
        notations.remove(el)
    if tied := [copy.deepcopy(el) for el in tone.findall("notations/tied")]:
        if notations is None:
            _insert(note, notations := ET.Element("notations"))
        notations.extend(tied)
    return note


def _tone(el: ET.Element) -> ET.Element:
    """A copy of a note to follow a chord's first: no words, and of its marks only ties."""
    note = copy.deepcopy(el)
    for lyric in note.findall("lyric"):
        note.remove(lyric)
    if note.find("chord") is None:
        _insert(note, ET.Element("chord"))
    for notations in note.findall("notations"):
        for mark in [m for m in notations if m.tag != "tied"]:
            notations.remove(mark)
        if not len(notations):
            note.remove(notations)
    return note


def _chord(first: ET.Element, tones: list[ET.Element]) -> list[ET.Element]:
    return [_sounding(first, tones[0])] + [_tone(t) for t in tones[1:]]


def _copy(event: Event) -> Event:
    return event[0], event[1], [copy.deepcopy(n) for n in event[2]]


def split(measure: ET.Element) -> tuple[list[Event], list[Event]]:
    """The upper and the lower voice of a measure of a shared staff."""
    voices = _events(measure)
    ids = sorted(voices, key=lambda v: (v != "1", v))
    first = voices[ids[0]] if ids else []
    shown = [e for v in ids[1:] for e in voices[v] if e[2][0].get("print-object") != "no"]
    upper, lower = [], [_copy(e) for e in shown]
    for t, length, notes in first:
        alone = length > 0 and not any(s < t + length and t < s + d for s, d, _ in shown)
        pitched = sorted((n for n in notes if n.find("pitch") is not None), key=_height)
        if alone and len(pitched) >= 2:
            upper.append((t, length, _chord(notes[0], pitched[1:])))
            lower.append((t, length, _chord(notes[0], pitched[:1])))
            continue
        upper.append(_copy((t, length, notes)))
        if alone:
            lower.append(_copy((t, length, notes)))
    # The lower voice's own notes sing the words of the upper's at the same time.
    words = {t: notes[0].findall("lyric") for t, _, notes in first if notes[0].find("lyric") is not None}
    for t, _, notes in lower:
        if notes[0].find("pitch") is not None and notes[0].find("lyric") is None:
            for lyric in words.get(t, []):
                _insert(notes[0], copy.deepcopy(lyric))
    for _, _, notes in upper + lower:  # a voice alone shows its rests
        for n in notes:
            if n.find("rest") is not None:
                n.attrib.pop("print-object", None)
                n.attrib.pop("print-spacing", None)
    return upper, sorted(lower, key=lambda e: e[0])


def _beams_ok(events: list[Event]) -> bool:
    open_ = False
    for _, _, notes in events:
        beam = next((b.text for b in notes[0].findall("beam") if b.get("number", "1") == "1"), None)
        if beam == "begin" and not open_:
            open_ = True
        elif beam in ("continue", "end") and open_:
            open_ = beam == "continue"
        elif beam or open_:
            return False
    return not open_


def _beam_run(run: list[ET.Element], level: int) -> None:
    short = ("16th", "32nd", "64th", "128th")[level - 2:]
    j = 0
    while j < len(run):
        if level > 1 and run[j].findtext("type") not in short:
            j += 1
            continue
        end = j
        while end + 1 < len(run) and (level == 1 or run[end + 1].findtext("type") in short):
            end += 1
        if end > j:
            for i in range(j, end + 1):
                kind = "begin" if i == j else "end" if i == end else "continue"
                _insert(run[i], _beam(kind, level))
        elif level > 1:
            _insert(run[j], _beam("forward hook" if j == 0 else "backward hook", level))
        j = end + 1
    if level < 4 and any(n.findtext("type") in ("16th", "32nd", "64th", "128th")[level - 1:] for n in run):
        _beam_run(run, level + 1)


def _beam(kind: str, level: int) -> ET.Element:
    el = ET.Element("beam", number=str(level))
    el.text = kind
    return el


def rebeam(events: list[Event], beat: int) -> None:
    """Beam the eighths and shorter notes of each beat (of beat divisions) together."""
    for _, _, notes in events:
        for n in notes:
            for b in n.findall("beam"):
                n.remove(b)
    runs, last = [], None
    for t, _, notes in events:
        n = notes[0]
        if n.findtext("type") not in BEAMED or n.find("rest") is not None or n.find("grace") is not None:
            last = None
            continue
        if last != t // beat:
            runs.append([])
        runs[-1].append(n)
        last = t // beat
    for run in runs:
        if len(run) > 1:
            _beam_run(run, 1)


def _beats(part: ET.Element) -> list[int]:
    """The divisions in a beat of each measure, for beaming: a dotted quarter in 6/8."""
    out, beats, kind = [], 4, 4
    divisions = _running(part, "divisions", 1)
    for m, d in zip(part.findall("measure"), divisions):
        b, k = m.findtext("attributes/time/beats") or "", m.findtext("attributes/time/beat-type") or ""
        if b.isdigit() and k.isdigit():
            beats, kind = int(b), int(k)
        unit = d * 4 // kind
        out.append(3 * unit if kind >= 8 and beats % 3 == 0 else max(unit, d))
    return out


def _set_voice(note: ET.Element, voice: str, stem: str | None) -> None:
    if (el := note.find("voice")) is None:
        _insert(note, el := ET.Element("voice"))
    el.text = voice
    for s in note.findall("stem"):
        note.remove(s)
    if stem:
        _insert(note, _element("stem"))
        note.find("stem").text = stem


def _move(by: int, tag: str, voice: str | None = None) -> ET.Element:
    el = ET.Element(tag)
    ET.SubElement(el, "duration").text = str(by)
    if voice:
        ET.SubElement(el, "voice").text = voice
    return el


def _lyric_lines(events: list[Event]) -> int:
    numbers = [l.get("number", "1") for _, _, notes in events for l in notes[0].findall("lyric")]
    return max((int(n) for n in numbers if n.isdigit()), default=0)


def _words(lyric: ET.Element) -> str:
    return "_".join(t.text or "" for t in lyric.findall("text"))


def _shared_words(measures: list[tuple[list[Event], list[Event]]], lines: int) -> None:
    """Drop the lower voice's words that the upper sings at the same time. Where the two
    sing other words at the same time anywhere, the lower's own go below the upper's lines,
    all of them in a measure where it has its own (the bass's "sha-ru" under the tenor's in
    האדון הרופא); else the two share the lines."""
    found, apart = [], False  # per measure: the lower's words, (note, lyric, the upper's the same)
    for upper, lower in measures:
        sung = {(t, l.get("number", "1")): _words(l) for t, _, notes in upper for l in notes[0].findall("lyric")}
        words = []
        for t, _, notes in lower:
            for l in notes[0].findall("lyric"):
                here = sung.get((t, l.get("number", "1")))
                words.append((notes[0], l, here == _words(l)))
                apart |= here is not None and here != _words(l)
        found.append(words)
    for words in found:
        own = any(not same for _, _, same in words)
        for note, l, same in words:
            if same and not (apart and own):
                note.remove(l)
            elif apart and (number := l.get("number", "1")).isdigit():
                l.set("number", str(int(number) + lines))
                if "name" in l.attrib:
                    l.set("name", l.get("number"))


def _lend_words(parts: list[ET.Element], new: list[bool]) -> None:
    """A new staff without words sings those of the nearest staff above at the same times:
    the words between two staves of the original were both's."""
    for k, part in enumerate(parts):
        above = next((p for p in reversed(parts[:k]) if p.find(".//lyric") is not None), None)
        if not new[k] or above is None or part.find(".//lyric") is not None:
            continue
        for m, source in zip(part.findall("measure"), above.findall("measure")):
            words: dict[int, list[ET.Element]] = {}
            for t, el in _onsets(source):
                if el.tag == "note" and el.find("chord") is None and el.find("lyric") is not None:
                    words.setdefault(t, el.findall("lyric"))
            for t, el in _onsets(m):
                if el.tag == "note" and el.find("chord") is None and el.find("pitch") is not None:
                    for lyric in words.get(t, []):
                        _insert(el, copy.deepcopy(lyric))


def _number_slurs(part: ET.Element) -> None:
    """Pair each voice's slurs again, numbered apart within the part; drop those left unpaired."""
    held: dict[str, list[tuple[ET.Element, ET.Element]]] = {}
    used: set[int] = set()
    for note in part.iter("note"):
        voice = note.findtext("voice") or "1"
        for notations in note.findall("notations"):
            for slur in sorted(notations.findall("slur"), key=lambda s: s.get("type") != "stop"):
                if slur.get("type") == "stop":
                    if not held.get(voice):
                        notations.remove(slur)
                        continue
                    _, start = held[voice].pop()
                    slur.set("number", start.get("number"))
                    used.discard(int(start.get("number")))
                elif slur.get("type") == "start":
                    free = sorted(set(range(1, SLURS + 1)) - used)
                    if not free:
                        notations.remove(slur)
                        continue
                    slur.set("number", str(free[0]))
                    used.add(free[0])
                    held.setdefault(voice, []).append((notations, slur))
    for notations, slur in (x for stack in held.values() for x in stack):
        notations.remove(slur)
    for note in part.iter("note"):
        for notations in note.findall("notations"):
            if not len(notations):
                note.remove(notations)


def _is_dynamics(el: ET.Element) -> bool:
    kinds = [c for d in el.findall("direction-type") for c in d]
    return el.tag == "direction" and bool(kinds) and all(c.tag == "dynamics" for c in kinds)


def _clef(voices: list[Voice]) -> tuple[str, str, str]:
    clefs = {v.clef for v in voices}
    if len(clefs) == 1:
        return clefs.pop()
    return BASS if any(v.low for v in voices) else TREBLE


def _part(voices: list[Voice], top: bool, pid: str) -> ET.Element:
    """A part of voices, one or two, which are not the part they come from."""
    part = ET.Element("part", id=pid)
    sources = [v.part.findall("measure") for v in voices]
    beats = _beats(voices[0].part)
    clef = _clef(voices)
    lines = 0
    built: list[list[dict[str, list[Event]]]] = []  # measure -> voice -> its voices' events
    for k in range(len(sources[0])):
        row = []
        for v, measures in zip(voices, sources):
            if v.side is None:
                row.append({key: [_copy(e) for e in events] for key, events in _events(measures[k]).items()})
            else:
                events = split(measures[k])[v.side]
                if not _beams_ok(events):
                    rebeam(events, beats[k])
                row.append({"1": events})
        built.append(row)
    if len(voices) == 2:
        lines = max(_lyric_lines(e) for row in built for e in row[0].values())
        _shared_words([([e for es in row[0].values() for e in es], [e for es in row[1].values() for e in es])
                       for row in built], lines)
    for k, row in enumerate(built):
        source = sources[0][k]
        m = ET.SubElement(part, "measure", {a: v for a, v in source.attrib.items() if a in ("number", "implicit")})
        for barline in source.findall("barline"):
            if barline.get("location") == "left":
                m.append(copy.deepcopy(barline))
        attributes = next((copy.deepcopy(el) for t, el in _onsets(source) if el.tag == "attributes" and t == 0), None)
        for el in [] if attributes is None else [*attributes.findall("clef"), *attributes.findall("staves")]:
            attributes.remove(el)
        if k == 0:
            if attributes is None:
                attributes = ET.Element("attributes")
            c = _element("clef", ("sign", clef[0]), ("line", clef[1]))
            if clef[2] != "0":
                ET.SubElement(c, "clef-octave-change").text = clef[2]
            _place(attributes, c)
        if attributes is not None and len(attributes):
            m.append(attributes)
        items, seen = [], set()
        for j, (v, measures) in enumerate(zip(voices, sources)):
            for t, el in _onsets(measures[k]):
                if el.tag not in ITEMS or (el.tag in ("harmony", "sound") and not (top and j == 0)) \
                        or (v.side == 1 and not _is_dynamics(el)):
                    continue
                el = copy.deepcopy(el)
                for child in [c for c in el if c.tag in ("staff", "voice")]:
                    el.remove(child)
                if (key := (t, ET.tostring(el))) not in seen:
                    seen.add(key)
                    items.append((t, el))
        at = 0
        for t, el in sorted(items, key=lambda x: x[0]):
            if t > at:
                m.append(_move(t - at, "forward"))
            elif t < at:
                m.append(_move(at - t, "backup"))
            at = t
            m.append(el)
        for j, voice_events in enumerate(row):
            for n, (key, events) in enumerate(sorted(voice_events.items(), key=lambda x: (x[0] != "1", x[0]))):
                name = str(j + 1 + 2 * n) if len(voices) == 2 else str(n + 1)
                stem = ("up", "down")[j] if len(voices) == 2 else None
                if at:
                    m.append(_move(at, "backup"))
                at = 0
                for t, length, notes in events:
                    if t > at:
                        m.append(_move(t - at, "forward", name))
                        at = t
                    for note in notes:
                        _set_voice(note, name, stem)
                        for instrument in note.findall("instrument"):
                            note.remove(instrument)
                        m.append(note)
                    at = t + length
        for barline in source.findall("barline"):
            if barline.get("location", "right") != "left":
                m.append(copy.deepcopy(barline))
    _number_slurs(part)
    return part


def restaff(text: str, count: int) -> str:
    """The score of MusicXML text with its voices on count staves."""
    start = text.index("<score-partwise")
    root = ET.fromstring(text[start:])
    if any(int(s.text or 1) > 1 for s in root.iter("staves")):
        raise ValueError("a part has more than one staff")
    parts = root.findall("part")
    if len({len(p.findall("measure")) for p in parts}) > 1:
        raise ValueError("the parts have different numbers of measures")
    voices = voices_of(root)
    chosen = groups(voices, count)
    _unify(root)
    part_list = root.find("part-list")
    score_parts = {sp.get("id"): sp for sp in part_list.findall("score-part")}
    new_parts, new_list, built = [], [], []
    for g, members in enumerate(chosen, 1):
        vs = [voices[i] for i in members]
        pid = f"P{g}"
        whole = (len(vs) == 1 and vs[0].side is None) or (len(vs) == 2 and vs[0].part is vs[1].part)
        if whole:
            part, score_part = vs[0].part, copy.deepcopy(score_parts[vs[0].part.get("id")])
            part.set("id", pid)
        else:
            part, score_part = _part(vs, members[0] == 0, pid), ET.Element("score-part")
            ET.SubElement(score_part, "part-name").text = ", ".join(v.name for v in vs)
            if all(v.short for v in vs):
                ET.SubElement(score_part, "part-abbreviation").text = " ".join(v.short for v in vs)
        score_part.set("id", pid)
        new_parts.append(part)
        new_list.append(score_part)
        built.append(not whole)
    _lend_words(new_parts, built)
    groups_before = [el for el in part_list if el.tag == "part-group" and el.get("type") == "start"]
    groups_after = [el for el in part_list if el.tag == "part-group" and el.get("type") == "stop"]
    for el in list(part_list):
        part_list.remove(el)
    part_list.extend(groups_before + new_list + groups_after)
    for p in parts:
        root.remove(p)
    root.extend(new_parts)
    _print_accidentals(root)
    return text[:start] + ET.tostring(root, encoding="unicode")


def _print_accidentals(root: ET.Element) -> None:
    for part in root.findall("part"):
        key: dict[str, int] = {}
        for m in part.findall("measure"):
            if (fifths := m.findtext("attributes/key/fifths")) is not None:
                key = key_alters(int(fifths))
            state: dict[tuple, int] = {}  # (staff, step, octave) -> alteration in force
            notes = [(t, k, n) for k, (t, n) in enumerate(_onsets(m)) if n.tag == "note" and n.find("pitch") is not None]
            for _, _, n in sorted(notes, key=lambda x: x[:2]):
                if n.find("tie[@type='stop']") is not None:
                    continue
                p = n.find("pitch")
                alter, place = round(float(p.findtext("alter") or 0)), (n.findtext("staff") or "1", p.findtext("step"), p.findtext("octave"))
                if alter != state.get(place, key.get(place[1], 0)) and n.find("accidental") is None and alter in SIGNS:
                    sign = ET.Element("accidental")
                    sign.text = SIGNS[alter]
                    _insert(n, sign)
                state[place] = alter


def print_accidentals(text: str) -> str:
    """Print the accidentals that a score of MusicXML text lacks: where neither the key nor
    an earlier note on that line or space of the staff in the measure gives a note its
    alteration. A note tied over the barline keeps its own without one, but the notes after
    it do not: Audiveris printed a C flat's flat only before the tie (האדון הרופא, bar 2)."""
    start = text.index("<score-partwise")
    root = ET.fromstring(text[start:])
    _print_accidentals(root)
    return text[:start] + ET.tostring(root, encoding="unicode")
