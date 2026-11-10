import xml.etree.ElementTree as ET

import music21 as m21

from readablemusic.chords import Chord, add_chords, chord_symbol
from PIL import Image, ImageDraw

from readablemusic.reader import (add_endings, add_repeats, apply, direction, doubts, draft, level, measured,
                                  parse_event, parse_voice, replace, shared, ties_out, voices_of)


def note(pitch, kind, duration, voice="1", chord=False, lyric=None, tie=None, extra=""):
    step, octave = pitch[0], pitch[-1]
    alter = {"#": "<alter>1</alter>", "b": "<alter>-1</alter>"}.get(pitch[1:-1], "")
    return (f"<note>{'<chord/>' if chord else ''}<pitch><step>{step}</step>{alter}<octave>{octave}</octave></pitch>"
            f"<duration>{duration}</duration>{f'<tie type={chr(34)}{tie}{chr(34)}/>' if tie else ''}"
            f"<voice>{voice}</voice><type>{kind}</type>{extra}"
            f"{f'<lyric><text>{lyric}</text></lyric>' if lyric else ''}</note>")


# Siyahamba's second measure as Audiveris read it: the tie missed, the second chord a lone A.
MEASURE = ("<measure number='1'><attributes><divisions>24</divisions><key><fifths>1</fifths></key></attributes>"
           + note("G4", "half", 48, lyric="hamb'") + note("B4", "half", 48, chord=True)
           + note("A4", "eighth", 12, lyric="e")
           + "<direction><direction-type><words>p</words></direction-type></direction>"
           + note("A4", "eighth", 12, lyric="ku") + note("C5", "eighth", 12, chord=True)
           + note("F#4", "eighth", 12, lyric="kha") + note("A4", "eighth", 12, chord=True)
           + note("F#4", "eighth", 12) + note("A4", "eighth", 12, chord=True)
           + "<barline location='right'><bar-style>light-heavy</bar-style></barline></measure>")


def test_the_draft_has_one_line_per_voice():
    part = ET.fromstring(f"<part id='P1'>{MEASURE}</part>")
    assert voices_of(part[0], 24) == {"1": ["G4+B4 2", "A4 8", "A4+C5 8", "F#4+A4 8", "F#4+A4 8"]}
    assert draft([part], [0]) == ("Measure 1:\n  staff 1 voice 1: "
                                  "G4+B4 2 [hamb'], A4 8 [e], A4+C5 8 [ku], F#4+A4 8 [kha], F#4+A4 8")


def test_events_are_parsed():
    ev = parse_event("D4+G4 4t~", 24)
    assert (ev["pitches"], ev["duration"], ev["triplet"], ev["tie"]) == (["D4", "G4"], 16, True, True)
    assert parse_event("s 8.", 24)["hidden"] and parse_event("s 8.", 24)["duration"] == 18
    # A comma in a syllable does not end the event.
    voice = parse_voice("D4 4t [khos',|God,], E4 8 [|kha-], r 8", 24)
    assert [ev["lyrics"] for ev in voice] == [{1: "khos',", 2: "God,"}, {2: "kha-"}, {}]


