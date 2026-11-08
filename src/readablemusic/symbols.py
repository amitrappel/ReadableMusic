"""Correct accidentals and ties with the vector drawing of PDFs exported from notation software.

Notation programs print music symbols as characters of a music font and draw ties as
filled curves. Audiveris reads the rendered page and misses some of them: an accidental
that touches a lyric is taken into the text, and a tie that runs along a staff line is
lost with it. Each accidental character is matched to the notehead to its right at the
height of its origin, and each flat curve to the noteheads at its ends; what Audiveris
lacks or misread is written into its project (.omr), which is then exported again (see
audiveris.export). A tie across a system break is drawn in two halves, which are paired
by part and pitch.

Fonts: Finale's Maestro and the fonts that copy its layout (notehead 'œ', sharp '#'), and
SMuFL fonts (Leland, Bravura, Finale Maestro). MuseScore 2 and LilyPond fonts are not read.
"""

import ctypes
import re
import shutil
import zipfile
from pathlib import Path
from typing import NamedTuple

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

FINALE_ACCIDENTALS = {"#": "SHARP", "b": "FLAT", "n": "NATURAL", "Ü": "DOUBLE_SHARP", "º": "DOUBLE_FLAT"}
FINALE_NOTEHEAD = "œ"
SMUFL_ACCIDENTALS = {"": "SHARP", "": "FLAT", "": "NATURAL", "": "DOUBLE_SHARP",
                     "": "DOUBLE_FLAT"}
ATTRS = re.compile(r'([\w-]+)="([^"]*)"')
BOUNDS = re.compile(r'\s*<bounds x="(-?\d+)" y="(-?\d+)" w="(\d+)" h="(\d+)"/>')
RELATION = re.compile(r'<relation source="(\d+)" target="(\d+)">\s*<([\w-]+)([^>]*)/>')
# In interlines:
SAME_HEIGHT = 0.4  # between an accidental's origin and the centre of its notehead
ACCIDENTAL_REACH = 1.6  # from an accidental's right edge to its notehead (chords stack them)
TIE_REACH = 1.5  # from the end of a tie to its notehead
TIE_WIDTH = 0.8  # least width of a tie
STAFF_END = 2.0  # from the end of half a tie to the end of its staff
FLAT = 0.5  # a tie's height is at most this share of its width


class Glyph(NamedTuple):
    shape: str
    x0: float  # left, right and origin height in PDF points from the top left
    x1: float
    y: float


class Curve(NamedTuple):
    left: tuple[float, float]  # end points in PDF points from the top left
    right: tuple[float, float]
    above: bool  # arches upwards


class Inter(NamedTuple):
    tag: str
    attrs: dict
    x: int  # bounds in sheet pixels
    y: int
    w: int
    h: int
    at: int  # position in the sheet XML

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


class Half(NamedTuple):
    """Half of a tie across a system break: side LEFT leaves its system at the end, from
    head; side RIGHT enters the next one at the start, to head."""
    sheet: int
    system: int
    part: str
    side: str
    head: Inter
    ends: tuple | None  # (x1, y1, x2, y2, above) of a curve to add; None for Audiveris's own half
    slur: Inter | None


def accidentals(page: pdfium.PdfPage) -> list[Glyph]:
    """The accidentals printed as music-font characters, by their origin, which notation
    fonts put at the height of the note."""
    textpage, height = page.get_textpage(), page.get_height()
    chars = []
    for i in range(textpage.count_chars()):
        name = ctypes.create_string_buffer(128)
        pdfium_c.FPDFText_GetFontInfo(textpage.raw, i, name, len(name), None)
        chars.append((name.value, i, textpage.get_text_range(i, 1)))
    finale = {font for font, _, c in chars if c == FINALE_NOTEHEAD}
    glyphs = []
    for font, i, c in chars:
        shape = FINALE_ACCIDENTALS.get(c) if font in finale else SMUFL_ACCIDENTALS.get(c)
        if shape:
            x, y = ctypes.c_double(), ctypes.c_double()
            pdfium_c.FPDFText_GetCharOrigin(textpage.raw, i, x, y)
            left, _, right, _ = textpage.get_charbox(i)
            glyphs.append(Glyph(shape, left, right, height - y.value))
    return glyphs


