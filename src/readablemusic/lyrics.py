"""Clean up OCR'd lyrics."""

import re
import unicodedata

import music21 as m21

from .parts import _system_starts

NIQQUD = re.compile(r"[֑-ׇ]")  # Hebrew cantillation marks and vowel points
OPEN = ("begin", "middle")  # syllables that a later syllable of the same word must follow
MAX_STRAY_SYLLABLES = 2  # a system's lyric line this short, of lone letters, is marks read as text
STRAY = re.compile(r"\s*[a-zA-Z]?\s*")  # fermatas read as 'm', dynamics as 'f'; a lone Hebrew letter is sung


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


def drop_stray_lines(score: m21.stream.Score) -> m21.stream.Score:
    """Drop lyric lines of a lone Latin letter or two, then number each system's lines from 1.

    Tesseract reads fermatas as 'm'; Audiveris gives each such mark a lyric line of its own,
    which pushes the real line to verse 2 in that system only. Run before parts are merged,
    while the score still knows where systems start.
    """
    for part in score.parts:
        measures = list(part.getElementsByClass(m21.stream.Measure))
        starts = _system_starts(part) + [len(measures)]
        for start, end in zip(starts, starts[1:]):
            lines: dict[int, list[tuple[m21.note.NotRest, m21.note.Lyric]]] = {}
            for m in measures[start:end]:
                for n in m.recurse().notes:
                    for lyric in n.lyrics:
                        lines.setdefault(lyric.number, []).append((n, lyric))
            kept = []
            for number in sorted(lines):
                found = lines[number]
                if len(found) <= MAX_STRAY_SYLLABLES and all(STRAY.fullmatch(ly.text or "") for _, ly in found):
                    for n, lyric in found:
                        n.lyrics.remove(lyric)
                else:
                    kept.append(found)
            for number, found in enumerate(kept, start=1):
                for _, lyric in found:
                    lyric.number = number
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
