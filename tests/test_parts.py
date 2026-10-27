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
