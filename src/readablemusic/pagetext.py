"""Separate the text on the page from the music, before recognition.

Every line of text in a PDF's text layer is sorted by where it is and what it says:

- credits: title, subtitle, composer, lyricist, arranger, unlabeled names;
- rights and notes, which become footnotes;
- furniture: page numbers, running titles, dates, version stamps, which are dropped;
- music: anything else (tempo marks, "Verse 2", lyrics). Among the staves it is not even
  looked at; outside them it is returned, so that blanking the margins spares it.

The credits, footnotes and furniture are whitened on the page, so that recognition sees
only music, and the output prints them in one standard form, wherever the original had
them. Scans have no text layer: ocr.py reads their lines, which are sorted the same way.
"""

import difflib
import html
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import music21 as m21
import pypdfium2 as pdfium

from .textlayer import Char, text_chars

LABELS = {
    "composer": r"music\b|\b(composed|composer|melody)\b|לחן|מוזיקה",  # OCR can stick a letter to 'music'
    "lyricist": r"\b(words|lyrics|text|poem)\b|מי?לים|תמליל",
    "arranger": r"\b(arr|arranged|arrangement|arranger)\b|עיבוד|עיבד|מעבד",
}
CREDITS = ("title", "subtitle", "composer", "lyricist", "arranger", "creator")
RIGHTS = r"©|\(c\)|copyright|all rights|used by permission"
FURNITURE = (r"^(v|ver|version)\.?\s*\d|\bstock\b|\bno\.\s*\d"  # version and catalogue numbers
             r"|^\d{1,4}([./-]\d{1,4}){0,2}$")  # page numbers and dates
GAP = 1.5  # a horizontal gap of this many font heights separates two pieces of text on a line
SPACE = 0.2  # a gap of this many font heights between letters is a word space
CENTRE = 0.2  # share of the page width around the middle that counts as centred
SIMILAR = 0.7  # difflib ratio above which a text direction repeats text taken off the page
PAD = 1.0  # points around a line of text when it is whitened
MARGIN = 0.15  # share of the page width at the left that holds part names
PROSE_WORDS = 5  # an unlabeled line this long that ends like a sentence is not a credit
BELOW_LABEL = 2.5  # font heights under a label alone where its name may be


class Bounds(NamedTuple):
    """Where the music is on a page, in points from the top."""
    top: float  # of the area kept for recognition
    first: float  # first staff line
    last: float  # last staff line
    bottom: float  # of the area kept for recognition


@dataclass
class Item:
    kind: str  # one of CREDITS, rights, note, furniture, or music for text to keep on the page
    text: str
    page: int
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 in points from the top left
    size: float

    @property
    def name(self) -> str:
        """The name without its label: 'Music by: ABBA' -> 'ABBA'."""
        if self.kind not in LABELS:
            return self.text  # 'Edited by Harry Boulton' says what it says
        m = re.search(r"(?:\bby\b\s*:?|:)\s*(.+)$", self.text, re.I)
        if m:
            return m.group(1).strip()
        return re.sub(rf"^\W*({LABELS[self.kind]})\W*", "", self.text, flags=re.I).strip()


def _gap(a: Char, b: Char) -> float:
    return max(b.x0 - a.x1, a.x0 - b.x1)  # either direction: Hebrew runs leftwards


@dataclass
class Run:
    """Text on one line between large gaps."""
    chars: list[Char]

    @property
    def text(self) -> str:
        # Some programs place each letter on its own, with no space characters.
        out, last = "", None
        for ch in self.chars:
            if ch.c == " ":  # pdfium's generated line breaks between letters are not spaces
                out += " "
            elif ch.c.isprintable():
                if last and _gap(last, ch) > SPACE * max(last.size, ch.size):
                    out += " "
                out, last = out + ch.c, ch
        return " ".join(out.split())

    @property
    def size(self) -> float:
        return max(ch.size for ch in self.chars)

    @property
    def y(self) -> float:
        letters = [ch for ch in self.chars if ch.c.strip()]
        return sum(ch.y for ch in letters) / len(letters)

    @property
    def box(self) -> tuple[float, float, float, float]:
        letters = [ch for ch in self.chars if ch.c.strip()]
        half = self.size / 2
        return (min(c.x0 for c in letters) - PAD, min(c.y for c in letters) - half - PAD,
                max(c.x1 for c in letters) + PAD, max(c.y for c in letters) + half + PAD)

    @property
    def centre(self) -> float:
        return (self.box[0] + self.box[2]) / 2


