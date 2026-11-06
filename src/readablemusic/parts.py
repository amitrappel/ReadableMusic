"""Merge the parts Audiveris splits across systems back into one part per voice.

Audiveris joins staves of different systems into one part only when their OCR'd names
match exactly. With hidden empty staves and OCR noise ("B l", "Bl", "B1") a 9-voice score
can come out as 40+ parts, each hidden in most systems. Here systems that show every
staff are matched by position, whatever their names (a score may name the singers on the
first system and the voices after it); the other systems' visible staves are aligned, in
order, to the voices using a fuzzy match against all the names seen so far.
"""

import copy
import re
from collections import Counter
from dataclasses import dataclass, field

import music21 as m21

UNNAMED = "Voice"  # Audiveris's name for a staff whose name it could not read


@dataclass
class Voice:
    names: Counter = field(default_factory=Counter)
    first: str = UNNAMED  # name on the first system, where scores print the full name

    @property
    def name(self) -> str:
        if name_key(self.first):
            return self.first
        named = [(n, c) for n, c in self.names.items() if name_key(n)]
        return max(named, key=lambda nc: (nc[1], -len(nc[0])))[0] if named else UNNAMED

    @property
    def abbreviation(self) -> str | None:
        """The most common other name, as printed on the later systems."""
        named = [(n, c) for n, c in self.names.items() if name_key(n) and _plain(n) != _plain(self.name)]
        return max(named, key=lambda nc: (nc[1], -len(nc[0])))[0] if named else None

    def similarity(self, staff: str) -> float:
        named = [n for n in self.names if name_key(n)]
        return max((similarity(staff, n) for n in named), default=similarity(staff, UNNAMED))


def name_key(name: str) -> str:
    """Reduce a staff name to its first letter plus digits: 'Tenor 1' and 'T1 1' -> 't1'."""
    if name == UNNAMED:
        return ""
    s = name.lower().replace(" ", "")
    s = re.sub(r"(?<=[a-z])[li|](?=\d|$)", "1", s)  # OCR: 'Bl' -> 'b1'
    s = re.sub(r"(\d)\1$", r"\1", s)  # Sibelius style 'T1 1' -> 't1'
    digits = "".join(re.findall(r"\d", s))[:1]
    return s[:1] + digits if s[:1].isalpha() else ""


def _plain(name: str) -> str:
    s = re.sub(r"[^a-z0-9]", "", name.lower())
    return re.sub(r"(?<=[a-z])[li](?=\d|$)", "1", s)


def similarity(a: str, b: str) -> float:
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return 0.5  # unknown name: neutral
    pa, pb = _plain(a), _plain(b)
    if pa == pb:
        return 3.0
    if len(pa.rstrip("0123456789")) > 3 and len(pb.rstrip("0123456789")) > 3 \
            and not (pa.startswith(pb) or pb.startswith(pa)):
        return -10.0  # two different full words: 'Solo' vs 'Soprano', 'Baritone' vs 'Bass'
    if ka == kb:
        return 2.0
    if ka[0] == kb[0] and (len(ka) == 1 or len(kb) == 1):
        return 1.0  # 'Tenor' vs 'T1'
    return -10.0


