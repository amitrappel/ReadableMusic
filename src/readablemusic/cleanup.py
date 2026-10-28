"""Page clean-up before OMR."""

import numpy as np
from PIL import Image

from .scale import _otsu

MARGIN_GAP = 3.0  # empty interlines that separate the music from titles and footers
MAX_ABOVE = 6.0  # interlines above the first staff line for chord names, tempo marks, ...
MAX_BELOW = 10.0  # interlines below the last staff line for low notes and several verses
MIN_MATCHES_SHARE = 0.2  # staff matches needed, as a share of the sampled columns


def blank_outside_music(img: Image.Image, interline: float) -> Image.Image:
    """Whiten titles, headers and footers, which Audiveris otherwise reads as lyrics.

    From the first and the last staff line, walk away from the music to the first band
    of MARGIN_GAP empty interlines, or at most MAX_ABOVE / MAX_BELOW interlines for tight
    layouts; everything beyond is blanked.
    """
    a = np.asarray(img.convert("L"))
    black = a <= _otsu(a)  # Otsu puts levels up to and including t in the dark class
    extent = staff_extent(black, interline)
    if extent is None:
        return img
    first, last = extent
    empty = black.sum(axis=1) <= black.shape[1] // 200  # tolerate scan specks
    gap = max(1, round(MARGIN_GAP * interline))
    top = max(_gap(empty, first, -1, gap), round(first - MAX_ABOVE * interline))
    bottom = min(_gap(empty, last, +1, gap), round(last + MAX_BELOW * interline))
    out = a.copy()
    out[:max(top, 0)] = 255
    out[bottom:] = 255
    return Image.fromarray(out)


def staff_extent(black: np.ndarray, interline: float, columns: int = 300) -> tuple[int, int] | None:
    """Return the rows of the first and the last staff line on the page.

    Works column by column, like the scale estimate, so slightly skewed scans still work:
    in each sampled column, five line starts spaced one interline apart make a staff.
    Banners, rules and text do not, and the 1st/99th percentiles drop stray matches.
    """
    h, w = black.shape
    tops, bottoms = [], []
    for x in np.linspace(0, w - 1, min(columns, w)).astype(int):
        col = black[:, x].astype(np.int8)
        edges = np.flatnonzero(np.diff(col)) + 1
        starts = edges[col[edges] == 1]
        if len(starts) < 5:
            continue
        d = np.diff(starts)
        window = np.lib.stride_tricks.sliding_window_view(d, 4)
        staff = (np.abs(window - interline) <= 0.2 * interline).all(axis=1)
        k = np.flatnonzero(staff)
        tops.extend(starts[k])
        bottoms.extend(starts[k + 4])
    if len(tops) < MIN_MATCHES_SHARE * columns:  # too few to trust, e.g. a noisy scan
        return None
    return int(np.percentile(tops, 1)), int(np.percentile(bottoms, 99))


def _gap(empty: np.ndarray, start: int, step: int, gap: int) -> int:
    """Walk from row start by step; return the music-side row of the first run of gap empty
    rows, or the page edge if there is none."""
    run = 0
    y = start
    while 0 <= y < len(empty):
        run = run + 1 if empty[y] else 0
        if run == gap:
            return y - step * (gap - 1)
        y += step
    return 0 if step < 0 else len(empty)
