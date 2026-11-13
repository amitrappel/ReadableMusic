"""Let Claude read each system of a scan itself, where Audiveris's reading is too poor to be
its draft.

Of נערה במשקפים, a phone photo of a handwritten score, Audiveris found 11 of the 12 staves
but only 61 of some 250 notes, and a single measure of the last system, which it then lost
(4 systems on the page, 3 in its score). Here Audiveris gives only where the systems are:
each is cut from the page down to the next, so that the image holds a staff Audiveris
missed. Claude writes out the system's staves (label, clef, key, time) and its measures in
reader.py's format, with the hairpins, and the score is built as Audiveris exports one: a
part for each staff of each system, shown only in its own, so that merge_parts gives the
staves to voices by their labels and range. The notes then go in as Claude's reading of a
draft does (apply). The edge of the photo cut off the labels ("…ss"), so Claude names the
staves of all systems at once, from their left ends side by side.
"""

import json
import os
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Callable

from PIL import Image

from .chords import Chord
from .progress import Step
from .reader import SCHEMA as DRAFTED
from .reader import (ABOVE, ALSO, DIVISIONS, FORMAT, MODEL, STEMS, SYLLABLES, _ask, _image, _spaces, apply, doubts, level,
                     page_systems, parse_voice, systems_of)
from .reread import CLEFS, TIME
from .scale import TARGET_INTERLINE
from .vision import _shown

PROMPT = f"""The image shows one system of an a cappella choir score, handwritten or printed, perhaps
photographed at an angle. Read it carefully and write it out.

First its staves, top to bottom: the part label printed at the left of the staff ("" if
there is none; where the edge of the page cuts it off, the whole name it most likely is,
from the letters left and the usual names of choir parts); its clef ("treble";
"treble-8" with a small 8 below; "bass"; "alto"; or "other"), its key signature (positive
for sharps, negative for flats, 0 for none) and the time signature printed at its start
("3/4", or "" if none is printed there). Then every measure of the system in order,
numbered from {{first}}, with the voices of each staff, the staves numbered from 1 at the top.

{FORMAT}
{STEMS} {SYLLABLES}

{ALSO}
And every hairpin, a wedge that opens (crescendo) or closes (diminuendo): the staff it
belongs to, the measure and quarters where it starts, and those where it ends."""

NAMING = """The image shows, side by side from left to right, the left end of each system of an a
cappella choir score in order: the clefs of its staves and their part labels, which the edge
of the page may cut off. The systems have {} staves. Name the part of each staff, system
by system, top to bottom: the whole name its label stands for, from the letters left and
the usual names of choir parts, such as "Soprano 1", "Alto 2", "Tenor" or "Bass". The same
label on two systems is the same part; a later system often shortens the names of the
first. Give "" for a staff without a label."""
NAMED = {"type": "object", "properties": {"systems": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}},
         "required": ["systems"], "additionalProperties": False}
LABEL_WIDTH = 0.12  # share of the page right of a system's left end that holds its labels and clefs

SCHEMA = {**DRAFTED, "properties": {
    "staves": {"type": "array", "items": {
        "type": "object",
        "properties": {"label": {"type": "string"}, "clef": {"type": "string", "enum": [*CLEFS, "other"]},
                       "fifths": {"type": "integer"}, "time": {"type": "string"}},
        "required": ["label", "clef", "fifths", "time"], "additionalProperties": False}},
    **DRAFTED["properties"],
    "wedges": {"type": "array", "items": {
        "type": "object",
        "properties": {"kind": {"type": "string", "enum": ["crescendo", "diminuendo"]}, "staff": {"type": "integer"},
                       "measure": {"type": "string"}, "quarters": {"type": "number"},
                       "last": {"type": "string"}, "end": {"type": "number"}},
        "required": ["kind", "staff", "measure", "quarters", "last", "end"], "additionalProperties": False}}},
    "required": ["staves", *DRAFTED["required"], "wedges"]}


