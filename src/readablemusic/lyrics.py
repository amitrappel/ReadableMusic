"""Clean up OCR'd lyrics."""

import re
import unicodedata

import music21 as m21

NIQQUD = re.compile(r"[֑-ׇ]")  # Hebrew cantillation marks and vowel points


def clean_text(text: str) -> str:
    """Undo OCR ligatures ('ﬁ' -> 'fi') and drop niqqud, which we never output."""
    return NIQQUD.sub("", unicodedata.normalize("NFKC", text)).strip()


def clean_lyrics(score: m21.stream.Score) -> m21.stream.Score:
    for n in score.recurse().notes:
        for lyric in list(n.lyrics):
            text = clean_text(lyric.text or "")
            if text:
                lyric.text = text
            else:
                n.lyrics.remove(lyric)
    return score
