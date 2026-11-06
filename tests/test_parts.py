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


def test_voice_type_rejects_ocr_junk_and_reads_a_misread_b():
    assert voice_type("TI]") is None
    assert voice_type("82") == ("Bass", "B", "2")
    assert voice_type("מצו-סופרן") == ("Mezzo-soprano", "Mz", "")


def test_first_system_name_beats_later_abbreviations():
    score = m21.stream.Score([_part(_voice("Baritone", B1=9), "C3")])
    standardize_names(score)
    assert score.parts[0].partName == "Baritone"


def test_two_line_names_name_a_shared_staff():
    score = m21.stream.Score([_part(_voice("Lead"), "C4"), _part(_voice("Bass"), "C3")])
    assert standardize_names(score, {"Lead": "Tenor", "Bass": "Bari"}) == []
    assert [(p.partName, p.partAbbreviation) for p in score.parts] == [("Tenor, Lead", "T L"), ("Baritone, Bass", "Bar B")]


def test_four_unnamed_staves_are_satb():
    score = m21.stream.Score([_part(_voice("Voice"), "A4"), _part(_voice("Voice"), "F4"),
                              _part(_voice("Voice"), "A4"), _part(_voice("Voice"), "D3")])
    assert standardize_names(score) == []
    assert [p.partName for p in score.parts] == ["Soprano", "Alto", "Tenor", "Bass"]


def test_a_stray_second_voice_does_not_make_a_shared_staff():
    part = _part(_voice("Voice"), "A4")
    for _ in range(9):
        m = m21.stream.Measure()
        m.append(m21.note.Note("A4"))
        part.append(m)
    part.getElementsByClass(m21.stream.Measure)[0].append(m21.chord.Chord(["A4", "F4"]))
    standardize_names(m21.stream.Score([part]))
    assert part.partName == "Soprano"


def test_piano_is_kept_only_if_it_plays_like_one():
    piano = _part(_voice("Piano"), "C4")
    piano.getElementsByClass(m21.stream.Measure)[0].append(m21.chord.Chord(["C4", "E4", "G4"]))
    voice = _part(_voice("Piano"), "A4", "A4")
    assert standardize_names(m21.stream.Score([piano, voice])) == []
    assert [p.partName for p in (piano, voice)] == ["Piano", "Soprano"]


def test_a_lone_unnamed_staff_gets_no_voice_type():
    part = _part(_voice("Voice"), "C3", clef=m21.clef.BassClef())
    assert standardize_names(m21.stream.Score([part])) == []
    assert (part.partName, part.partAbbreviation) == ("Voice", None)


def test_a_role_is_capitalized():
    part = _part(_voice("solo"), "C4")
    standardize_names(m21.stream.Score([part]))
    assert part.partName == "Solo"