def test_a_measure_is_rewritten_with_claudes_lyrics_and_words():
    m = ET.fromstring(MEASURE)
    events = "G4+B4 2~ [hamb'|march-], G4+B4 8, G4+B4 8 [e-|ing], F4+A4 8 [ku-|in], G4+B4 8 [kha-|the]"
    open_words = {}
    assert replace(m, [parse_voice(events, 24)], {}, 1, [(60, direction("p", False))], open_words) == 8
    assert voices_of(m, 24) == {"1": ["G4+B4 2~", "G4+B4 8", "G4+B4 8", "F4+A4 8", "G4+B4 8"]}
    notes = [n for n in m.iter("note") if n.find("chord") is None]
    # Audiveris's syllables give way to Claude's; the tie ends on both notes of the next chord.
    assert [n.findtext("lyric[@number='1']/text") for n in notes] == ["hamb'", None, "e", "ku", "kha"]
    assert [n.findtext("lyric[@number='1']/syllabic") for n in notes] == ["single", None, "begin", "middle", "middle"]
    assert [n.findtext("lyric[@number='2']/syllabic") for n in notes] == ["begin", None, "end", "single", "single"]
    assert open_words == {1: True, 2: False}
    assert [t.get("type") for t in m.findall("note[2]/tie")] == ["start"]
    assert len([n for n in m.iter("note") if n.find("tie[@type='stop']") is not None]) == 2
    # F natural in G major needs its sign; the words give way to Claude's, at their onset.
    assert [n.findtext("accidental") for n in notes] == [None, None, None, "natural", None]
    tags = [c.tag for c in m]
    assert tags.count("direction") == 1 and tags.index("direction") == 5 and tags[-1] == "barline"
    assert m.find("direction").get("placement") == "below" and m.find("direction//dynamics/p") is not None


def test_a_note_both_parts_sing_is_in_both_voices():
    m = ET.fromstring("<measure number='2'><attributes><divisions>24</divisions></attributes>"
                      + note("D4", "half", 48) + note("D4", "half", 48) + "</measure>")
    voices = [parse_voice("D4+G4 4t [nyen'], E4 4t [kwen-], D4 4t~ [khos',], D4 8, G4+C5 4 [si-], G4+B4 8 [ya-]", 24),
              parse_voice("s 4t, E4 4t, D4 4t~, D4 8, s 4, s 8", 24)]
    replace(m, voices, {}, 1)
    starts = [t for t in m.iter("tuplet") if t.get("type") == "start"]
    # One bracket over the triplet both voices sing; the second voice's is not printed.
    assert [(t.get("bracket"), t.get("show-number")) for t in starts] == [(None, None), ("no", "none")]
    assert [n.findtext("pitch/step") for n in m.iter("note") if n.findtext("voice") == "2" and n.find("rest") is None]         == ["E", "D", "D"]
    assert all(n.find("lyric") is None for n in m.iter("note") if n.findtext("voice") == "2")


def test_a_lone_note_on_a_staff_of_two_parts_is_sung_by_both():
    # Siyahamba's third measure: a chord on one stem, then notes with a stem up and a stem down.
    voices = shared(parse_voice("D4+G4 4t, E4 4t [kwen-], D4 4t~, D4 8, G4+C5 4, G4+B4 8", 24))
    assert [[(ev["pitches"], ev["tie"], ev["hidden"]) for ev in v] for v in voices] == [
        [(["D4", "G4"], False, False), (["E4"], False, False), (["D4"], True, False), (["D4"], False, False),
         (["G4", "C5"], False, False), (["G4", "B4"], False, False)],
        [([], False, True), (["E4"], False, False), (["D4"], True, False), (["D4"], False, False),
         ([], False, True), ([], False, True)]]
    assert not voices[1][1]["lyrics"]
    # Only where the staff's notes are mostly chords: a melody keeps one voice.
    parts = [ET.fromstring("<part id='P1'><measure number='0'><attributes><divisions>24</divisions></attributes>"
                           f"{note('G4', 'whole', 96)}</measure></part>") for _ in range(2)]
    answer = {"measures": [{"number": "0", "staves": [{"staff": 1, "voices": ["G4+B4 2, A4 2"]},
                                                      {"staff": 2, "voices": ["G4 2, A4 2"]}]}],
              "chords": [], "texts": [], "endings": [], "repeats": []}
    apply(parts, [[0]], [answer], log=lambda m: None)
    assert [sorted(set(n.findtext("voice") for n in part.iter("note"))) for part in parts] == [["1", "2"], ["1"]]


