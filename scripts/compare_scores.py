"""Compare two MusicXML results of the same score: counts, title, credits, part names, lyrics.

Usage: uv run python -X utf8 scripts/compare_scores.py <a.musicxml> <b.musicxml>
Part ids are random, so they are not compared.
"""

import re
import sys
import xml.etree.ElementTree as ET


def summary(path: str) -> dict:
    root = ET.parse(path).getroot()

    def texts(tag: str) -> list[str]:
        return [" ".join(e.text.split()) for e in root.iter(tag) if e.text and e.text.strip()]

    return {
        "notes": len(list(root.iter("note"))),
        "lyrics": len(list(root.iter("lyric"))),
        "measures": len(re.findall(r"<measure[ >]", open(path, encoding="utf-8").read())),
        "title": texts("work-title") + texts("movement-title"),
        "credits": texts("credit-words"),
        "parts": texts("part-name"),
        "syllables": texts("text"),
    }


def main() -> None:
    a, b = summary(sys.argv[1]), summary(sys.argv[2])
    for key in a:
        if a[key] == b[key]:
            print(f"  same  {key}: {a[key] if key != 'syllables' else len(a[key])}")
        elif key == "syllables":
            changed = [(i, x, y) for i, (x, y) in enumerate(zip(a[key], b[key])) if x != y]
            print(f"  DIFF  {key}: {len(a[key])} vs {len(b[key])}, first changes {changed[:6]}")
        else:
            print(f"  DIFF  {key}:\n    a={a[key]}\n    b={b[key]}")


if __name__ == "__main__":
    main()
