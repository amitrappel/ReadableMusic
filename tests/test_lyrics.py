from readablemusic.lyrics import clean_text


def test_ligatures_are_split():
    assert clean_text("ﬁjr") == "fijr"


def test_niqqud_is_removed():
    assert clean_text("שָׁלוֹם") == "שלום"


def test_tidy_drops_chords_and_credits():
    import music21 as m21
    from readablemusic.tidy import tidy
    m = m21.stream.Measure([m21.harmony.ChordSymbol("D7"), m21.expressions.TextExpression("G7"),
                            m21.expressions.TextExpression("Last time, end"),
                            m21.expressions.TextExpression("South African freedom song, transl. 1984"),
                            m21.note.Note("C4", quarterLength=4)])
    s = tidy(m21.stream.Score([m21.stream.Part([m])]))
    assert [t.content for t in s.recurse().getElementsByClass(m21.expressions.TextExpression)] == ["Last time, end"]
    assert not s.recurse().getElementsByClass(m21.harmony.Harmony)
