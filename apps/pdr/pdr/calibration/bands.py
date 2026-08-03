"""Auto-detect digit x/y bands from the union of lit pixels across sample frames.

Run on a directory of PNG crops to find where the digit cells actually sit.
The X bands become the CELLS coordinates in pdr.config.
"""

from __future__ import annotations

import glob
import os

import numpy as np
from PIL import Image


def litmask(a):
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    red = (R > 105) & (R - G > 45) & (R - B > 45)
    green = (G > 105) & (G - R > 35) & (G - B > 25)
    return red, green


def bands(mask, axis, thr):
    prof = mask.sum(axis)
    on = prof > thr
    out = []
    s = None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        if not v and s is not None:
            out.append((s, i - 1))
            s = None
    if s is not None:
        out.append((s, len(on) - 1))
    return out, prof


def run(frames_dir: str) -> None:
    # union of lit pixels across all frames, to capture every segment
    files = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if not files:
        print(f"no PNG frames in {frames_dir}")
        return
    arrs = [np.asarray(Image.open(f).convert("RGB")).astype(int) for f in files]
    union = np.zeros(arrs[0].shape[:2], bool)
    for a in arrs:
        r, g = litmask(a)
        union |= r | g
    xb, _ = bands(union, 0, 3)
    yb, _ = bands(union, 1, 3)
    print("X bands (col ranges of lit content):")
    for b in xb:
        print("  ", b, "w=", b[1] - b[0] + 1)
    print("Y bands:")
    for b in yb:
        print("  ", b, "h=", b[1] - b[0] + 1)
