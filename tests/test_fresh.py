import xml.etree.ElementTree as ET
from types import SimpleNamespace

import music21 as m21
from PIL import Image

from readablemusic.fresh import bands, build, labels, name_staves
from readablemusic.parts import merge_parts
from readablemusic.reader import apply


def answer(staves, measures, texts=()):
    return {"cost": 0, "staves": [{"label": label, "clef": clef, "fifths": 0, "time": time} for label, clef, time in staves],
            "measures": [{"number": n, "staves": [{"staff": s, "voices": [v]} for s, v in enumerate(vs, 1)]}
                         for n, vs in measures],
            "chords": [], "texts": list(texts), "endings": [], "repeats": []}


def test_a_score_is_built_from_claudes_reading_of_each_system():
    # נערה במשקפים: six staves on the first system, two on the next, with words in Hebrew.
    first = answer([("S", "treble", "3/4"), ("B", "bass", "3/4")],
                   [("1", ["E5 2.", "C3 2."]), ("2", ["D5 2, C5 4", "G2 2."])],
                   [{"measure": "1", "quarters": 0, "staff": 2, "above": True, "text": "mp"}])
    second = answer([("S", "treble", "")], [("3", ["r 2, G4 4 [א-]"]), ("4", ["A4 2 [הב-], B4 4 [תי]"])])
    root, systems, renumbered, owner = build([first, second])
    assert systems == [[0, 1], [2, 3]] and owner == [(0, 0), (0, 1), (1, 0)]
    parts = root.findall("part")
    rewritten, _ = apply(parts, systems, renumbered, log=lambda m: None)
    assert (2, 3) in rewritten
    shown = [[d.get("print-object") for d in p.iter("staff-details")] for p in parts]
    assert shown == [["yes", "no"], ["yes", "no"], ["no", "yes"]]
    assert [n.findtext("lyric/text") for n in parts[2].iter("note") if n.find("lyric") is not None] == ["א", "הב", "תי"]
    assert parts[1].find(".//dynamics") is not None
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
    merged = merge_parts(m21.converter.parse(xml, format="musicxml"))
    # The second system's staff is the first's soprano.
    assert len(merged.parts) == 2
    assert [p.nameWithOctave for p in merged.parts[0].flatten().pitches] == ["E5", "D5", "C5", "G4", "A4", "B4"]


def test_hairpins_go_on_their_staff_from_start_to_end():
    first = answer([("S", "treble", "3/4"), ("B", "bass", "3/4")], [("1", ["E5 2.", "C3 2."]), ("2", ["D5 2.", "G2 2."])])
    second = answer([("S", "treble", ""), ("B", "bass", "")], [("3", ["G4 2.", "G3 4, A3 2"]), ("4", ["A4 2.", "A3 2."])])
    second["wedges"] = [{"kind": "diminuendo", "staff": 2, "measure": "3", "quarters": 0, "last": "3", "end": 1.5}]
    root, systems, renumbered, owner = build([first, second])
    assert renumbered[1]["wedges"] == [{"kind": "diminuendo", "staff": 4, "measure": "3", "quarters": 0, "last": "3", "end": 1.5}]
    parts = root.findall("part")
    apply(parts, systems, renumbered, log=lambda m: None)
    measure = parts[3].findall("measure")[2]
    assert [(c.tag, c.findtext("pitch/step")) for c in measure if c.tag in ("note", "direction")] ==         [("direction", None), ("note", "G"), ("note", "A"), ("direction", None)]
    assert [w.get("type") for w in measure.iter("wedge")] == ["diminuendo", "stop"]


def test_a_hairpin_starts_on_the_note_nearest_its_start():
    # נערה במשקפים: a crescendo drawn from the middle of bar 1's dotted half, a diminuendo
    # from late in bar 3 to bar 4; music21 hangs a start on the note after it.
    measures = [(str(n), [p + " 2."]) for n, p in enumerate(["E4", "A4", "G4", "A4"], 1)]
    first = answer([("S", "treble", "3/4")], measures)
    first["wedges"] = [{"kind": "crescendo", "staff": 1, "measure": "1", "quarters": 1, "last": "1", "end": 2},
                       {"kind": "diminuendo", "staff": 1, "measure": "3", "quarters": 2.5, "last": "4", "end": 0.5}]
    root, systems, renumbered, _ = build([first])
    apply(root.findall("part"), systems, renumbered, log=lambda m: None)
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
    merged = merge_parts(m21.converter.parse(xml, format="musicxml"), slurs=True)
    wedges = {type(w).__name__: [n.measureNumber for n in w.getSpannedElements()]
              for w in merged.parts[0].recurse().getElementsByClass(m21.dynamics.DynamicWedge)}
    assert wedges == {"Crescendo": [1], "Diminuendo": [4]}  # on one note each


def test_the_staves_of_all_systems_are_named_at_once():
    class Client:
        class messages:
            @staticmethod
            def create(**request):
                Client.request = request
                return SimpleNamespace(usage=SimpleNamespace(input_tokens=1000, output_tokens=100), content=[
                    SimpleNamespace(type="text", text='{"systems": [["Alto 2", "Bass"], ["Alto 2", ""]]}')])
    answers = [answer([("2", "treble", ""), ("ss", "bass", "")], []), answer([("Sop 2", "treble", ""), ("B", "bass", "")], [])]
    image = labels([Image.new("L", (1000, 1400), 255)], [(0, 1000, (60, 100, 900, 500), 0.0), (0, 1000, (60, 700, 900, 1000), 0.0)])
    assert image.size == (2 * 180 + 40, 1400 - 700 - 5 * 24)
    assert name_staves(Client, image, answers, log=lambda m: None) == 0.006
    assert "2, 2 staves" in Client.request["messages"][0]["content"][1]["text"]
    assert [[x["label"] for x in a["staves"]] for a in answers] == [["Alto 2", "Bass"], ["Alto 2", "B"]]


def test_a_hairpin_from_late_in_a_note_starts_on_the_next():
    measures = [(str(n), [p + " 2."]) for n, p in enumerate(["E4", "A4", "G4", "A4"], 1)]
    first = answer([("S", "treble", "3/4")], measures)
    first["wedges"] = [{"kind": "crescendo", "staff": 1, "measure": "1", "quarters": 1.5, "last": "1", "end": 2.5},
                       {"kind": "diminuendo", "staff": 1, "measure": "3", "quarters": 2, "last": "3", "end": 3}]
    root, systems, renumbered, _ = build([first])
    apply(root.findall("part"), systems, renumbered, log=lambda m: None)
    starts = [(m.get("number"), w.get("type")) for m in root.find("part").findall("measure") for w in m.iter("wedge")]
    assert starts == [("1", "crescendo"), ("1", "stop"), ("4", "diminuendo"), ("4", "stop")]


def test_each_system_is_cut_down_to_the_next():
    places = [(0, 1000, (40, 100, 900, 300), 0.0), (0, 1000, (40, 350, 900, 500), 0.01), (1, 1000, (40, 80, 900, 200), 0.0)]
    assert [box for _, _, box, _ in bands(places, [1400, 1300])] == [(0, 100, 1000, 350), (0, 350, 1000, 1400), (0, 80, 1000, 1300)]