def curves(page: pdfium.PdfPage) -> list[Curve]:
    """The flat filled curves on the page, which notation programs draw ties and slurs with."""
    height = page.get_height()
    found = []
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_PATH], max_depth=4):
        segments = [pdfium_c.FPDFPath_GetPathSegment(obj.raw, j)
                    for j in range(pdfium_c.FPDFPath_CountSegments(obj.raw))]
        if not any(pdfium_c.FPDFPathSegment_GetType(s) == pdfium_c.FPDF_SEGMENT_BEZIERTO for s in segments):
            continue
        points = []
        for s in segments:
            x, y = ctypes.c_float(), ctypes.c_float()
            pdfium_c.FPDFPathSegment_GetPoint(s, x, y)
            point, holder = (x.value, y.value), obj
            while holder is not None:  # into page space, through any enclosing forms
                point = holder.get_matrix().on_point(*point)
                holder = holder.container
            points.append((point[0], height - point[1]))
        left, right = min(points), max(points)
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        ends = (left[1] + right[1]) / 2
        if max(ys) - min(ys) <= FLAT * (max(xs) - min(xs)):
            found.append(Curve(left, right, above=ends - min(ys) > max(ys) - ends))
    return found


def _inters(xml: str, tag: str) -> list[Inter]:
    out = []
    for m in re.finditer(rf"<{tag} ([^>]*)>", xml):
        if (b := BOUNDS.match(xml, m.end())):
            out.append(Inter(tag, dict(ATTRS.findall(m.group(1))), *map(int, b.groups()), m.start()))
    return out


def _staves(xml: str) -> dict[str, tuple[int, str, int, int]]:
    """Staff id -> (system on the sheet, part in the system, left, right)."""
    systems = [m.start() for m in re.finditer(r"<system ", xml)]
    parts = [(m.start(), m.group(1)) for m in re.finditer(r'<part id="(\d+)"', xml)]
    out = {}
    for m in re.finditer(r'<staff id="(\d+)" left="(\d+)" right="(\d+)"', xml):
        system = sum(at < m.start() for at in systems) - 1
        part = max((p for p in parts if p[0] < m.start()), default=(0, "0"))[1]
        out[m.group(1)] = (system, part, int(m.group(2)), int(m.group(3)))
    return out


class _Sheet:
    """An Audiveris sheet to which inters and relations are added."""

    def __init__(self, xml: str):
        self.xml = xml
        self.next_id = int(re.search(r'last-persistent-id="(\d+)"', xml).group(1)) + 1
        self.edits: list[tuple[int, int, str]] = []  # (position, characters replaced, text)

    def reserve(self) -> str:
        self.next_id += 1
        return str(self.next_id - 1)

    def add(self, near: Inter, inter: str, relations: list[tuple[str, str, str]], new: str | None = None) -> str:
        """Add inter (XML with {id} for its id) in the system of near, and relations
        (source, target, element) with {id} for the new id; return the id."""
        new = new or self.reserve()
        self.edits.append((self.xml.index("</inters>", near.at), 0, "  " + inter.format(id=new) + "\n        "))
        for source, target, element in relations:
            text = (f'  <relation source="{source.format(id=new)}" target="{target.format(id=new)}">\n'
                    f"            {element}\n          </relation>\n        ")
            self.edits.append((self.xml.index("</relations>", near.at), 0, text))
        return new

    def insert(self, at: int, text: str) -> None:
        self.edits.append((at, 0, text))

    def set(self, inter: Inter, name: str, value: str) -> None:
        old = f'{name}="{inter.attrs[name]}"'
        self.edits.append((self.xml.index(old, inter.at), len(old), f'{name}="{value}"'))

    def result(self) -> str:
        xml = self.xml
        for at, length, text in sorted(self.edits, key=lambda e: e[0], reverse=True):  # stable: keeps order at one spot
            xml = xml[:at] + text + xml[at + length:]
        return re.sub(r'last-persistent-id="\d+"', f'last-persistent-id="{self.next_id - 1}"', xml, count=1)


