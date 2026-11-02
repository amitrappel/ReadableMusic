from readablemusic.parts import Voice, align, name_key


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