@dataclass
class Line:
    """A line of text with no letters behind it: read by OCR, or joined from two."""
    text: str
    box: tuple[float, float, float, float]

    @property
    def size(self) -> float:
        return self.box[3] - self.box[1]

    @property
    def y(self) -> float:
        return (self.box[1] + self.box[3]) / 2

    @property
    def centre(self) -> float:
        return (self.box[0] + self.box[2]) / 2


def runs(chars: list[Char]) -> list[Run]:
    out: list[Run] = []
    for ch in chars:
        if not ch.c.strip():
            if out:
                out[-1].chars.append(ch)  # spaces have no useful box
            continue
        run = out[-1] if out else None
        letters = [c for c in run.chars if c.c.strip()] if run else []
        size = max([ch.size] + [c.size for c in letters])
        # Measured from the whole run: some PDFs store words in visual order, letters in logical order.
        span = Char(min(c.x0 for c in letters), max(c.x1 for c in letters), 0, 0, "") if letters else None
        if not letters or abs(ch.y - run.y) > size / 2 or _gap(span, ch) > GAP * size:
            out.append(Run([ch]))
        else:
            run.chars.append(ch)
    return [r for r in out if r.text]


def _stack(page_runs: list[Run], width: float) -> dict[str, str]:
    names = [r for r in page_runs if r.box[2] < MARGIN * width and any(c.isalpha() for c in r.text)]
    names.sort(key=lambda r: r.y)
    return {lower.text: upper.text for upper, lower in zip(names, names[1:])
            if lower.y - upper.y <= GAP * max(upper.size, lower.size)}


def stacked_names(pdf_path: Path) -> dict[str, str]:
    """Part names on two lines beside a staff, 'Tenor' over 'Lead', by the lower line.

    Audiveris reads only the lower line, of a staff that two voices share.
    """
    stacked: dict[str, str] = {}
    pdf = pdfium.PdfDocument(pdf_path)
    for n in range(len(pdf)):
        stacked |= _stack(runs(text_chars(pdf[n])), pdf[n].get_width())
    return stacked


def read_page_text(pdf_path: Path, bounds: list[Bounds | None]) -> list[Item]:
    """Sort the text layer of each page; pages with None in bounds hold no music and are skipped."""
    pdf = pdfium.PdfDocument(pdf_path)
    lines = [runs(text_chars(pdf[n])) if b is not None else [] for n, b in enumerate(bounds)]
    return sort_text(lines, bounds, [pdf[n].get_width() for n in range(len(bounds))])


def _label_alone(text: str) -> bool:
    """'Arrangement by', 'Arr.', and 'Lyrics & wmusic' with a word OCR spoiled: no name follows."""
    if not any(re.search(label, text, re.I) for label in LABELS.values()):
        return False
    rest = re.sub("|".join(LABELS.values()) + r"|\bby\b|\band\b", "", text, flags=re.I)
    return all(w.islower() for w in re.findall(r"\w+", rest))


def _join_labels(page_lines: list) -> list:
    """Give a label alone the name beside it or under it, as OCR reads them as separate lines."""
    lines = list(page_lines)
    for label in [line for line in lines if _label_alone(line.text)]:
        def beside(line) -> bool:
            return abs(line.y - label.y) < label.size / 2 and line.box[0] > label.box[0]

        def under(line) -> bool:
            return (0 < line.y - label.y < BELOW_LABEL * label.size
                    and line.box[0] < label.box[2] and label.box[0] < line.box[2])

        others = [line for line in lines if line is not label and not _label_alone(line.text)]
        name = min(filter(beside, others), key=lambda line: line.box[0], default=None) \
            or min(filter(under, others), key=lambda line: line.y, default=None)
        if name:
            joined = Line(f"{label.text}: {name.text}", _union(label.box, name.box))
            lines = [joined if line is label else line for line in lines if line is not name]
    return lines