def _fix_accidentals(sheet: _Sheet, glyphs: list[Glyph], k: float, interline: float) -> int:
    heads = _inters(sheet.xml, "head")
    alters = {a.attrs["id"]: a for a in _inters(sheet.xml, "alter")}
    keys = _inters(sheet.xml, "key")
    relations = RELATION.findall(sheet.xml)
    alter_of = {target: alters[source] for source, target, kind, _ in relations
                if kind == "alter-head" and source in alters}
    fixed = 0
    for g in glyphs:
        x0, x1, y = g.x0 / k, g.x1 / k, g.y / k
        if any(key.x - interline / 2 <= x0 <= key.x + key.w + interline / 2
               and key.y - interline <= y <= key.y + key.h + interline for key in keys):
            continue  # a key signature
        near = [h for h in heads if abs(h.cy - y) <= SAME_HEIGHT * interline
                and -interline / 2 <= h.x - x1 <= ACCIDENTAL_REACH * interline]
        if not near:
            continue
        head = min(near, key=lambda h: h.x)
        hid = head.attrs["id"]
        if hid in alter_of:
            if (old := alter_of[hid]) is not None and old.attrs["shape"] != g.shape:
                sheet.set(old, "shape", g.shape)
                fixed += 1
            continue
        if any(a.x < x1 and x0 < a.x + a.w and abs(a.cy - y) < interline for a in alters.values()):
            continue  # Audiveris read it, but for another notehead
        box = f'<bounds x="{round(x0)}" y="{round(head.y - interline)}" w="{max(1, round(x1 - x0))}" h="{round(head.h + 2 * interline)}"/>'
        sheet.add(head, f'<alter pitch="{head.attrs["pitch"]}" shape="{g.shape}" grade="0.9" '
                        f'staff="{head.attrs["staff"]}" id="{{id}}">\n            {box}\n          </alter>',
                  [("{id}", hid, f'<alter-head dx="{(head.x - x1) / interline:.3f}" dy="0" grade="0.9"/>')])
        alter_of[hid] = None  # one accidental per notehead
        fixed += 1
    return fixed


def _slur(x1: float, y1: float, x2: float, y2: float, above: bool, interline: float, extra: str = "") -> str:
    x1, y1, x2, y2 = round(x1), round(y1), round(x2), round(y2)
    bend = -interline if above else interline
    top, bottom = min(y1, y2, y1 + bend), max(y1, y2, y1 + bend)
    shape = "SLUR_ABOVE" if above else "SLUR_BELOW"
    return (f'<slur above="{str(above).lower()}" tie="true"{extra} shape="{shape}" grade="0.9" id="{{id}}">\n'
            f'            <bounds x="{x1}" y="{top}" w="{x2 - x1}" h="{bottom - top}"/>\n'
            f'            <curve x1="{x1}" y1="{y1}" ctrlx1="{x1 + (x2 - x1) / 4:.1f}" ctrly1="{y1 + bend:.1f}" '
            f'ctrlx2="{x2 - (x2 - x1) / 4:.1f}" ctrly2="{y2 + bend:.1f}" x2="{x2}" y2="{y2}"/>\n'
            f'          </slur>')


