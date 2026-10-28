"""Estimate staff-line spacing ("interline") of a page image."""

import numpy as np
from PIL import Image

# Audiveris works best with about 20-30 px between staff lines (see docs/phase0-findings.md).
TARGET_INTERLINE = 24


def estimate_interline(img: Image.Image, columns: int = 300) -> float | None:
    """Return the most common distance in pixels between staff lines, or None if no staves."""
    return staff_evidence(img, columns)[0]


def staff_evidence(img: Image.Image, columns: int = 300) -> tuple[float | None, int]:
    """Return (interline, support): support counts the staff-like samples behind the estimate.

    Scans a sample of pixel columns. In each column, a black run followed by a white
    run spans one line plus one gap, so the most frequent black+white length is the
    interline. This is the classic OMR scale estimation. To ignore scan noise, a
    period only counts when it repeats over four consecutive gaps, as in a staff.
    """
    a = np.asarray(img.convert("L"))
    black = a <= _otsu(a)  # Otsu puts levels up to and including t in the dark class
    h, w = black.shape
    counts = np.zeros(h + 1, dtype=np.int64)
    for x in np.linspace(0, w - 1, min(columns, w)).astype(int):
        col = black[:, x].astype(np.int8)
        edges = np.flatnonzero(np.diff(col)) + 1
        starts = edges[col[edges] == 1]  # white -> black transitions
        if len(starts) < 5:
            continue
        d = np.diff(starts)
        window = np.lib.stride_tricks.sliding_window_view(d, 4)
        staff_like = window.max(axis=1) <= window.min(axis=1) * 1.15
        np.add.at(counts, window[staff_like, 0], 1)
    counts[:4] = 0  # ignore noise-sized periods
    if counts.sum() == 0:
        return None, 0
    peak = int(counts.argmax())
    # Refine with a weighted mean around the peak, since true spacing is fractional.
    lo, hi = max(peak - 1, 0), peak + 2
    return float(np.average(np.arange(lo, hi), weights=counts[lo:hi])), int(counts[lo:hi].sum())


def _otsu(a: np.ndarray) -> int:
    hist = np.bincount(a.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    cum = np.cumsum(hist)
    cum_mean = np.cumsum(hist * np.arange(256))
    w0 = cum / total
    w1 = 1 - w0
    with np.errstate(divide="ignore", invalid="ignore"):
        m0 = cum_mean / cum
        m1 = (cum_mean[-1] - cum_mean) / (total - cum)
        between = w0 * w1 * (m0 - m1) ** 2
    return int(np.nanargmax(between))
