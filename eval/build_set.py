"""Build an evaluation set with known answers from Bach chorales bundled with music21.

For each chorale, writes to eval/data/<name>/:
  truth-satb.musicxml   / satb/page-N.png     one voice per staff
  truth-shared.musicxml / shared/page-N.png   S+A on one staff, T+B on another
                          bad/page-N.jpg      satb pages degraded like a poor scan

Usage: uv run python eval/build_set.py [count]
"""

import copy
import io
import sys
from pathlib import Path

import music21 as m21
import numpy as np
import resvg_py
import verovio
from PIL import Image, ImageFilter

DATA = Path(__file__).parent / "data"
PAGE_WIDTH_PX = 2480  # A4 at 300 DPI


def chorales(count: int) -> list[str]:
    """Pick plain four-voice chorales with lyrics, in a stable order."""
    picked = []
    for md in sorted(m21.corpus.search("bach", fileExtensions=("mxl",)), key=lambda m: str(m.sourcePath)):
        path = str(md.sourcePath)
        score = m21.corpus.parse(path)
        if len(score.parts) == 4 and any(n.lyric for n in score.parts[0].recurse().notes):
            picked.append(path)
            if len(picked) == count:
                break
    return picked


def clean(score: m21.stream.Score) -> m21.stream.Score:
    """Drop titles and credits, and name the parts S, A, T, B."""
    score.metadata = m21.metadata.Metadata()
    for credit in list(score.getElementsByClass(m21.text.TextBox)):
        score.remove(credit)
    for part, name in zip(score.parts, "SATB"):
        part.partName = name
        part.partAbbreviation = name
    return score


def shared(score: m21.stream.Score) -> m21.stream.Score:
    """Put S+A on one staff and T+B on another, as two voices per staff."""
    merged = m21.stream.Score()
    for upper, lower, name in ((0, 1, "SA"), (2, 3, "TB")):
        part = m21.stream.Part()
        part.partName = name
        hi = score.parts[upper].getElementsByClass(m21.stream.Measure)
        lo = score.parts[lower].getElementsByClass(m21.stream.Measure)
        for mh, ml in zip(hi, lo):
            m = m21.stream.Measure(number=mh.number)
            if mh.paddingLeft:
                m.paddingLeft = mh.paddingLeft
            for cls in (m21.clef.Clef, m21.key.KeySignature, m21.meter.TimeSignature):
                for el in mh.getElementsByClass(cls):
                    m.insert(0, copy.deepcopy(el))
            for src, stem, vid in ((mh, "up", 1), (ml, "down", 2)):
                v = m21.stream.Voice(id=vid)
                for n in src.recurse().notesAndRests:
                    n = copy.deepcopy(n)
                    if n.isNote or n.isChord:
                        n.stemDirection = stem
                    if vid == 2:
                        n.lyrics = []  # one lyric line per staff, as in printed shared staves
                    v.insert(n.getOffsetInHierarchy(src), n)
                m.insert(0, v)
            part.append(m)
        merged.append(part)
    return merged


def render(musicxml: Path, out_dir: Path) -> list[Path]:
    tk = verovio.toolkit()
    tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 45, "footer": "none", "header": "none"})
    tk.loadFile(str(musicxml))
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    for n in range(1, tk.getPageCount() + 1):
        png = bytes(resvg_py.svg_to_bytes(svg_string=tk.renderToSVG(n), width=PAGE_WIDTH_PX, background="white"))
        dest = out_dir / f"page-{n}.png"
        dest.write_bytes(png)
        pages.append(dest)
    return pages


def degrade(src: Path, dest: Path, seed: int) -> None:
    """Fake a poor scan: 200 DPI, skew, shadow, grain, specks, blur, JPEG."""
    rng = np.random.default_rng(seed)
    img = Image.open(src).convert("L")
    img = img.resize((img.width * 2 // 3, img.height * 2 // 3), Image.LANCZOS)
    img = img.rotate(rng.uniform(-2, 2), resample=Image.BICUBIC, expand=True, fillcolor=255)
    a = np.asarray(img, dtype=np.float32)
    h, w = a.shape
    a = a * (np.linspace(0.65, 1.0, w)[None, :] * np.linspace(0.85, 1.0, h)[:, None])
    a = a + rng.normal(0, 12, a.shape)
    a[rng.random(a.shape) < 0.002] = 0
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.9))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=45)
    dest.write_bytes(buf.getvalue())


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    for i, path in enumerate(chorales(count)):
        name = Path(path).stem
        out = DATA / name
        out.mkdir(parents=True, exist_ok=True)
        satb = clean(m21.corpus.parse(path))
        satb.write("musicxml", out / "truth-satb.musicxml")
        shared(satb).write("musicxml", out / "truth-shared.musicxml")
        pages = render(out / "truth-satb.musicxml", out / "satb")
        render(out / "truth-shared.musicxml", out / "shared")
        (out / "bad").mkdir(exist_ok=True)
        for p in pages:
            degrade(p, out / "bad" / p.with_suffix(".jpg").name, seed=i)
        print(f"{name}: {len(pages)} page(s)")


if __name__ == "__main__":
    main()