def _fix_ties(sheet: _Sheet, ties: list[Curve], k: float, interline: float, n: int) -> tuple[int, list[Half]]:
    """Add the ties within systems of sheet n; return how many, and the halves of ties across
    system breaks: those Audiveris has without their other half, and those it lacks."""
    heads = _inters(sheet.xml, "head")
    by_id = {h.attrs["id"]: h for h in heads}
    staves = _staves(sheet.xml)
    slurs = {s.attrs["id"]: s for s in _inters(sheet.xml, "slur")}
    relations = RELATION.findall(sheet.xml)
    slurred = {(target, attrs) for source, target, kind, attrs in relations
               if kind == "slur-head" and source in slurs}
    reach = TIE_REACH * interline

    def distance(h: Inter, x: float, y: float) -> float:
        return max(0.0, h.x - x, x - h.x - h.w) + abs(h.cy - y)

    def has_slur(h: Inter, side: str) -> bool:
        return any(t == h.attrs["id"] and f'side="{side}"' in s for t, s in slurred)

    def at_edge(h: Inter, side: str) -> bool:
        """Whether h is the last (LEFT) or the first (RIGHT) notehead of its staff."""
        sign = 1 if side == "LEFT" else -1
        return h.attrs["staff"] in staves and not has_slur(h, side) and not any(
            o.attrs["staff"] == h.attrs["staff"] and sign * (o.cx - h.cx) > interline / 2 for o in heads)

    def half(h: Inter, side: str, ends: tuple | None, slur: Inter | None) -> Half:
        system, part, _, _ = staves[h.attrs["staff"]]
        return Half(n, system, part, side, h, ends, slur)

    fixed, halves = 0, []
    for c in ties:
        (lx, ly), (rx, ry) = [(x / k, y / k) for x, y in (c.left, c.right)]
        if rx - lx < TIE_WIDTH * interline:
            continue
        lefts = [h for h in heads if distance(h, lx, ly) <= reach and h.cx <= lx + interline / 2]
        rights = [h for h in heads if distance(h, rx, ry) <= reach and h.cx >= rx - interline / 2]
        pairs = [(distance(a, lx, ly) + distance(b, rx, ry), a, b) for a in lefts for b in rights
                 if a is not b and a.attrs["staff"] == b.attrs["staff"] and a.attrs["pitch"] == b.attrs["pitch"]]
        if not pairs:
            # Half a tie, if it runs from the last note to the end of the staff, or from the
            # start of the staff to the first note; a slur's half is told apart by pairing.
            ends = [h for h in lefts if at_edge(h, "LEFT") and rx >= staves[h.attrs["staff"]][3] - STAFF_END * interline]
            starts = [h for h in rights if at_edge(h, "RIGHT") and lx < h.x]
            if ends:
                halves.append(half(min(ends, key=lambda h: distance(h, lx, ly)), "LEFT", (lx, ly, rx, ry, c.above), None))
            elif starts:
                halves.append(half(min(starts, key=lambda h: distance(h, rx, ry)), "RIGHT", (lx, ly, rx, ry, c.above), None))
            continue
        _, a, b = min(pairs, key=lambda p: p[0])
        between = [h for h in heads if h.attrs["staff"] == a.attrs["staff"] and a.cx + interline / 2 < h.cx < b.cx - interline / 2]
        if between or has_slur(a, "LEFT") or has_slur(b, "RIGHT"):
            continue  # notes in between make it a slur; or Audiveris has a tie or slur there
        sheet.add(a, _slur(lx, ly, rx, ry, c.above, interline),
                  [("{id}", a.attrs["id"], '<slur-head side="LEFT" grade="0.9"/>'),
                   ("{id}", b.attrs["id"], '<slur-head side="RIGHT" grade="0.9"/>')])
        slurred |= {(a.attrs["id"], 'side="LEFT"'), (b.attrs["id"], 'side="RIGHT"')}
        fixed += 1
    # Audiveris's own halves that still lack their other half
    for sid, s in slurs.items():
        ends = [(target, attrs) for source, target, kind, attrs in relations if source == sid and kind == "slur-head"]
        if (s.attrs.get("tie") == "true" and len(ends) == 1 and ends[0][0] in by_id
                and by_id[ends[0][0]].attrs["staff"] in staves
                and "left-extension" not in s.attrs and "right-extension" not in s.attrs):
            halves.append(half(by_id[ends[0][0]], "LEFT" if 'side="LEFT"' in ends[0][1] else "RIGHT", None, s))
    return fixed, halves


