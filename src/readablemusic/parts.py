"""Merge the parts Audiveris splits across systems back into one part per voice.

Audiveris joins staves of different systems into one part only when their OCR'd names
match exactly. With hidden empty staves and OCR noise ("B l", "Bl", "B1") a 9-voice score
can come out as 40+ parts, each hidden in most systems. Here each system's visible staves
are aligned, in order, to one list of voices using a fuzzy name match.
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

    @property
    def name(self) -> str:
        named = [(n, c) for n, c in self.names.items() if n != UNNAMED]
        return max(named, key=lambda nc: (nc[1], -len(nc[0])))[0] if named else UNNAMED


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
                options.append((best[i - 1][j - 1] + similarity(staves[i - 1], voices[j - 1].name), "match"))
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

    # Voices: start from the fullest system, then add any staff that matches none.
    voices: list[Voice] = []
    order = sorted(range(len(systems)), key=lambda s: -len(systems[s]))
    mapping: dict[int, dict[int, int]] = {}
    for s in order:
        names = [str(parts[k].partName or UNNAMED) for k in systems[s]]
        matched = align(names, voices)
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
        mapping[s] = dict(zip(systems[s], matched))

    out = m21.stream.Score()
    for v, voice in enumerate(voices):
        sources = [next((k for k, vv in mapping[s].items() if vv == v), None) for s in range(len(bounds))]
        if drop_percussion and any(k is not None and _is_percussion(parts[k]) for k in sources):
            continue
        part = m21.stream.Part()
        part.partName = voice.name
        for s, (a, b) in enumerate(bounds):
            k = sources[s]
            for idx in range(a, b):
                part.append(_measure_for(measures, k, idx, first=(idx == a)))
        out.append(part)
    return out


def _measure_for(measures, k: int | None, idx: int, first: bool) -> m21.stream.Measure:
    if k is None:
        # Voice not shown in this system: a full-measure rest, timed like the top staff.
        ref = measures[0][idx]
        m = m21.stream.Measure(number=ref.number)
        rest = m21.note.Rest(quarterLength=ref.barDuration.quarterLength)
        rest.fullMeasure = True
        m.append(rest)
        return m
    m = copy.deepcopy(measures[k][idx])
    m.removeByClass(m21.layout.StaffLayout)
    if first:
        # Restate clef and key, since the previous measure may come from another source part.
        src = measures[k][idx]
        for cls in (m21.clef.Clef, m21.key.KeySignature):
            if not m.getElementsByClass(cls) and (ctx := src.getContextByClass(cls)) is not None:
                m.insert(0, copy.deepcopy(ctx))
    return m
