"""Chord symbols (G, D7, Bbm7/Ab) over the top staff.

Audiveris reads few chord symbols and misreads some, so its own are dropped (tidy.py).
These come from the text of a notation program's PDF, placed by the measures and time
slots of Audiveris's project, or from Claude's reading of a scan (reader.py).
"""

import re
import zipfile
from fractions import Fraction
from pathlib import Path
from typing import NamedTuple

import music21 as m21
import pypdfium2 as pdfium

from .pagetext import SPACE, runs
from .textlayer import text_chars

CHORD_NAME = re.compile(r"[A-G][#b♯♭]?(?:m|maj|min|dim|aug|sus|add|M|\+|°|ø)?\d*"
                        r"(?:(?:[#b♯♭+-]|sus|add)\d+)*(?:/[A-G][#b♯♭]?)?")
ROOM = (6, 0.5)  # interlines above a system's top staff line that hold its chord symbols
MIN_SHARE = 0.25  # chords per measure below which chord-like names are rehearsal letters (A, B, C)
SYMBOL = re.compile(r"([A-G])([b#♭♯]?)([^/]*)(?:/([A-G])([b#♭♯]?))?")
ACCIDENTAL = {"b": "-", "♭": "-", "#": "#", "♯": "#", "": ""}  # music21 writes flats as '-'


class Chord(NamedTuple):
    measure: int  # index of the measure in its part
    quarters: float  # position from the start of the measure
    symbol: str  # as printed


def chord_symbol(text: str) -> m21.harmony.ChordSymbol | None:
    """The chord symbol a printed chord name stands for, printed as on the page."""
    m = SYMBOL.fullmatch(text.strip())
    if not m:
        return None
    root, alter, kind, bass, bass_alter = m.groups()
    kind = kind.replace("♭", "b").replace("♯", "#")
    figure = root + ACCIDENTAL[alter] + kind + (f"/{bass}{ACCIDENTAL[bass_alter]}" if bass else "")
    try:
        symbol = m21.harmony.ChordSymbol(figure)
    except Exception:  # music21 raises many kinds for figures it does not know
        return None
    symbol.chordKindStr = kind  # 'm7b5', not music21's own spelling of the kind
    symbol.chordStepModifications = []  # which the kind as printed already says ('(b5)' again)
    return symbol


def add_chords(score: m21.stream.Score, chords: list[Chord]) -> int:
    """Put the chord symbols over the top part; return how many."""
    measures = list(score.parts[0].getElementsByClass(m21.stream.Measure)) if score.parts else []
    added = 0
    for chord in chords:
        if not 0 <= chord.measure < len(measures) or (symbol := chord_symbol(chord.symbol)) is None:
            continue
        m = measures[chord.measure]
        at = min(max(Fraction(chord.quarters).limit_denominator(12), Fraction(0)), Fraction(m.highestTime))
        m.insert(at, symbol)
        added += 1
    return added


def _systems(omr: Path) -> list[tuple[int, list[tuple[float, float, list]]]]:
    """Per sheet: its picture width, and per system (top staff line, interline, measures as
    (left, right, [(x, quarters)]))."""
    out = []
    with zipfile.ZipFile(omr) as z:
        names = sorted((n for n in z.namelist() if re.fullmatch(r"sheet#\d+/sheet#\d+\.xml", n)),
                       key=lambda n: int(re.search(r"#(\d+)", n).group(1)))
        for name in names:
            xml = z.read(name).decode("utf-8")
            d = float(re.search(r'<interline [^>]*main="(\d+)"', xml).group(1))
            width = int(re.search(r'<picture width="(\d+)"', xml).group(1))
            sheet = []
            for system in re.findall(r"<system .*?</system>", xml, re.S):
                lines = re.search(r"<lines>.*?</lines>", system, re.S)
                top = min(float(y) for y in re.findall(r'y="(\d+(?:\.\d+)?)"', lines.group(0))) if lines else 0.0
                stacks = []
                for left, right, body in re.findall(r'<stack id="\d+" left="(\d+)" right="(\d+)"[^>]*>(.*?)</stack>',
                                                    system, re.S):
                    slots = [(int(left) + int(x), 4 * Fraction(t))
                             for x, t in re.findall(r'x-offset="(\d+)" time-offset="(\d+(?:/\d+)?)"', body)]
                    stacks.append((int(left), int(right), slots))
                sheet.append((top, d, stacks))
            out.append((width, sheet))
    return out


def _words(run) -> list[tuple[str, float]]:
    """(word, left edge) of a run of text."""
    out: list[tuple[str, float]] = []
    last = None
    for ch in run.chars:
        if not ch.c.strip() or not ch.c.isprintable():
            last = None if ch.c == " " else last
            continue
        if last is None or ch.x0 - last.x1 > SPACE * max(last.size, ch.size):
            out.append(("", ch.x0))
        out[-1] = (out[-1][0] + ch.c, out[-1][1])
        last = ch
    return out


def text_chords(pdf_path: Path, omr: Path, measures: int) -> list[Chord]:
    """Chord names printed as text above each system's top staff; sheet n must be page n."""
    systems = _systems(omr)
    if sum(len(stacks) for _, sheet in systems for _, _, stacks in sheet) != measures:
        return []  # the measures could not be told apart
    pdf = pdfium.PdfDocument(pdf_path)
    chords, first = [], 0
    for n, (width, sheet) in enumerate(systems):
        if n >= len(pdf):
            break
        k = width / pdf[n].get_width()  # pixels per point
        words = [(word, x * k, run.y * k) for run in runs(text_chars(pdf[n])) for word, x in _words(run)]
        for top, d, stacks in sheet:
            for word, x, y in words:
                if not (top - ROOM[0] * d <= y <= top - ROOM[1] * d and CHORD_NAME.fullmatch(word)):
                    continue
                k = next((k for k, (left, right, _) in enumerate(stacks) if left <= x < right), None)
                if k is not None:
                    slots = stacks[k][2] or [(x, Fraction(0))]
                    chords.append(Chord(first + k, float(min(slots, key=lambda s: abs(s[0] - x))[1]), word))
            first += len(stacks)
    return chords if len(chords) >= MIN_SHARE * measures else []
