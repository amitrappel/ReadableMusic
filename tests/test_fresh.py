import xml.etree.ElementTree as ET

import music21 as m21

from readablemusic.fresh import bands, build
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


def test_each_system_is_cut_down_to_the_next():
    places = [(0, 1000, (40, 100, 900, 300), 0.0), (0, 1000, (40, 350, 900, 500), 0.01), (1, 1000, (40, 80, 900, 200), 0.0)]
    assert [box for _, _, box, _ in bands(places, [1400, 1300])] == [(0, 100, 1000, 350), (0, 350, 1000, 1400), (0, 80, 1000, 1300)]
