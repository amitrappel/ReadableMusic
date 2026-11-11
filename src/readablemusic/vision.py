"""Ask Claude what the first page of a score shows: each staff's clef on the first system,
the key and time signatures, the credits and the footnotes, and how well it can be read.

Recognition can misread a handwritten clef, miss a key or time signature, or drop the small
8 under a tenor's treble clef, and each such mistake spoils every note of a part. Claude
sees the page and, enlarged, the start of the first system; where it disagrees with the
recognised score, the score is read again under what it saw (reread.py). On 18 samples it
found 3 such mistakes and made none of its own; on the whole page alone it miscounted a key.
On a scan its clefs go to every system (system_clefs).

Runs only when ANTHROPIC_API_KEY is set (`uv run --env-file .env ...`), at about 5 cents a
score. Any failure leaves the recognised score as it is.
"""

import base64
import io
import json
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .pagetext import Item
from .reader import CURSIVE, systems_of
from .reread import CLEFS, TIME, reread

MODEL = "claude-opus-5-5"
MAX_EDGE, MAX_AREA = 2576, 3_700_000  # the largest image the model sees in full detail
MAX_IMAGE_BYTES = 3_500_000  # the API takes 5 MB an image after base64
HEADER_ROOM = 14  # interlines after the staff start that hold a clef, 7 accidentals and a time
MARGIN = 5  # interlines above and below the first system's staves
HEADER_MIN = 0.03  # share of the page above the first system that is enlarged for the credits
CREDIT_KINDS = ("title", "subtitle", "composer", "lyricist", "arranger")
LEGIBILITY = ("clear", "partly", "poor")

PROMPT = f"""This is the first page of an a cappella choir score.
Look at the first system of music on the page (the first group of staves sung together).
The second image enlarges the start of that system; read the clefs, key and time there.
Two more images, where there are, enlarge the left and the right of the top of the page.
Report what is printed there, not what convention would suggest:
- For each staff of that system, top to bottom: the part label printed at its left ("" if none),
  and its clef. "treble-8" is a treble clef with a small 8 below it; a treble clef without
  the 8 is "treble", even for a tenor part. Use "other" for any other clef or none.
- The key signature at the start: positive for sharps, negative for flats, 0 for none.
- The time signature at the start as "beats/beat-type" (common time C is "4/4", cut time is
  "2/2"), or "" if none is printed.
- The credits printed on the page: title, subtitle, composer (music), lyricist (words),
  arranger, as written on the page and without their labels ("" if absent). {CURSIVE}
- Any other text printed on the page outside the music, such as footnotes, sources and
  copyright lines, each paragraph as written. Leave out page numbers, part names and the
  text within the music (lyrics, chord symbols, tempo and other directions).
- How well the notes, rests and lyrics of the whole page can be read in this image:
  "clear" if all of them for sure, "partly" if some not for sure, "poor" if many not. And
  what in the image itself makes it hard, if anything, a few words each: blur, too few
  pixels, part of the page cut off (such as the part names at the left), shadow or uneven
  light, a steep angle, a fold or curl. Leave out what a better image would not change,
  such as handwriting."""