def test_repeat_signs_missed_by_audiveris_are_added():
    part = ET.fromstring("<part id='P1'>" + "".join(
        f"<measure number='{k}'>{note('G4', 'whole', 96)}</measure>" for k in range(2)) + "</part>")
    assert add_repeats([part], [(1, False), (1, False), (0, True)]) == 2
    assert add_repeats([part], [(1, False)]) == 0
    first, second = part.findall("measure")
    assert [c.tag for c in first][0] == "barline" and first.find("barline/repeat").get("direction") == "forward"
    assert (second.findtext("barline/bar-style"), second.find("barline/repeat").get("direction")) ==         ("light-heavy", "backward")


def test_endings_are_joined_across_a_system_break():
    # Audiveris's own bracket, over the second measure only, gives way to Claude's.
    part = ET.fromstring("<part id='P1'>" + "".join(
        f"<measure number='{k}'>{note('G4', 'whole', 96)}"
        + ("<barline location='right'><bar-style>light-heavy</bar-style><repeat direction='backward'/></barline>"
           if k == 2 else "")
        + ("<barline location='right'><ending number='1' type='stop'/></barline>" if k == 1 else "")
        + "</measure>" for k in range(5)) + "</part>")
    assert add_endings([part], [("1", 1, 1, False), ("1", 2, 2, True), ("2", 3, 4, False)], set(range(5))) == 2
    measures = part.findall("measure")
    assert [e.get("type") for e in measures[1].iter("ending")] == ["start"]
    right = measures[2].find("barline[@location='right']")
    assert [c.tag for c in right] == ["bar-style", "ending", "repeat"] and right.find("ending").get("type") == "stop"
    assert measures[3].find("barline").get("location") == "left"
    assert measures[4].find("barline/ending").get("type") == "discontinue"


def test_words_seen_by_two_systems_are_printed_once():
    parts = [ET.fromstring("<part id='P1'>" + "".join(
        f"<measure number='{k}'><attributes><divisions>24</divisions></attributes>{note('G4', 'whole', 96)}</measure>"
        for k in range(2)) + "</part>")]
    voice = {"staff": 1, "voices": ["G4 1"]}
    answers = [{"measures": [{"number": "0", "staves": [voice]}], "chords": [], "endings": [],
                "texts": [{"measure": "0", "quarters": 0, "staff": 1, "above": False, "text": "Last time, end"}]},
               {"measures": [{"number": "1", "staves": [voice]}], "chords": [], "endings": [],
                "texts": [{"measure": "1", "quarters": 0, "staff": 1, "above": True, "text": "Last time, end"}]}]
    rewritten, _ = apply(parts, [[0], [1]], answers, log=lambda m: None)
    assert rewritten == {(0, 0), (0, 1)}
    assert [len(m.findall("direction")) for m in parts[0].findall("measure")] == [0, 1]


def test_triplets_ties_and_a_second_voice():
    m = ET.fromstring("<measure number='2'><attributes><divisions>24</divisions></attributes>"
                      + note("D4", "quarter", 24) + note("E4", "quarter", 24) + note("D4", "half", 48) + "</measure>")
    voices = [[parse_event(e, 24) for e in "D4+G4 4t, E4 4t, D4 4t~, D4 8, G4+C5 4, G4+B4 8".split(", ")],
              [parse_event(e, 24) for e in "s 4, E4 4, D4 2".split(", ")]]
    replace(m, voices, {}, 1)
    assert [t.get("type") for t in m.iter("tuplet")] == ["start", "stop"]
    assert m.find("backup/duration").text == "96"
    assert ties_out(m) == {1: set(), 2: set()}
    assert voices_of(m, 24)["2"] == ["s 4", "E4 4", "D4 2"]