def sort_text(lines: list[list], bounds: list[Bounds | None], widths: list[float]) -> list[Item]:
    """Sort the lines of each page, all of them in the units of its bounds and width."""
    items: list[Item] = []
    for n, page_bounds in enumerate(bounds):
        if page_bounds is not None:
            items += _classify(_join_labels(lines[n]), n, page_bounds, widths[n])
    titles = [i for i in items if i.kind == "subtitle"]
    if titles:
        max(titles, key=lambda i: i.size).kind = "title"
    _settle_later_pages(items, len(bounds) - 1)
    return items


def _classify(page_runs: list[Run], page: int, bounds: Bounds, width: float) -> list[Item]:
    items: list[Item] = []
    for run in page_runs:
        text, y = run.text, run.y
        above, near_top = y < bounds.top, bounds.top <= y < bounds.first
        below, near_bottom = y > bounds.bottom, bounds.last < y <= bounds.bottom
        if not (above or near_top or below or near_bottom):
            continue  # among the staves: music, whatever it says

        def add(*kinds: str) -> None:
            items.extend(Item(k, text, page, run.box, run.size) for k in kinds)

        labels = [k for k, label in LABELS.items() if re.search(label, text, re.I)]
        if re.search(RIGHTS, text, re.I):
            add("rights")
        elif (above or below) and re.search(FURNITURE, text, re.I):
            add("furniture")
        elif sum(c.isalpha() for c in text) < 2:
            continue
        elif above or (near_top and labels):
            if page > 0:
                add("later")
            elif items and re.match(r"(and|&)\s", text, re.I) and items[-1].kind in LABELS:
                items[-1].text += " " + text  # 'Arrangement by MO RECTOR' / 'and NANCY BERGMAN'
                items[-1].box = _union(items[-1].box, run.box)
            elif labels:
                add(*labels)
            elif len(text.split()) >= PROSE_WORDS and text.endswith((".", ",", ";")):
                add("note")  # a verse printed above the music
            else:
                offset = run.centre / width - 0.5
                add("subtitle" if abs(offset) < CENTRE else "creator")  # the page does not say what they did
        elif below:
            if text.startswith("*"):
                add("note")
            elif page > 0:
                add("later")
            else:
                add("note" if len(text.split()) >= 2 else "furniture")  # a lone word is a stray label
    return items


def _settle_later_pages(items: list[Item], later_pages: int) -> None:
    """Text outside the music on later pages is a running title if it repeats a credit or
    recurs from page to page; otherwise it belongs to the music ('Verse 2', 'cresc.')."""
    first_page = [i.text.lower() for i in items if i.page == 0 and i.kind in CREDITS]
    later = [i for i in items if i.kind == "later"]
    counts = Counter(i.text.lower() for i in later)
    for item in later:
        text = item.text.lower()
        recurs = counts[text] >= max(2, later_pages / 2)
        repeats = any(difflib.SequenceMatcher(None, text, t).ratio() >= SIMILAR for t in first_page)
        item.kind = "furniture" if recurs or repeats else "music"


def _union(a: tuple, b: tuple) -> tuple:
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def _names(items: list[Item], kind: str) -> list[str]:
    """The distinct names of one kind, in page order, without labels left empty by broken fonts."""
    names = [i.name for i in items if i.kind == kind and i.name.strip(" :")]
    return list(dict.fromkeys(names))


