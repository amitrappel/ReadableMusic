"""Undo clefs Audiveris read wrongly for a system or two.

A misread clef moves every note of its staff by the same number of staff steps, so the notes
land far from the rest of the part. A run of measures in another clef is reread under the
part's main clef when it is short and rereading brings it nearer the rest of the part. Real
clef changes (a tenor line moving to treble for a page) last longer and are kept.
"""

import copy
from statistics import median

import music21 as m21

MAX_STRAY_MEASURES = 12  # a clef read wrongly lasts a system or two; real changes last longer
CLEF_GAIN = 3  # semitones by which rereading must bring a run nearer to the rest of its part


def _key(clef: m21.clef.Clef | None) -> tuple | None:
    return (clef.sign, clef.line, clef.octaveChange) if clef else None


def _bottom_line(clef: m21.clef.Clef) -> int:
    """Diatonic number of the staff's bottom line; music21's own lowestLine misses some octave marks."""
    return m21.clef.clefFromString(f"{clef.sign}{clef.line}").lowestLine + 7 * clef.octaveChange


def _notes(measure: m21.stream.Measure) -> list[m21.note.NotRest]:
    return [n for n in measure.recurse().notes if not isinstance(n, m21.harmony.Harmony)]


def _pitches(measure: m21.stream.Measure) -> list[m21.pitch.Pitch]:
    return [p for n in _notes(measure) for p in n.pitches]


def moved(pitch: m21.pitch.Pitch, steps: int, key: m21.key.KeySignature) -> m21.pitch.Pitch:
    """The pitch printed on the same staff position under a clef `steps` diatonic steps away."""
    if steps % 7 == 0:
        new = copy.deepcopy(pitch)
        new.octave = pitch.octave + steps // 7
        return new
    from_key = key.accidentalByStep(pitch.step)
    printed = pitch.accidental.alter if pitch.accidental else 0
    new = m21.pitch.Pitch()
    new.diatonicNoteNum = pitch.diatonicNoteNum + steps
    # The key gives the new step its accidental, unless the page printed one against the key.
    alter = key.accidentalByStep(new.step) if printed == (from_key.alter if from_key else 0) else pitch.accidental
    if alter is not None and alter.alter != 0:
        new.accidental = m21.pitch.Accidental(alter.alter)
    return new


def _runs(part: m21.stream.Part) -> list[tuple[m21.clef.Clef, list[m21.stream.Measure]]]:
    """(clef, measures) of each run of measures that start in one clef, in order."""
    runs = []
    for m in part.getElementsByClass(m21.stream.Measure):
        # The context search skips a clef at the very start of the measure itself.
        clef = m.clef or m.getContextByClass(m21.clef.Clef)
        if runs and _key(runs[-1][0]) == _key(clef):
            runs[-1][1].append(m)
        else:
            runs.append((clef, [m]))
    return runs


def _is_stray(clef: m21.clef.Clef, measures: list, main: m21.clef.Clef, centre: float) -> bool:
    if len(measures) > MAX_STRAY_MEASURES:
        return False
    if clef.sign == "G" and clef.octaveChange == 1:
        return True  # an octave-up treble clef is never sung from
    pitches = [p for m in measures for p in _pitches(m)]
    if not pitches:
        return False
    steps = _bottom_line(main) - _bottom_line(clef)
    key = measures[0].getContextByClass(m21.key.KeySignature) or m21.key.KeySignature(0)
    before = median(p.ps for p in pitches)
    after = median(moved(p, steps, key).ps for p in pitches)
    return abs(before - centre) - abs(after - centre) >= CLEF_GAIN


def fix_clefs(score: m21.stream.Score, move: bool = True) -> int:
    """Reread stray clef runs under each part's main clef, in place; return how many runs.
    With move False the pitches are right (Claude read them off the page), and a short run
    in another clef only takes the main clef's sign."""
    fixed = 0
    for part in score.parts:
        runs = [(clef, ms) for clef, ms in _runs(part) if clef is not None]
        counts: dict[tuple, int] = {}
        for clef, measures in runs:
            counts[_key(clef)] = counts.get(_key(clef), 0) + sum(len(_pitches(m)) for m in measures)
        if len(counts) < 2:
            continue
        main_key = max(counts, key=counts.get)
        main = next(clef for clef, _ in runs if _key(clef) == main_key)
        rest = [p.ps for clef, ms in runs if _key(clef) == main_key for m in ms for p in _pitches(m)]
        if not rest:
            continue
        centre = median(rest)
        for clef, measures in runs:
            if _key(clef) == main_key or not (_is_stray(clef, measures, main, centre) if move
                                              else len(measures) <= MAX_STRAY_MEASURES):
                continue
            steps = _bottom_line(main) - _bottom_line(clef)
            for m in measures if move else []:
                key = m.getContextByClass(m21.key.KeySignature) or m21.key.KeySignature(0)
                for n in _notes(m):
                    if isinstance(n, m21.chord.Chord):
                        n.pitches = tuple(moved(p, steps, key) for p in n.pitches)
                    elif isinstance(n, m21.note.Note):
                        n.pitch = moved(n.pitch, steps, key)
            for m in measures:
                for c in list(m.recurse().getElementsByClass(m21.clef.Clef)):
                    c.activeSite.replace(c, copy.deepcopy(main))
            fixed += 1
        _drop_repeated_clefs(part)
    return fixed


def _drop_repeated_clefs(part: m21.stream.Part) -> None:
    current = None
    for m in part.getElementsByClass(m21.stream.Measure):
        for c in list(m.recurse().getElementsByClass(m21.clef.Clef)):
            if current is not None and _key(c) == _key(current):
                c.activeSite.remove(c)
            else:
                current = c