def test_chord_symbols_keep_their_printed_spelling():
    symbol = chord_symbol("B♭m7/A♭")
    assert (symbol.root().name, symbol.bass().name, symbol.chordKindStr) == ("B-", "A-", "m7")
    assert chord_symbol("Gm7b5").chordKindStr == "m7b5" and chord_symbol("hamba") is None
    part = m21.stream.Part([m21.stream.Measure([m21.note.Note("G4", quarterLength=4)])])
    score = m21.stream.Score([part])
    assert add_chords(score, [Chord(0, 2.5, "D7"), Chord(0, 0, "G"), Chord(5, 0, "C")]) == 2
    assert [(h.offset, h.figure) for h in part.recurse().getElementsByClass(m21.harmony.ChordSymbol)] == \
        [(0.0, "G"), (2.5, "D7")]


def test_chord_names_are_told_from_words():
    from readablemusic.chords import CHORD_NAME
    assert all(CHORD_NAME.fullmatch(name) for name in ["G", "D7", "B♭m7/A♭", "Gm7♭5", "F+7", "Esus4", "Fmaj7"])
    assert not any(CHORD_NAME.fullmatch(word) for word in ["Am-", "Be", "Ba", "hamba", "Tune:"])


def test_chord_symbols_are_flattened_for_the_pdf():
    from readablemusic.engrave import _for_reportlab
    svg = ('<g id="h" class="harm"><text x="5" y="8" font-size="0px"><tspan class="text">'
           '<tspan font-size="405px">B</tspan><tspan font-family="Leipzig" font-size="720px"></tspan>'
           '<tspan font-size="405px">m7/A</tspan><tspan font-family="Leipzig" font-size="720px"></tspan>'
           '</tspan></text></g>')
    assert '<text x="5" y="8" font-size="405px">Bbm7/Ab</text>' in _for_reportlab(svg)
    assert not chord_symbol("Gm7b5").chordStepModifications


def test_the_last_ending_is_left_open(tmp_path):
    from readablemusic.reader import open_endings
    xml = tmp_path / "s.musicxml"
    xml.write_text('<barline location="right"><ending number="1" type="stop" /><repeat direction="backward" />'
                   '</barline><barline location="left"><ending number="2" type="start" /></barline>'
                   '<barline location="right"><ending number="2" type="stop" /></barline>', encoding="utf-8")
    open_endings(xml)
    assert [m for m in __import__("re").findall(r'number="(\d)" type="(\w+)"', xml.read_text(encoding="utf-8"))] == \
        [("1", "stop"), ("2", "start"), ("2", "discontinue")]


def eighths(count, notes):
    """A part of 3/8 measures, the first with its attributes, each holding notes."""
    head = "<attributes><divisions>24</divisions><time><beats>3</beats><beat-type>8</beat-type></time></attributes>"
    return ET.fromstring("<part id='P1'>" + "".join(
        f"<measure number='{k + 1}'>{head if k == 0 else ''}{notes[k]}</measure>" for k in range(count)) + "</part>")


def answer_of(*measures, texts=()):
    return {"measures": [{"number": str(k), "staves": [{"staff": 1, "voices": [v]}]} for k, v in measures],
            "chords": [], "texts": list(texts), "endings": [], "repeats": []}


def test_fermatas_and_slurs_are_written_and_slurs_numbered_across_measures():
    ev = parse_event("G4 8.^)( [rez]", 24)
    assert (ev["dots"], ev["fermata"], ev["slurs"], ev["lyrics"]) == (1, True, (1, 1), {1: "rez"})
    part = eighths(3, [note("C6", "quarter", 24) + note("C6", "eighth", 12)] * 3)
    # An end with no start is dropped, a slur goes on over the barline, one that never ends is dropped.
    apply([part], [[0, 1, 2]], [answer_of((1, "G4 4)(, A4 8)("), (2, "B4 4), C5 8^("), (3, "D5 4, E5 8"))],
          log=lambda m: None)
    slurs = [(n.findtext("pitch/step"), [(x.get("type"), x.get("number")) for x in n.iter("slur")])
             for n in part.iter("note")]
    assert slurs == [("G", [("start", "1")]), ("A", [("stop", "1"), ("start", "1")]), ("B", [("stop", "1")]),
                     ("C", []), ("D", []), ("E", [])]
    assert [n.findtext("pitch/step") for n in part.iter("note") if n.find("notations/fermata") is not None] == ["C"]


