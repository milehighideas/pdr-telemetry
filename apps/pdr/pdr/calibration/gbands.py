"""Green-only band detection — this is what produced the CELLS now in config.py.

Expects `g_*.png` crops of the green lap timer.
"""

from __future__ import annotations

import glob
import os

import numpy as np
from PIL import Image


def gmask(a):
    R = a[..., 0].astype(int)
    G = a[..., 1].astype(int)
    B = a[..., 2].astype(int)
    return (G > 105) & (G - R > 35) & (G - B > 25)


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


def run(frames_dir: str) -> None:
    files = sorted(glob.glob(os.path.join(frames_dir, "g_*.png")))
    if not files:
        print(f"no g_*.png frames in {frames_dir}")
        return
    arrs = [np.asarray(Image.open(f).convert("RGB")).astype(int) for f in files]
    union = np.zeros(arrs[0].shape[:2], bool)
    for a in arrs:
        union |= gmask(a)
    print("crop size WxH:", arrs[0].shape[1], arrs[0].shape[0])
    print("X bands:", [(b, b[1] - b[0] + 1) for b in bands(union, 0, 2)])
    print("Y bands:", [(b, b[1] - b[0] + 1) for b in bands(union, 1, 2)])
