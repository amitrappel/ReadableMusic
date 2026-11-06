import music21 as m21

from readablemusic.parts import Voice, align, name_key, standardize_names, voice_type


def voices(*names):
    out = []
    for n in names:
        v = Voice()
        v.names[n] += 1
        out.append(v)
    return out


def test_name_key_handles_ocr_and_styles():
    assert name_key("B l") == name_key("Bl") == name_key("B1") == "b1"
    assert name_key("T1 1") == name_key("Tenorl") == "t1"
    assert name_key("Soprano") == name_key("S") == "s"
    assert name_key("Voice") == ""


def test_align_skips_hidden_staves():
    vs = voices("Solo", "S", "A", "T", "B")
    assert align(["S", "T", "B"], vs) == [1, 3, 4]


def test_align_matches_full_names_to_abbreviations():
    vs = voices("S", "M", "A", "T1", "T2", "B1", "B2")
    staves = ["Soprano", "Mezzo", "Alto", "Tenorl", "Tenor2", "Baritone", "Bass"]
    assert align(staves, vs) == [0, 1, 2, 3, 4, 5, 6]


def test_align_unnamed_staves_follow_order():
    vs = voices("S", "A", "T", "B")
    assert align(["Voice", "Voice", "T", "B"], vs) == [0, 1, 2, 3]


def test_align_uses_every_name_of_a_voice():
    # Singers' names on the first system, voice names after it.
    vs = voices("Shani", "Yael", "Salit", "Guy", "Doron")
    for v, short in zip(vs, ["S", "Mezzo", "A", "T", "B"]):
        v.names[short] += 3
    assert align(["Mezzo", "T"], vs) == [1, 3]


def test_voice_name_prefers_first_system_and_keeps_abbreviation():
    v = Voice(first="Shani")
    v.names.update({"Shani": 1, "S": 5})
    assert (v.name, v.abbreviation) == ("Shani", "S")
    v = Voice(first="13")  # OCR noise on the first system
    v.names.update({"13": 1, "Tenor": 4})
    assert (v.name, v.abbreviation) == ("Tenor", None)


def _part(voice, *pitches, clef=None):
    part = m21.stream.Part()
    part.source_voice, part.partName = voice, voice.name
    m = m21.stream.Measure()
    if clef:
        m.append(clef)
    for p in pitches:
        m.append(m21.note.Note(p))
    part.append(m)
    return part


def _voice(first, **names):
    v = Voice(first=first)
    v.names.update({first: 1, **names})
    return v


def test_voice_type_reads_styles_and_ocr():
    assert voice_type("Soprano") == voice_type("S.") == ("Soprano", "S", "")
    assert voice_type("T1 1") == voice_type("Tenorl") == ("Tenor", "T", "1")
    assert voice_type("Mezzo") == ("Mezzo-soprano", "Mz", "")
    assert voice_type("Shani") is None


def test_standard_names_move_singers_to_a_footnote():
    score = m21.stream.Score([
        _part(_voice("Shani", S=3), "A4"),
        _part(_voice("Yael", Mezzo=3), "F4"),
        _part(_voice("Lead"), "C4"),
        _part(_voice("Guy"), "C4", clef=m21.clef.Treble8vbClef()),  # singers only: from the clef
    ])
    footnotes = standardize_names(score)
    assert [(p.partName, p.partAbbreviation) for p in score.parts][:2] == [("Soprano", "S"), ("Mezzo-soprano", "Mz")]
    assert score.parts[2].partName == "Lead"
    assert footnotes == ["Original part names: Soprano – Shani, Mezzo-soprano – Yael, Tenor – Guy"]


def test_parts_of_one_voice_type_are_numbered():
    score = m21.stream.Score([_part(_voice("Tenor"), "C4"), _part(_voice("Tenor"), "C4")])
    assert standardize_names(score) == []
    assert [p.partName for p in score.parts] == ["Tenor 1", "Tenor 2"]