def poor(mxl: Path, omr: Path) -> str:
    """Why Audiveris's reading cannot be Claude's draft ("" if it can): its systems are not
    those on the page, or its staves hold more rests than notes where they are shown."""
    try:
        with zipfile.ZipFile(mxl) as z:
            text = z.read(next(n for n in z.namelist() if n.endswith(".xml") and not n.startswith("META-INF"))).decode("utf-8")
        root = ET.fromstring(text[text.index("<score-partwise"):])
        systems, places = len(systems_of(root)), len(page_systems(omr))
    except (OSError, ValueError, StopIteration, ET.ParseError, zipfile.BadZipFile):
        return ""
    notes = rests = 0
    for part in root.findall("part"):
        for m, shown in zip(part.findall("measure"), _shown(part)):
            for n in m.iter("note") if shown else ():
                notes += n.find("pitch") is not None
                rests += n.find("rest") is not None
    why = [f"{places} systems on the page, {systems} in the score"] if systems != places else []
    why += [f"{notes} notes and {rests} rests"] if notes < rests else []
    return "; ".join(why)


def bands(places: list[tuple[int, int, tuple[int, int, int, int], float]], heights: list[int]) -> list[tuple]:
    """The systems' places on the page, each from the full width and down to the next system
    (the last to the foot of its sheet, of heights[sheet] pixels)."""
    out = []
    for k, (sheet, width, (_, top, _, bottom), slope) in enumerate(places):
        after = places[k + 1] if k + 1 < len(places) else None
        foot = after[2][1] if after and after[0] == sheet else heights[sheet]
        out.append((sheet, width, (0, top, width, max(bottom, foot)), slope))
    return out


def _length(events: list[dict]) -> int:
    return sum(ev["duration"] for ev in events)


def _time(quarters: Fraction) -> str:
    return f"{quarters.numerator}/4" if quarters.denominator == 1 else f"{2 * quarters}/8" if (2 * quarters).denominator == 1 else ""


def _clef(name: str) -> ET.Element:
    sign, line, octave = CLEFS.get(name, CLEFS["treble"])
    clef = ET.Element("clef")
    ET.SubElement(clef, "sign").text = sign
    ET.SubElement(clef, "line").text = str(line)
    if octave:
        ET.SubElement(clef, "clef-octave-change").text = str(octave)
    return clef


