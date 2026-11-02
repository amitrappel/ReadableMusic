"""Title, composer, lyricist, arranger and copyright from the PDF text layer.

The page is blanked around the music before recognition (cleanup.py), so the header and
footer are read from the PDF instead: the text above the first staff of the first page,
and copyright lines below its music. Lines with a label ("Music by", "arr.", "מילים") are
classified by it; of the rest, the largest centred line is the title, other centred lines
are subtitles, and a name on the right is the composer, as is the custom. Scans have no
text layer and get no credits.
"""

import difflib
import html
import re
from dataclasses import dataclass
from pathlib import Path

import music21 as m21
import pypdfium2 as pdfium

from .textlayer import Char, text_chars

LABELS = {
    "composer": r"\b(music|composed|composer|melody)\b|לחן|מוזיקה",
    "lyricist": r"\b(words|lyrics|text|poem)\b|מילים|תמליל",
    "arranger": r"\b(arr|arranged|arrangement|arranger)\b|עיבוד|עיבד|מעבד",
}
RIGHTS = r"©|\(c\)|copyright|all rights|used by permission"
NOT_CREDIT = r"^(v|ver|version)\.?\s*\d|\bstock\b|\bno\.\s*\d"  # version numbers, catalogue numbers
GAP = 1.5  # a horizontal gap of this many font sizes separates two pieces of text on a line
CENTRE = 0.2  # share of the page width around the middle that counts as centred


@dataclass
class Credit:
    kind: str  # title, subtitle, composer, lyricist, arranger, rights, or "" for an unlabeled name
    text: str  # as printed
    justify: str  # left, center or right
    size: float  # font size in points


SPACE = 0.2  # a gap of this many font heights between letters is a word space


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
        return sum(ch.y for ch in self.chars) / len(self.chars)

    @property
    def centre(self) -> float:
        return (min(ch.x0 for ch in self.chars) + max(ch.x1 for ch in self.chars)) / 2


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


def read_credits(pdf_path: Path, band: tuple[float, float, float]) -> list[Credit]:
    """Credits on the first page, from its music band in points from the top: the first
    staff line, the top of the area kept for OMR and its bottom.

    Between the top of that area and the first staff line, tempo marks, section names and
    chord symbols are common, so only labeled credits are taken from there.
    """
    first, top, _ = band  # the copyright may sit above the bottom of the area
    page = pdfium.PdfDocument(pdf_path)[0]
    width = page.get_width()
    chars = text_chars(page)
    credits: list[Credit] = []
    header = [r for r in runs([ch for ch in chars if ch.y < first])
              if sum(c.isalpha() for c in r.text) >= 2 and not re.search(NOT_CREDIT, r.text, re.I)]
    for run in header:
        text = run.text
        offset = run.centre / width - 0.5
        justify = "center" if abs(offset) < CENTRE else "right" if offset > 0 else "left"
        if credits and re.match(r"(and|&)\s", text, re.I) and credits[-1].justify == justify:
            credits[-1].text += " " + text  # 'Arrangement by MO RECTOR' / 'and NANCY BERGMAN'
            continue
        kinds = [k for k, label in LABELS.items() if re.search(label, text, re.I)]
        if re.search(RIGHTS, text, re.I):
            kinds = ["rights"]
        if not kinds and run.y > top:
            continue
        if not kinds:
            kinds = ["subtitle" if justify == "center" else "composer" if justify == "right" else ""]
        credits += [Credit(k, text, justify, run.size) for k in kinds]
    titles = [c for c in credits if c.kind == "subtitle"]
    if titles:
        max(titles, key=lambda c: c.size).kind = "title"
    # Copyright lines may sit right under the first system, inside the area kept for OMR.
    footer = [r for r in runs([ch for ch in chars if ch.y > first]) if re.search(RIGHTS, r.text, re.I)]
    credits += [Credit("rights", r.text, "center", r.size) for r in footer]
    return credits


def name(credit: Credit) -> str:
    """The name without its label: 'Music by: ABBA' -> 'ABBA'."""
    m = re.search(r"(?:\bby\b\s*:?|:)\s*(.+)$", credit.text, re.I)
    if m:
        return m.group(1)
    label = LABELS.get(credit.kind)
    return re.sub(rf"^\W*({label})\W*", "", credit.text, flags=re.I) if label else credit.text


FONT_SIZE = {"title": 22, "subtitle": 14}


def add_credits(musicxml: Path, credits: list[Credit]) -> None:
    """Write the credits into the MusicXML header, both as data and as text to print."""
    if not credits:
        return
    xml = musicxml.read_text(encoding="utf-8")
    def e(text: str) -> str:
        return html.escape(text, quote=False)  # element text only
    title = next((c.text for c in credits if c.kind == "title"), None)
    xml = re.sub(r"\s*<work>.*?</work>|\s*<movement-title>.*?</movement-title>", "", xml, flags=re.S)
    head = f"<work><work-title>{e(title)}</work-title></work>\n  " if title else ""
    xml = xml.replace("<identification>", head + "<identification>", 1)
    seen = set()
    ident = []
    for c in credits:
        if c.kind in ("title", "subtitle") or (c.kind, c.text) in seen:
            continue
        seen.add((c.kind, c.text))
        if c.kind == "rights":
            ident.append(f"<rights>{e(c.text)}</rights>")
        else:
            kind = f' type="{c.kind}"' if c.kind else ""
            if name(c).strip(" :"):  # a label alone, as from PDFs with broken fonts
                ident.append(f"<creator{kind}>{e(name(c))}</creator>")
    ident.sort(key=lambda s: s.startswith("<rights"))  # MusicXML lists creators first
    xml = re.sub(r"\s*<creator\b.*?</creator>|\s*<rights\b.*?</rights>", "", xml, flags=re.S)
    xml = xml.replace("<identification>", "<identification>\n    " + "\n    ".join(ident), 1)
    # Verovio prints every credit in the page header, so the copyright stays data only.
    # It ignores font sizes too; the engraver enlarges bold credits (see engrave.py).
    printed = set()
    words = []
    for c in credits:
        if c.kind == "rights" or c.text in printed:  # 'Words and Music by' is one line for two creators
            continue
        printed.add(c.text)
        kind = f"<credit-type>{c.kind}</credit-type>" if c.kind else ""
        bold = ' font-weight="bold"' if c.kind == "title" else ""
        words.append(f'<credit page="1">{kind}<credit-words justify="{c.justify}" valign="top" '
                     f'font-size="{FONT_SIZE.get(c.kind, 10)}"{bold}>{e(c.text)}</credit-words></credit>')
    xml = re.sub(r"\s*<credit\b.*?</credit>", "", xml, flags=re.S)
    xml = xml.replace("<part-list>", "\n  ".join(words) + "\n  <part-list>", 1)
    musicxml.write_text(xml, encoding="utf-8")


SIMILAR = 0.7  # difflib ratio above which a text direction repeats a credit


def drop_credit_text(score: m21.stream.Score, credits: list[Credit]) -> m21.stream.Score:
    """Remove text directions that repeat a credit, such as a running title on later pages,
    and copyright lines read as directions or lyrics."""
    texts = [c.text.lower() for c in credits]
    for el in list(score.recurse().getElementsByClass(m21.expressions.TextExpression)):
        content = (el.content or "").lower()
        if re.search(RIGHTS, content) or any(difflib.SequenceMatcher(None, content, t).ratio() >= SIMILAR
                                             for t in texts):
            el.activeSite.remove(el)
    for n in score.recurse().notes:
        n.lyrics = [ly for ly in n.lyrics if not re.search(RIGHTS, (ly.text or "").lower())]
    return score
