from readablemusic.lyrics import clean_text


def test_ligatures_are_split():
    assert clean_text("ﬁjr") == "fijr"


def test_niqqud_is_removed():
    assert clean_text("שָׁלוֹם") == "שלום"
