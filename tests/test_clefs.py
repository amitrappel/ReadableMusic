import music21 as m21

from readablemusic.clefs import fix_clefs, moved


def _part(clefs_and_notes):
    part = m21.stream.Part()
    for number, (clef, notes) in enumerate(clefs_and_notes, start=1):
        m = m21.stream.Measure(number=number)
        if clef:
            m.append(m21.clef.clefFromString(clef))
        if number == 1:
            m.append(m21.key.KeySignature(-1))
        for name in notes:
            m.append(m21.note.Note(name, quarterLength=1))
        part.append(m)
    return part


def test_a_short_run_in_a_misread_clef_is_reread():
    # A bass part whose third measure was read in treble clef: its notes came out a 13th too high.
    bass = ["C3", "D3", "E3", "F3"]
    part = _part([("F4", bass), (None, bass), ("G2", ["A4", "B-4", "C5", "D5"]), ("F4", bass), (None, bass)])
    assert fix_clefs(m21.stream.Score([part])) == 1
    m3 = part.measure(3)
    assert [n.nameWithOctave for n in m3.notes] == ["C3", "D3", "E3", "F3"]
    assert [c.sign for c in part.recurse().getElementsByClass(m21.clef.Clef)] == ["F"]


def test_a_long_run_in_another_clef_is_kept():
    treble = ["C5", "D5", "E5", "F5"]
    part = _part([("F4", ["C3"] * 4)] * 14 + [("G2", treble)] + [(None, treble)] * 12)
    assert fix_clefs(m21.stream.Score([part])) == 0
    assert part.measure(16).notes[0].nameWithOctave == "C5"


def test_moved_keeps_the_key_and_printed_accidentals():
    key = m21.key.KeySignature(-1)
    assert moved(m21.pitch.Pitch("B-4"), -12, key).nameWithOctave == "D3"  # staff position of B4 in bass clef
    assert moved(m21.pitch.Pitch("A4"), -12, key).nameWithOctave == "C3"
    assert moved(m21.pitch.Pitch("B4"), -1, key).nameWithOctave == "A4"  # a printed natural against the key stays
    assert moved(m21.pitch.Pitch("C5"), -7, key).nameWithOctave == "C4"
