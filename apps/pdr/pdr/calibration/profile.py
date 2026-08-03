"""Column profile of lit pixels — the first look at where digits sit in a crop."""

from __future__ import annotations

import glob
import os

import numpy as np
from PIL import Image


def masks(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    red = (R > 110) & (R - G > 50) & (R - B > 50)
    green = (G > 110) & (G - R > 40) & (G - B > 30)
    return red, green


def run(frames_dir: str) -> None:
    for f in sorted(glob.glob(os.path.join(frames_dir, "*.png"))):
        im = Image.open(f)
        red, green = masks(im)
        name = os.path.basename(f)
        # column profile of red
        colred = red.sum(0)
        print(
            "===", name, "size", im.size,
            "redpx", int(red.sum()), "greenpx", int(green.sum()),
        )
        # print column sums compressed to width ~ every 4px
        prof = "".join(str(min(9, int(c / 2))) for c in colred)
        print("colred:", prof)
