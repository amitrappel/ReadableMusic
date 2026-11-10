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


def test_lines_hold_four_measures_or_three_where_four_are_crowded():
    assert lines([10] * 8, [10] * 8, 100) == [4, 4]
    assert lines([10] * 10, [10] * 10, 100) == [4, 3, 3]  # no line of two at the end
    assert lines([10] * 5, [10] * 5, 100) == [3, 2]
    assert lines([22] * 6, [22] * 6, 100) == [3, 3]  # four take 88% of the line


def test_lines_start_every_four_measures_and_other_breaks_go():
    out = line_breaks(score(8))
    starts = [m.group(1) for m in re.finditer(r'<measure number="(\d+)">\s*<print new-system="yes"', out)]
    assert starts == ["5"]
    assert "new-page" not in out
    assert line_breaks(out) == out
