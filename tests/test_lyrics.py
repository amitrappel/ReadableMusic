import music21 as m21

from readablemusic.lyrics import clean_text, close_words, drop_stray_lines


def test_ligatures_are_split():
    assert clean_text("ﬁjr") == "fijr"


def test_niqqud_is_removed():
    assert clean_text("שָׁלוֹם") == "שלום"


def test_tidy_drops_chords_and_credits():
    from readablemusic.tidy import tidy
    m = m21.stream.Measure([m21.harmony.ChordSymbol("D7"), m21.expressions.TextExpression("G7"),
                            m21.expressions.TextExpression("Last time, end"),
                            m21.expressions.TextExpression("South African freedom song, transl. 1984"),
                            m21.note.Note("C4", quarterLength=4)])
    s = tidy(m21.stream.Score([m21.stream.Part([m])]))
    assert [t.content for t in s.recurse().getElementsByClass(m21.expressions.TextExpression)] == ["Last time, end"]
    assert not s.recurse().getElementsByClass(m21.harmony.Harmony)


def test_open_words_are_closed():
    part = m21.stream.Part()
    for text, syllabic in [("pa...", "begin"), ("la", "single"), ("hal", "begin"), ("le", "middle"), ("lu", "end"),
                           ("oh", "begin")]:
        n = m21.note.Note("C4")
        n.lyrics.append(m21.note.Lyric(text, syllabic=syllabic))
        part.append(n)
    close_words(part)
    assert [n.lyrics[0].syllabic for n in part.notes] == ["single", "single", "begin", "middle", "end", "single"]


def test_marks_read_as_lyrics_are_dropped_per_system():
    # System 1: the words are verse 2, a fermata read as 'm' is verse 3. System 2: words are verse 1,
    # a dynamic read as 'f' is verse 2 and a lone Hebrew syllable is verse 3.
    part = m21.stream.Part()
    for number, (verses, new_system) in enumerate([({2: "Kommt", 3: "m"}, False), ({2: "Sohn"}, False),
                                                   ({1: "all"}, True), ({1: "die", 2: "f", 3: "ש"}, False)], start=1):
        m = m21.stream.Measure(number=number)
        if new_system:
            m.insert(0, m21.layout.SystemLayout(isNew=True))
        n = m21.note.Note("C4", quarterLength=4)
        for verse, text in verses.items():
            n.lyrics.append(m21.note.Lyric(text, number=verse))
        m.append(n)
        part.append(m)
    drop_stray_lines(m21.stream.Score([part]))
    assert [[(ly.number, ly.text) for ly in n.lyrics] for n in part.recurse().notes] == [
        [(1, "Kommt")], [(1, "Sohn")], [(1, "all")], [(1, "die"), (2, "ש")]]
