"""Compare a recognised score with its known answer.

Notes are matched as (measure index, offset in measure, pitch, duration) per staff, which
tolerates a wrong note without shifting everything after it. Lyrics are compared as one
syllable sequence per staff.

Usage: uv run python eval/score.py TRUTH.musicxml RESULT.mxl
"""

import difflib
import sys
from collections import Counter
from dataclasses import dataclass

import music21 as m21


@dataclass
class Result:
    note_precision: float
    note_recall: float
    lyrics: float
    staves_truth: int
    staves_found: int

    @property
    def note_f1(self) -> float:
        p, r = self.note_precision, self.note_recall
        return 2 * p * r / (p + r) if p + r else 0.0


def _notes(part: m21.stream.Part) -> Counter:
    found = Counter()
    for i, measure in enumerate(part.getElementsByClass(m21.stream.Measure)):
        for n in measure.recurse().notes:
            offset = float(n.getOffsetInHierarchy(measure))
            for pitch in n.pitches:
                found[(i, offset, pitch.midi, float(n.quarterLength))] += 1
    return found


def _lyrics(part: m21.stream.Part) -> list[str]:
    return [n.lyric.strip().lower() for n in part.recurse().notes if n.lyric]


def compare(truth_path: str, result_path: str) -> Result:
    truth, result = m21.converter.parse(truth_path), m21.converter.parse(result_path)
    matched = n_truth = n_found = 0
    lyric_scores = []
    for t, r in zip(truth.parts, result.parts):
        tn, rn = _notes(t), _notes(r)
        matched += sum((tn & rn).values())
        n_truth += sum(tn.values())
        n_found += sum(rn.values())
        tl, rl = _lyrics(t), _lyrics(r)
        if tl:
            lyric_scores.append(difflib.SequenceMatcher(None, " ".join(tl), " ".join(rl)).ratio())
    for t in truth.parts[len(result.parts):]:
        n_truth += sum(_notes(t).values())
        if _lyrics(t):
            lyric_scores.append(0.0)
    for r in result.parts[len(truth.parts):]:
        n_found += sum(_notes(r).values())
    return Result(
        note_precision=matched / n_found if n_found else 0.0,
        note_recall=matched / n_truth if n_truth else 0.0,
        lyrics=sum(lyric_scores) / len(lyric_scores) if lyric_scores else 1.0,
        staves_truth=len(truth.parts),
        staves_found=len(result.parts),
    )


if __name__ == "__main__":
    r = compare(sys.argv[1], sys.argv[2])
    print(f"notes F1 {r.note_f1:.1%} (precision {r.note_precision:.1%}, recall {r.note_recall:.1%}), "
          f"lyrics {r.lyrics:.1%}, staves {r.staves_found}/{r.staves_truth}")