def align(staves: list[str], voices: list[Voice]) -> list[int | None]:
    """Map each staff (top to bottom) to a voice index, preserving order. None = no match."""
    n, m = len(staves), len(voices)
    neg = float("-inf")
    best = [[neg] * (m + 1) for _ in range(n + 1)]
    move = [[None] * (m + 1) for _ in range(n + 1)]
    for j in range(m + 1):
        best[0][j] = 0.0
    for i in range(1, n + 1):
        for j in range(m + 1):
            options = [(best[i - 1][j] - 5.0, "new")]  # staff that matches no voice
            if j:
                options.append((best[i][j - 1], "skip"))  # voice hidden in this system
                options.append((best[i - 1][j - 1] + voices[j - 1].similarity(staves[i - 1]), "match"))
            best[i][j], move[i][j] = max(options, key=lambda o: o[0])
    result: list[int | None] = [None] * n
    i, j = n, m
    while i > 0:
        step = move[i][j]
        if step == "match":
            result[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif step == "skip":
            j -= 1
        else:
            i -= 1
    return result


def _system_starts(part: m21.stream.Part) -> list[int]:
    starts = []
    for idx, m in enumerate(part.getElementsByClass(m21.stream.Measure)):
        layouts = m.getElementsByClass((m21.layout.SystemLayout, m21.layout.PageLayout))
        if idx == 0 or any(getattr(x, "isNew", False) for x in layouts):
            starts.append(idx)
    return starts


def _is_hidden(measure: m21.stream.Measure) -> bool:
    return any(x.hidden for x in measure.getElementsByClass(m21.layout.StaffLayout))


def _is_percussion(part: m21.stream.Part) -> bool:
    return any(isinstance(c, m21.clef.PercussionClef) for c in part.recurse().getElementsByClass(m21.clef.Clef))


def merge_parts(score: m21.stream.Score, drop_percussion: bool = True) -> m21.stream.Score:
    parts = list(score.parts)
    measures = [list(p.getElementsByClass(m21.stream.Measure)) for p in parts]
    starts = _system_starts(parts[0])
    bounds = list(zip(starts, starts[1:] + [len(measures[0])]))

    # Visible staves per system, top to bottom (parts are listed in vertical order).
    systems = [[k for k in range(len(parts)) if not _is_hidden(measures[k][a])] for a, _ in bounds]

    # Voices: start from the fullest systems, then add any staff that matches none.
    voices: list[Voice] = []
    order = sorted(range(len(systems)), key=lambda s: -len(systems[s]))
    mapping: dict[int, dict[int, int]] = {}
    for s in order:
        names = [str(parts[k].partName or UNNAMED) for k in systems[s]]
        matched = list(range(len(names))) if len(names) == len(voices) else align(names, voices)
        for pos, (k, v) in enumerate(zip(systems[s], matched)):
            if v is None:
                # Insert a new voice after the voice matched just above, keeping vertical order.
                above = [matched[q] for q in range(pos) if matched[q] is not None]
                v = (max(above) + 1) if above else 0
                for t in mapping.values():
                    for kk in t:
                        t[kk] += t[kk] >= v
                for q in range(pos + 1, len(matched)):
                    if matched[q] is not None and matched[q] >= v:
                        matched[q] += 1
                voices.insert(v, Voice())
                matched[pos] = v
            voices[v].names[names[pos]] += 1
            if s == 0:
                voices[v].first = names[pos]
        mapping[s] = dict(zip(systems[s], matched))

    out = m21.stream.Score()
    for v, voice in enumerate(voices):
        sources = [next((k for k, vv in mapping[s].items() if vv == v), None) for s in range(len(bounds))]
        if drop_percussion and any(k is not None and _is_percussion(parts[k]) for k in sources):
            continue
        part = m21.stream.Part()
        part.partName = voice.name
        part.partAbbreviation = voice.abbreviation
        part.source_voice = voice  # for standardize_names
        current: dict[type, str] = {}
        for s, (a, b) in enumerate(bounds):
            k = sources[s]
            for idx in range(a, b):
                part.append(_measure_for(measures, k, idx, first=(idx == a), current=current))
        out.append(part)
    return out


VOICE_TYPES = {  # standard name and abbreviation of each way scores name a voice
    ("Soprano", "S"): ("s", "sop", "sopr", "soprano", "סופרן"),
    ("Mezzo-soprano", "Mz"): ("m", "mz", "mzs", "mez", "mezzo", "mezzosoprano", "מצו", "מצו-סופרן"),
    ("Alto", "A"): ("a", "alt", "alto", "contralto", "אלט"),
    ("Tenor", "T"): ("t", "ten", "tenor", "טנור"),
    ("Baritone", "Bar"): ("bar", "bari", "baritone", "בריטון"),
    ("Bass", "B"): ("b", "bs", "bass", "basso", "בס"),
}
STEMS = {stem: voice for voice, stems in VOICE_TYPES.items() for stem in stems}
ROLES = {"lead", "solo", "malesolo", "femalesolo", "descant", "piano"}  # kept as they are
SHARED = {"G": ("Soprano, Alto", "S A"), "F": ("Tenor, Bass", "T B")}  # two voices on one staff


def voice_type(name: str) -> tuple[str, str, str] | None:
    """Standard name, abbreviation and number of a staff name: 'T1 1' -> ('Tenor', 'T', '1')."""
    plain = re.sub(r"[^\w]", "", name.lower())
    stem = plain.rstrip("0123456789")
    digits = re.sub(r"\D", "", plain)[:1]
    if stem not in STEMS and stem[-1:] in ("l", "i") and stem[:-1] in STEMS:  # OCR: 'Tenorl', 'BI'
        stem, digits = stem[:-1], "1"
    return (*STEMS[stem], digits) if stem in STEMS else None


def _voice_from_range(part: m21.stream.Part) -> tuple[str, str, str]:
    """Guess the voice type of a part without one from its clef and pitches."""
    clef = next(iter(part.recurse().getElementsByClass(m21.clef.Clef)), None)
    sign, octave = (clef.sign, clef.octaveChange) if clef else ("G", 0)
    notes = list(part.recurse().notes)
    if any(n.isChord for n in notes) or any(m.voices for m in part.getElementsByClass(m21.stream.Measure)):
        return (*SHARED.get(sign, SHARED["G"]), "")
    pitches = sorted(p.midi for n in notes for p in n.pitches)
    middle = pitches[len(pitches) // 2] if pitches else 60
    if sign == "F":
        return (("Baritone", "Bar", "") if middle >= 50 else ("Bass", "B", ""))
    if octave < 0:
        return ("Tenor", "T", "")
    return (("Soprano", "S", "") if middle >= 67 else ("Mezzo-soprano", "Mz", "") if middle >= 64
            else ("Alto", "A", ""))


def standardize_names(score: m21.stream.Score) -> list[str]:
    """Give each part its standard voice name; return footnotes for the names it replaces.

    A score may name the singers on the first system; those go to a footnote. Parts that
    name no voice type anywhere get one from their clef and range, and roles such as
    'Lead' stay as they are.
    """
    named: list[tuple[m21.stream.Part, tuple[str, str, str] | None]] = []
    for part in score.parts:
        voice = part.source_voice
        types = (voice_type(n) for n, _ in voice.names.most_common())
        found = next((t for t in types if t), None)
        if found is None and re.sub(r"[^\w]", "", voice.name.lower()) in ROLES:
            named.append((part, None))
        else:
            named.append((part, found or _voice_from_range(part)))
    counts = Counter(t[0] for _, t in named if t and not t[2])
    numbers: Counter = Counter()
    originals = []
    for part, kind in named:
        if kind is None:
            continue
        name, abbreviation, number = kind
        if not number and counts[name] > 1:  # two parts of one voice type are numbered
            numbers[name] += 1
            number = str(numbers[name])
        part.partName = f"{name} {number}" if number else name
        part.partAbbreviation = abbreviation + number
        first = part.source_voice.first
        if len(re.sub(r"[^\w]|\d", "", first)) >= 2 and first != UNNAMED and voice_type(first) is None:
            originals.append(f"{part.partName} – {first}")
    return ["Original part names: " + ", ".join(originals)] if originals else []


def _signature(el) -> str:
    if isinstance(el, m21.clef.Clef):
        return f"{el.sign}{el.line}{el.octaveChange}"
    return str(el.sharps)


def _measure_for(measures, k: int | None, idx: int, first: bool, current: dict) -> m21.stream.Measure:
    """Copy measure idx of source part k. `current` tracks the clef and key in effect."""
    if k is None:
        # Voice not shown in this system: a full-measure rest, timed like the top staff.
        ref = measures[0][idx]
        m = m21.stream.Measure(number=ref.number)
        rest = m21.note.Rest(quarterLength=ref.barDuration.quarterLength)
        rest.fullMeasure = True
        m.append(rest)
        return m
    src = measures[k][idx]
    m = copy.deepcopy(src)
    # Layout comes from the engraver, not from the scan.
    m.removeByClass((m21.layout.StaffLayout, m21.layout.SystemLayout, m21.layout.PageLayout))
    for cls in (m21.clef.Clef, m21.key.KeySignature):
        own = [el for el in m.getElementsByClass(cls) if el.offset == 0]
        if own:
            el = own[0]
        elif first and (el := src.getContextByClass(cls)) is not None:
            # The previous measure may come from another source part: state it if it differs.
            el = copy.deepcopy(el)
            m.insert(0, el)
        else:
            continue
        if current.get(cls) == _signature(el):
            m.remove(el)  # unchanged: printing it again would look like a change
        current[cls] = _signature(el)
    return m
