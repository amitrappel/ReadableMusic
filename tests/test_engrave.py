import re

from readablemusic.engrave import line_breaks, lines

HEAD = '<?xml version="1.0" encoding="utf-8"?>\n'


def score(measures: int) -> str:
    bars = "".join(
        f'<measure number="{k}">'
        + ('<attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>'
           '<clef><sign>G</sign><line>2</line></clef></attributes>' if k == 1 else "")
        + ('<print new-page="yes"/>' if k == 3 else "")
        + "<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>whole</type></note>"
        + "</measure>" for k in range(1, measures + 1))
    return (HEAD + '<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Voice</part-name>'
            f'</score-part></part-list><part id="P1">{bars}</part></score-partwise>')


def test_lines_hold_more_short_measures_than_long_ones():
    assert lines([10] * 12, [10] * 12, 100) == [6, 6]
    assert lines([5] * 24, [5] * 24, 100) == [12, 12]
    assert lines([30] * 4, [30] * 4, 100) == [2, 2]
    assert lines([60] * 3, [60] * 3, 100) == [1, 1, 1]  # two would not fit
    # A line starts at a rehearsal mark or a canon's entry where that costs little.
    assert lines([10] * 12, [10] * 12, 100, {5}) == [5, 7]
    assert lines([10] * 12, [10] * 12, 100, {2}) == [6, 6]


def test_lines_are_marked_and_other_breaks_go():
    out = line_breaks(score(20))  # bars of a whole note each, ten to a line
    starts = [m.group(1) for m in re.finditer(r'<measure number="(\d+)">\s*<print new-system="yes"', out)]
    assert starts == ["11"]
    assert "new-page" not in out
    assert line_breaks(out) == out