SCHEMA = {
    "type": "object",
    "properties": {
        "staves": {"type": "array", "items": {
            "type": "object",
            "properties": {"label": {"type": "string"},
                           "clef": {"type": "string", "enum": [*CLEFS, "other"]}},
            "required": ["label", "clef"], "additionalProperties": False}},
        "fifths": {"type": "integer"},
        "time": {"type": "string"},
        **{kind: {"type": "string"} for kind in CREDIT_KINDS},
        "notes": {"type": "array", "items": {"type": "string"}},
        "legibility": {"type": "string", "enum": list(LEGIBILITY)},
        "problems": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["staves", "fifths", "time", *CREDIT_KINDS, "notes", "legibility", "problems"],
    "additionalProperties": False,
}


@dataclass
class Reading:
    clefs: list[str]  # of the first system's staves, top to bottom
    fifths: int
    time: str  # "3/8", or "" if none is printed
    credits: dict[str, str]  # kind -> text, for the kinds printed
    notes: tuple[str, ...] = ()  # footnotes, sources, copyright
    legibility: str = "clear"  # of the whole page, one of LEGIBILITY
    problems: tuple[str, ...] = ()  # what in the image makes it hard to read

    def items(self, page: int) -> list[Item]:
        return [Item(kind, text, page, (0, 0, 0, 0), 0) for kind, text in self.credits.items()] + \
            [Item("note", text, page, (0, 0, 0, 0), 0) for text in self.notes]


def system_start(sheet: str) -> tuple[int, tuple[int, int, int, int]] | None:
    """(picture width, box from the page's left edge to just after the clefs, keys and times
    of the first system) in the pixels of an Audiveris sheet, or None without a system."""
    picture = re.search(r'<picture width="(\d+)" height="(\d+)"', sheet)
    interline = re.search(r'<interline [^>]*main="(\d+)"', sheet)
    if not picture or not interline or "<system " not in sheet:
        return None
    width, height, d = int(picture.group(1)), int(picture.group(2)), int(interline.group(1))
    system = sheet[sheet.index("<system "):sheet.index("</system>")]
    lines = "".join(re.findall(r"<lines>.*?</lines>", system, re.S))
    ys = [float(y) for y in re.findall(r'y="(\d+(?:\.\d+)?)"', lines)]
    lefts = [int(x) for x in re.findall(r'<staff id="\d+" left="(\d+)"', system)]
    if not ys or not lefts:
        return None
    # Where recognition missed the key or time, its header ends too soon.
    stops = [int(x) for x in re.findall(r'<header start="\d+" stop="(\d+)"', system)]
    right = max(stops + [min(lefts) + HEADER_ROOM * d]) + 2 * d
    return width, (0, max(0, int(min(ys) - MARGIN * d)), min(width, right), min(height, int(max(ys) + MARGIN * d)))


def _fit(img: Image.Image) -> Image.Image:
    k = min(MAX_EDGE / max(img.size), (MAX_AREA / (img.width * img.height)) ** 0.5)
    return img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)


def _image_block(img: Image.Image) -> dict:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    media = "image/png"
    if buf.tell() > MAX_IMAGE_BYTES:  # a noisy scan
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        media = "image/jpeg"
    return {"type": "image", "source": {"type": "base64", "media_type": media,
                                        "data": base64.standard_b64encode(buf.getvalue()).decode()}}


def ask(page: Image.Image, omr: Path, log=print) -> Reading | None:
    """Claude's reading of page, which Audiveris recognised as the first sheet of omr."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic

        with zipfile.ZipFile(omr) as z:
            start = system_start(z.read("sheet#1/sheet#1.xml").decode("utf-8"))
        if not start:
            return None
        width, box = start
        page = page.convert("L")
        k = page.width / width
        crop = page.crop(tuple(round(v * k) for v in box))
        images = [_image_block(_fit(page)), _image_block(_fit(crop))]
        if (top := round(box[1] * k)) > HEADER_MIN * page.height:  # titles and credits, often small
            images += [_image_block(_fit(page.crop((round(a * page.width), 0, round(b * page.width), top))))
                       for a, b in ((0, 0.6), (0.4, 1))]
        response = anthropic.Anthropic(timeout=180.0).messages.create(
            model=MODEL, max_tokens=16000,
            messages=[{"role": "user", "content": [*images, {"type": "text", "text": PROMPT}]}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
        if response.stop_reason != "end_turn":
            log(f"Claude did not read the page ({response.stop_reason})")
            return None
        answer = json.loads(next(b.text for b in response.content if b.type == "text"))
        cost = (response.usage.input_tokens * 4 + response.usage.output_tokens * 20) / 1e6
        log(f"Claude read the first page (${cost:.3f})")
        return Reading([s["clef"] for s in answer["staves"]], answer["fifths"], answer["time"],
                       {kind: answer[kind].strip() for kind in CREDIT_KINDS if answer[kind].strip()},
                       tuple(" ".join(n.split()) for n in answer["notes"] if n.strip()),
                       answer["legibility"], tuple(p.strip() for p in answer["problems"] if p.strip()))
    except Exception as e:  # the score is complete without this step
        log(f"Could not ask Claude about the first page: {e}")
        return None


def _clef_name(clef: ET.Element) -> str:
    sign = (clef.findtext("sign"), int(clef.findtext("line") or 0), int(clef.findtext("clef-octave-change") or 0))
    return next((name for name, c in CLEFS.items() if c == sign), "other")


def _shown(part: ET.Element) -> list[bool]:
    """Whether the part's staff is printed in each measure: Audiveris hides it in the systems
    where another of its parts is that staff."""
    out, shown = [], True
    for m in part.findall("measure"):
        for details in m.findall("attributes/staff-details"):
            if details.get("print-object"):
                shown = details.get("print-object") != "no"
        out.append(shown)
    return out


def system_clefs(root: ET.Element, seen: list[str]) -> dict[str, str]:
    """For a scan, whose staves keep their clefs: part id -> the clef seen on the first
    system's staff that the part is, by its place among the staves shown, in every system
    where it is shown; for the parts read in any other clef. Audiveris misreads the 8 under
    a tenor's clef differently from system to system (האדון הרופא: two C clefs, an 8 above),
    and starts a part of its own where it misreads a staff's name."""
    parts = root.findall("part")
    if any(int(s.text or 1) > 1 for s in root.iter("staves")):
        return {}
    shown = [_shown(p) for p in parts]
    found: dict[str, set[str]] = {}
    for measures in systems_of(root):
        here = [p for p, s in zip(parts, shown) if s[measures[0]]]
        if len(here) == len(seen):
            for part, clef in zip(here, seen):
                found.setdefault(part.get("id"), set()).add(clef)
    out = {}
    for part in parts:
        clefs = found.get(part.get("id"), set())
        if len(clefs) == 1 and (clef := clefs.pop()) in CLEFS and {_clef_name(c) for c in part.iter("clef")} != {clef}:
            out[part.get("id")] = clef
    return out