def header_lines(items: list[Item]) -> list[tuple[str, str, str]]:
    """The standard header: (credit type, justification, text), whatever the original looked like."""
    lines = [("title", "center", i.text) for i in items if i.kind == "title"]
    lines += [("subtitle", "center", i.text) for i in items if i.kind == "subtitle"]
    music, words = ", ".join(_names(items, "composer")), ", ".join(_names(items, "lyricist"))
    if music and music == words:
        lines.append(("composer", "right", f"Words and music: {music}"))
    else:
        if music:
            lines.append(("composer", "right", f"Music: {music}"))
        if words:
            lines.append(("lyricist", "left", f"Words: {words}"))
    if arranger := ", ".join(_names(items, "arranger")):
        lines.append(("arranger", "right", f"Arrangement: {arranger}"))
    lines += [("", "left", name) for name in _names(items, "creator")]
    return lines


def write_page_text(musicxml: Path, items: list[Item], footnotes: list[str] = ()) -> None:
    """Write the standard header and the footnotes into the MusicXML, as data and as text to print.

    Verovio prints all credits in the page header and ignores their font size, so the title
    is marked bold for the engraver to enlarge, and footnotes are data that it prints itself.
    """
    def e(text: str) -> str:
        return html.escape(text, quote=False)  # element text only

    xml = musicxml.read_text(encoding="utf-8")
    title = next((i.text for i in items if i.kind == "title"), None)
    xml = re.sub(r"\s*<work>.*?</work>|\s*<movement-title>.*?</movement-title>", "", xml, flags=re.S)
    if title:
        xml = xml.replace("<identification>", f"<work><work-title>{e(title)}</work-title></work>\n  <identification>", 1)
    ident = [f'<creator type="{kind}">{e(name)}</creator>'
             for kind in ("composer", "lyricist", "arranger") for name in _names(items, kind)]
    ident += [f"<creator>{e(name)}</creator>" for name in _names(items, "creator")]
    rights = list(dict.fromkeys(i.text for i in items if i.kind == "rights"))
    ident += [f"<rights>{e(r)}</rights>" for r in rights]
    notes = list(dict.fromkeys([i.text for i in items if i.kind == "note"] + list(footnotes)))
    if notes:
        fields = "".join(f'<miscellaneous-field name="footnote">{e(n)}</miscellaneous-field>' for n in notes)
        # MusicXML wants <miscellaneous> last in <identification>.
        xml = xml.replace("</identification>", f"<miscellaneous>{fields}</miscellaneous>\n  </identification>", 1)
    xml = re.sub(r"\s*<creator\b.*?</creator>|\s*<rights\b.*?</rights>", "", xml, flags=re.S)
    if ident:
        xml = xml.replace("<identification>", "<identification>\n    " + "\n    ".join(ident), 1)
    words = []
    for kind, justify, text in header_lines(items):
        credit_type = f"<credit-type>{kind}</credit-type>" if kind else ""
        bold = ' font-weight="bold"' if kind == "title" else ""
        words.append(f'<credit page="1">{credit_type}<credit-words justify="{justify}" valign="top"{bold}>'
                     f"{e(text)}</credit-words></credit>")
    xml = re.sub(r"\s*<credit\b.*?</credit>", "", xml, flags=re.S)
    if words:
        xml = xml.replace("<part-list>", "\n  ".join(words) + "\n  <part-list>", 1)
    musicxml.write_text(xml, encoding="utf-8")


def drop_repeated_text(score: m21.stream.Score, items: list[Item]) -> m21.stream.Score:
    """Remove what recognition still read of text taken off the page: directions that repeat
    it, such as running titles in the band kept for recognition, and copyright lines."""
    texts = [i.text.lower() for i in items if i.kind != "music"]
    for el in list(score.recurse().getElementsByClass(m21.expressions.TextExpression)):
        content = (el.content or "").lower()
        if re.search(RIGHTS, content) or any(difflib.SequenceMatcher(None, content, t).ratio() >= SIMILAR
                                             for t in texts):
            el.activeSite.remove(el)
    for n in score.recurse().notes:
        n.lyrics = [ly for ly in n.lyrics if not re.search(RIGHTS, (ly.text or "").lower())]
    return score