def build(answers: list[dict]) -> tuple[ET.Element, list[list[int]], list[dict], list[tuple[int, int]]]:
    """The score of Claude's answers, one per system read, with every part's measures at
    rest; the measure indices of each system; the answers renumbered for it (staves by
    part, the other parts at rest, measures by their place in the score); and the system
    and staff of each part."""
    staves = [max([len(a["staves"])] + [s["staff"] for m in a["measures"] for s in m["staves"]]) for a in answers]
    owner = [(s, j) for s, n in enumerate(staves) for j in range(n)]  # part -> (system, staff)
    systems, k = [], 0
    for a in answers:
        systems.append(list(range(k, k + len(a["measures"]))))
        k += len(a["measures"])
    # A measure's length is that of its first voice; the time signature, where none is read, the commonest.
    lengths = []
    for a in answers:
        for m in a["measures"]:
            voice = next((v for s in sorted(m["staves"], key=lambda s: s["staff"]) for v in s["voices"] if v.strip()), "")
            try:
                lengths.append(_length(parse_voice(voice, DIVISIONS)))
            except ValueError:
                lengths.append(0)
    common = Counter(x for x in lengths if x).most_common(1)
    times, now = [], (_time(Fraction(common[0][0], DIVISIONS)) if common else "") or "4/4"
    for s, a in enumerate(answers):
        printed = [x["time"] for x in a["staves"] if TIME.fullmatch(x["time"])]
        now = printed[0] if printed else now
        times.append(now)
        beats, kind = TIME.fullmatch(now).groups()
        for k in systems[s]:
            lengths[k] = lengths[k] or int(Fraction(4 * int(beats), int(kind)) * DIVISIONS)
    root = ET.Element("score-partwise", version="4.0")
    part_list = ET.SubElement(root, "part-list")
    for p, (s, j) in enumerate(owner, 1):
        label = answers[s]["staves"][j]["label"].strip() if j < len(answers[s]["staves"]) else ""
        ET.SubElement(ET.SubElement(part_list, "score-part", id=f"P{p}"), "part-name").text = label
    for p, (own, j) in enumerate(owner, 1):
        info = answers[own]["staves"][j] if j < len(answers[own]["staves"]) else {"clef": "treble", "fifths": 0}
        part = ET.SubElement(root, "part", id=f"P{p}")
        for s, measures in enumerate(systems):
            beats, kind = TIME.fullmatch(times[s]).groups()
            for k in measures:
                m = ET.SubElement(part, "measure", number=str(k + 1))
                first = k == measures[0]
                if first and s:
                    ET.SubElement(m, "print", {"new-system": "yes"})
                if first:
                    attributes = ET.SubElement(m, "attributes")
                    if not k:
                        ET.SubElement(attributes, "divisions").text = str(DIVISIONS)
                        ET.SubElement(ET.SubElement(attributes, "key"), "fifths").text = str(max(-7, min(7, info["fifths"])))
                    if not s or times[s] != times[s - 1]:
                        time = ET.SubElement(attributes, "time")
                        ET.SubElement(time, "beats").text = beats
                        ET.SubElement(time, "beat-type").text = kind
                    if not k:
                        attributes.append(_clef(info["clef"]))
                    ET.SubElement(attributes, "staff-details", {"print-object": "yes" if s == own else "no"})
                rest = ET.SubElement(m, "note")
                ET.SubElement(rest, "rest", measure="yes")
                ET.SubElement(rest, "duration").text = str(lengths[k])
                ET.SubElement(rest, "voice").text = "1"
    renumbered = []
    for s, a in enumerate(answers):
        offset = next(p for p, (own, _) in enumerate(owner) if own == s)
        number = {m["number"]: str(k + 1) for m, k in zip(a["measures"], systems[s])}
        measures = []
        for m, k in zip(a["measures"], systems[s]):
            at_rest = [", ".join("r " + x[2:] for x in _spaces(lengths[k], DIVISIONS))]
            given = {x["staff"]: [v for v in x["voices"] if v.strip()] for x in m["staves"] if 1 <= x["staff"] <= staves[s]}
            measures.append({"number": number[m["number"]], "staves": [
                {"staff": p + 1, "voices": (given.get(p + 1 - offset) if owner[p][0] == s else None) or at_rest}
                for p in range(len(owner))]})
        def moved(items: list[dict], *keys: str) -> list[dict]:
            return [{**x, **{key: number[x[key]] for key in keys}} for x in items if all(x[key] in number for key in keys)]
        renumbered.append({**a, "measures": measures, "chords": moved(a["chords"], "measure"),
                           "texts": [{**t, "staff": t["staff"] + offset} for t in moved(a["texts"], "measure")
                                     if 1 <= t["staff"] <= staves[s]],
                           "wedges": [{**w, "staff": w["staff"] + offset} for w in moved(a.get("wedges", []), "measure", "last")
                                      if 1 <= w["staff"] <= staves[s]],
                           "endings": moved(a["endings"], "first", "last"), "repeats": moved(a["repeats"], "measure")})
    return root, systems, renumbered, owner


def labels(sheets: list[Image.Image], places: list[tuple]) -> Image.Image:
    """The left end of each system, with its clefs and part labels, side by side; each down
    to the next system, as Audiveris can miss a staff."""
    strips = []
    for (sheet, width, (left, top, _, _), _), (_, _, (_, _, _, bottom), _) in             zip(places, bands(places, [page.height for page in sheets])):
        page, k = sheets[sheet], sheets[sheet].width / width
        d = TARGET_INTERLINE / k  # the pages are scaled to it; the box holds a margin of ABOVE
        strips.append(page.crop((0, round((top + (ABOVE - 2) * d) * k), round((left + LABEL_WIDTH * width) * k),
                                 round(bottom * k))))
    out = Image.new("L", (sum(s.width for s in strips) + 20 * len(strips), max(s.height for s in strips)), 255)
    x = 0
    for strip in strips:
        out.paste(strip.convert("L"), (x, 0))
        x += strip.width + 20
    return out