def corrections(xml: str, reading: Reading, scan: bool = False) -> tuple[dict[str, str], int | None, str | None]:
    """(part id -> clef, fifths, time) where the reading differs from the score: the clefs
    when the staves of the score's first measure match the first system's one for one (on a
    scan, system_clefs), the key and time only when the score does not change them later.
    On a scan the key also where parts change it apart from each other, which is a misreading
    (האדון הרופא: the tenor's flats missed on one system, the bass's on two)."""
    root = ET.fromstring(xml[xml.index("<score-partwise"):])
    staves = []  # (part id, or None for a part on several staves; its clef)
    for part in root.iter("part"):
        first = part.find("measure")
        found = first.findall("attributes/clef") if first is not None else []
        several = any(int(s.text or 1) > 1 for s in part.iter("staves"))
        staves += [(None if several else part.get("id"), _clef_name(c)) for c in found] or [(part.get("id"), "treble")]
    seen = reading.clefs
    if len(seen) != len(staves):
        seen = [c for c in seen if c != "other"]  # percussion staves, which are dropped
    clefs = {} if len(seen) != len(staves) else \
        {part: clef for (part, ours), clef in zip(staves, seen) if part and clef in CLEFS and clef != ours}
    if scan:
        clefs = system_clefs(root, reading.clefs) or system_clefs(root, [c for c in reading.clefs if c != "other"])
    keys = [int(k.findtext("fifths")) for k in root.iter("key") if k.findtext("fifths")]
    times = [f"{t.findtext('beats')}/{t.findtext('beat-type')}" for t in root.iter("time")]
    fifths = reading.fifths if (reading.fifths != (keys[0] if keys else 0) and len(set(keys)) <= 1
                                and -7 <= reading.fifths <= 7) else None
    changes = [{(k, m.findtext("attributes/key/fifths")) for k, m in enumerate(part.findall("measure"))
                if k and m.findtext("attributes/key/fifths") is not None} for part in root.findall("part")]
    if scan and changes and -7 <= reading.fifths <= 7 and set(keys) - {reading.fifths} and not set.intersection(*changes):
        fifths = reading.fifths
    time = reading.time if (TIME.fullmatch(reading.time) and reading.time != (times[0] if times else "")
                            and len(set(times)) <= 1) else None
    return clefs, fifths, time


def correct(musicxml: Path, reading: Reading, scan: bool = False) -> str:
    """Read the score (MusicXML, or Audiveris's compressed .mxl) again where Claude saw other
    clefs, key or time; say what changed."""
    name = None
    if musicxml.suffix == ".mxl":
        with zipfile.ZipFile(musicxml) as z:
            name = next(n for n in z.namelist() if n.endswith(".xml") and not n.startswith("META-INF"))
            xml = z.read(name).decode("utf-8")
    else:
        xml = musicxml.read_text(encoding="utf-8")
    clefs, fifths, time = corrections(xml, reading, scan)
    if not (clefs or fifths is not None or time):
        return ""
    if name:
        with zipfile.ZipFile(musicxml, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(name, reread(xml, clefs, fifths, time))
            z.writestr("META-INF/container.xml", '<?xml version="1.0" encoding="UTF-8"?><container>'
                       f'<rootfiles><rootfile full-path="{name}"/></rootfiles></container>')
    else:
        musicxml.write_text(reread(xml, clefs, fifths, time), encoding="utf-8")
    done = [f"part {part} in {clef}" for part, clef in clefs.items()]
    done += [f"key {fifths:+d}"] if fifths is not None else []
    done += [f"time {time}"] if time else []
    return ", ".join(done)