def _join_halves(sheets: dict[int, _Sheet], halves: list[Half], interlines: dict[int, float]) -> int:
    """Pair each LEFT half with the RIGHT half of the same part and pitch at the start of the
    next system, add the halves Audiveris lacks, and return how many ties were completed.
    Halves on one sheet are linked as Audiveris links them; across pages it joins them itself."""
    systems = {n: 1 + max((s for s, *_ in _staves(sheet.xml).values()), default=0) for n, sheet in sheets.items()}
    starts = {(h.sheet, h.system, h.part, h.head.attrs["pitch"]): h for h in halves if h.side == "RIGHT"}
    joined = 0
    for h in (h for h in halves if h.side == "LEFT"):
        following = (h.sheet, h.system + 1) if h.system + 1 < systems[h.sheet] else (h.sheet + 1, 0)
        other = starts.get((*following, h.part, h.head.attrs["pitch"]))
        if other is None or (h.slur and other.slur):
            continue
        ids = [x.slur.attrs["id"] if x.slur else sheets[x.sheet].reserve() for x in (h, other)]
        for x, partner, link in ((h, ids[1], "right-extension"), (other, ids[0], "left-extension")):
            extra = f' {link}="{partner}"' if h.sheet == other.sheet else ""
            sheet = sheets[x.sheet]
            if x.slur is None:
                sheet.add(x.head, _slur(*x.ends, interlines[x.sheet], extra),
                          [("{id}", x.head.attrs["id"], f'<slur-head side="{x.side}" grade="0.9"/>')],
                          ids[0] if x is h else ids[1])
            elif extra:
                sheet.insert(x.slur.at + len("<slur"), extra)
        joined += 1
    return joined


def fix_symbols(omr: Path, pdf_path: Path) -> tuple[int, int]:
    """Add or correct accidentals and add ties in omr from the PDF's drawing; return how
    many of each. Sheet n of the project must be page n of the PDF."""
    pdf = pdfium.PdfDocument(pdf_path)
    with zipfile.ZipFile(omr) as src:
        entries = [(info, src.read(info)) for info in src.infolist()]
    sheets: dict[int, _Sheet] = {}
    where: dict[int, int] = {}  # sheet number -> entry
    interlines: dict[int, float] = {}
    halves: list[Half] = []
    fixed_accidentals = fixed_ties = 0
    for e, (info, data) in enumerate(entries):
        m = re.fullmatch(r"sheet#(\d+)/sheet#\1\.xml", info.filename)
        if not (m and int(m.group(1)) <= len(pdf)):
            continue
        n, xml = int(m.group(1)), data.decode("utf-8")
        width, interline = re.search(r'<picture width="(\d+)"', xml), re.search(r'<interline [^>]*?main="(\d+)"', xml)
        if not (width and interline):
            continue
        page = pdf[n - 1]
        k = page.get_width() / int(width.group(1))  # PDF points per sheet pixel
        sheet = _Sheet(xml)
        fixed_accidentals += _fix_accidentals(sheet, accidentals(page), k, int(interline.group(1)))
        sheet = _Sheet(sheet.result())  # the positions have moved
        ties, found = _fix_ties(sheet, curves(page), k, int(interline.group(1)), n)
        fixed_ties += ties
        halves += found
        sheets[n], where[n], interlines[n] = sheet, e, int(interline.group(1))
    fixed_ties += _join_halves(sheets, halves, interlines)
    for n, sheet in sheets.items():
        entries[where[n]] = (entries[where[n]][0], sheet.result().encode("utf-8"))
    if fixed_accidentals or fixed_ties:
        tmp = omr.with_suffix(".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
            for info, data in entries:
                dst.writestr(info, data)
        shutil.move(tmp, omr)
    return fixed_accidentals, fixed_ties
