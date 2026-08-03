"""Band detection restricted to a chosen subset of frames.

Same idea as `bands`, but with a lower threshold and only the frames whose names
match given prefixes — used when a few extreme frames (all-segments-lit) give a
cleaner union than the whole sample set.
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
    return out


def run(frames_dir: str, prefixes: tuple[str, ...] = ("v", "x")) -> None:
    files: list[str] = []
    for p in prefixes:
        files += sorted(glob.glob(os.path.join(frames_dir, f"{p}*.png")))
    if not files:
        print(f"no frames matching {prefixes} in {frames_dir}")
        return
    arrs = [np.asarray(Image.open(f).convert("RGB")).astype(int) for f in files]
    union = np.zeros(arrs[0].shape[:2], bool)
    for a in arrs:
        r, g = litmask(a)
        union |= r | g
    print("size", arrs[0].shape[1], "x", arrs[0].shape[0])
    print("X bands:", [(b, b[1] - b[0] + 1) for b in bands(union, 0, 2)])
    print("Y bands:", [(b, b[1] - b[0] + 1) for b in bands(union, 1, 2)])