def name_staves(client, image: Image.Image, answers: list[dict], log) -> float:
    """Name the staves of all systems at once from their labels side by side, so that a
    part keeps its name from system to system: read one system at a time, the "o2" left of
    the edge of נערה במשקפים was now Alto 2, now Soprano 2. Return the cost."""
    counts = ", ".join(str(len(a["staves"])) for a in answers)
    try:
        response = client.messages.create(
            model=MODEL, max_tokens=8000,
            messages=[{"role": "user", "content": [_image(image), {"type": "text", "text": NAMING.format(counts)}]}],
            output_config={"format": {"type": "json_schema", "schema": NAMED}})
        named = json.loads(next(b.text for b in response.content if b.type == "text"))["systems"]
    except Exception as e:  # the names each system's reading gave stay
        log(f"Claude could not name the staves: {e}")
        return 0.0
    cost = (response.usage.input_tokens * 4 + response.usage.output_tokens * 20) / 1e6
    if [len(n) for n in named] != [len(a["staves"]) for a in answers]:
        log(f"Claude named other staves than it read (${cost:.3f}); their names stay")
        return cost
    for names, a in zip(named, answers):
        for name, staff in zip(names, a["staves"]):
            staff["label"] = name.strip() or staff["label"]
    log(f"Claude named the staves (${cost:.3f}): " + " | ".join(", ".join(n) for n in named))
    return cost


def read_fresh(mxl: Path, omr: Path, load_sheets: Callable[[], list[Image.Image]], log=print) -> tuple[set, list[Chord]]:
    """Replace Audiveris's MusicXML file with Claude's reading of the systems on its pages;
    load_sheets gives the pages Audiveris read. Return the (part, measure) indices written,
    for beaming, and the chord symbols by measure index; nothing, and the file as it was,
    on any failure."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return set(), []
    try:
        import anthropic

        sheets = load_sheets()
        places = bands(page_systems(omr), [page.height for page in sheets])
        client = anthropic.Anthropic(timeout=600.0)
        images, prompts, answers, first, cost = [], [], [], 1, 0.0
        for k, (sheet, width, box, slope) in enumerate(places, 1):
            log(Step(f"Claude is reading system {k} of {len(places)}", "Recognition could read little of this "
                     "image, so Claude reads the music itself, a system at a time."))
            page = sheets[sheet]
            image = level(page.crop(tuple(round(v * page.width / width) for v in box)), slope)
            prompt = PROMPT.replace("{first}", str(first))
            answer = _ask(client, image, "", log, prompt=prompt, schema=SCHEMA)
            if not answer or not answer["measures"]:
                log(f"Claude could not read system {len(images) + len(answers) + 1}; it is left out")
                continue
            cost += answer["cost"]
            images.append(image)
            prompts.append(prompt)
            answers.append(answer)
            first += len(answer["measures"])
        if not answers:
            return set(), []
        if len(answers) == len(places):
            log(Step("Claude is naming the parts", "The names at the left of all the systems are read side by "
                     "side, so that each staff goes to the same voice throughout."))
            cost += name_staves(client, labels(sheets, page_systems(omr)), answers, log)
        root, systems, renumbered, owner = build(answers)
        # Where a voice does not add up, Claude looks again, keeping its measures and staves.
        again = 0
        for s, (image, prompt, answer) in enumerate(zip(images, prompts, answers)):
            own = [part for part, (system, _) in zip(root.findall("part"), owner) if system == s]
            numbers = {m["number"]: k for m, k in zip(answer["measures"], systems[s])}
            if (wrong := doubts(answer, own, numbers)):
                log(Step(f"Claude is reading system {s + 1} again", "Some of its measures do not add up to the time "
                         "signature, so Claude reads it once more."))
                again += 1
                second = _ask(client, image, "", log, answer, wrong, prompt, SCHEMA)
                if second and len(second["measures"]) == len(answer["measures"]) and len(second["staves"]) == len(answer["staves"]):
                    cost += second["cost"]
                    answers[s] = {**second, "cost": answer["cost"] + second["cost"],
                                  "staves": [{**x, "label": y["label"]} for x, y in zip(second["staves"], answer["staves"])]}
        if again:
            root, systems, renumbered, owner = build(answers)
        parts = root.findall("part")
        log(f"Claude read {len(answers)} system(s) itself, {again} of them twice (${cost:.2f})")
        rewritten, chords = apply(parts, systems, renumbered, log)
        with zipfile.ZipFile(mxl) as z:
            name = next(n for n in z.namelist() if n.endswith(".xml") and not n.startswith("META-INF"))
        with zipfile.ZipFile(mxl, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(name, '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode"))
            z.writestr("META-INF/container.xml", '<?xml version="1.0" encoding="UTF-8"?><container>'
                       f'<rootfiles><rootfile full-path="{name}"/></rootfiles></container>')
        return rewritten, chords
    except Exception as e:  # Audiveris's reading stays
        log(f"Could not have Claude read the systems itself: {e}")
        return set(), []
