"""Remove recognised items that a cappella users do not want in the output."""

import re

import music21 as m21

MAX_DIRECTION_WORDS = 4  # longer "directions" are titles and credits that slipped through
CHORD_NAME = re.compile(r"[A-G][#b]?(m|maj|min|dim|aug|sus)?\d*(/[A-G][#b]?)?")  # read as text


def tidy(score: m21.stream.Score) -> m21.stream.Score:
    """Drop chord symbols (also when read as text) and long text directions, in place."""
    for el in list(score.recurse().getElementsByClass((m21.harmony.Harmony, m21.expressions.TextExpression))):
        if (isinstance(el, m21.harmony.Harmony) or len(el.content.split()) > MAX_DIRECTION_WORDS
                or CHORD_NAME.fullmatch(el.content.strip())):
            el.activeSite.remove(el)
    return score
