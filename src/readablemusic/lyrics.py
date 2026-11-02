"""Clean up OCR'd lyrics."""

import re
import unicodedata

import music21 as m21

NIQQUD = re.compile(r"[֑-ׇ]")  # Hebrew cantillation marks and vowel points
OPEN = ("begin", "middle")  # syllables that a later syllable of the same word must follow


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
    for part in score.parts:
        close_words(part)
    return score


def close_words(part: m21.stream.Part) -> None:
    """End words that OCR left open, which engravers draw as hyphens up to the next syllable.

    'pa...' with an extension line is often read as the start of a word.
    """
    verses: dict[int, list[m21.note.Lyric]] = {}
    for n in part.recurse().notes:
        for lyric in n.lyrics:
            verses.setdefault(lyric.number, []).append(lyric)
    for lyrics in verses.values():
        for lyric, after in zip(lyrics, lyrics[1:] + [None]):
            if lyric.syllabic in OPEN and (lyric.text.endswith(("...", "…", "_"))
                                           or after is None or after.syllabic not in ("middle", "end")):
                lyric.syllabic = "single" if lyric.syllabic == "begin" else "end"