def test_a_measure_holding_two_where_audiveris_missed_a_barline_is_split():
    # אתה הצבת, bar 21: two bars of 3/8 read as one.
    end = "<barline location='right'><bar-style>light-heavy</bar-style></barline>"
    part = eighths(2, [note("C4", "quarter", 24) + note("D4", "eighth", 12), note("C4", "half", 72) + end])
    text = {"measure": "2", "quarters": 2.0, "staff": 1, "above": True, "text": "rit."}
    rewritten, _ = apply([part], [[0, 1]], [answer_of((1, "C4 4, D4 8"), (2, "C4 8 [me-], C4 4^ [cha], F4 8 [al], "
                                                                          "G4 8 [ti-], F4 8 [ten]"), texts=[text])],
                         log=lambda m: None)
    measures = part.findall("measure")
    assert [m.get("number") for m in measures] == ["1", "2", "3"] and rewritten == {(0, 0), (0, 1), (0, 2)}
    assert [voices_of(m, 24)["1"] for m in measures[1:]] == [["C4 8", "C4 4"], ["F4 8", "G4 8", "F4 8"]]
    assert measures[1].find("barline") is None and measures[2].findtext("barline/bar-style") == "light-heavy"
    assert measures[2].findtext("direction/direction-type/words") == "rit."
    assert measures[2].find("note/lyric/text").text == "al"


def test_audiveris_pitch_is_kept_a_step_from_claudes_on_the_staff():
    # אתה הצבת, bar 22: Claude read E flat on the bottom line as D, and the C on its ledger line rightly.
    events = parse_voice("C4 8 [le-], F4 8, D4 8 [ját]", 24)
    assert measured(events, ["D4 4.", "F4 4", "Eb4 4"], 30) == 1
    assert [ev["pitches"] for ev in events] == [["C4"], ["F4"], ["Eb4"]]
    # Only where the notes pair off, and not for chords.
    assert measured(parse_voice("C5 4, D5 16, C5 16", 24), ["D5 4", "C5 4"], 30) == 0
    assert measured(parse_voice("G4+B4 4, C5 8", 24), ["A4 4", "C5 8"], 30) == 0


def test_claude_looks_again_at_measures_that_do_not_add_up():
    part = eighths(4, [note("G4", "eighth", 12)] * 4)
    answer = answer_of((1, "C4 8"), (2, "Eb5 4, Eb5 4"), (3, "C4 8, C4 4, F4 8, G4 8, F4 8"), (4, "D4 4, D4 8, r 8"))
    # The first measure may be a pickup, and the third holds two.
    assert doubts(answer, [part], {"1": 0, "2": 1, "3": 2, "4": 3}) == [
        "- measure 2, staff 1, voice 1: its notes add up to 4 eighths, but a measure of 3/8 has 3",
        "- measure 4, staff 1, voice 1: its notes add up to 4 eighths, but a measure of 3/8 has 3"]
    assert doubts(answer_of((2, "Eb5 4 x")), [part], {"2": 1})[0].startswith("- measure 2, staff 1, voice 1: not an event")


def test_circled_numbers_are_numbers_in_a_circle():
    words = direction("②", True).find("direction-type/words")
    assert (words.text, words.get("enclosure")) == ("2", "circle")


def test_a_system_is_turned_level():
    img = Image.new("L", (400, 100), 255)
    ImageDraw.Draw(img).line([(0, 60), (400, 40)], fill=0, width=3)

    def row(image, x):
        column = [image.getpixel((x, y)) for y in range(100)]
        return column.index(min(column))
    turned = level(img, -20 / 400)
    assert abs(row(turned, 50) - row(turned, 350)) <= 1
    assert level(img, 0.0001) is img
