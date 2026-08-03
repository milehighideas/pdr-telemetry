"""Validate the shipped decoder against hand-labelled frames.

Expects crops named `g_<MMSSHH>_<frame>.png`, where MMSSHH is the lap time you read
off the frame by eye — e.g. `g_022089_470.png` means 2:20.89. Each frame is decoded
and compared against that label, so this is a real regression test of
`pdr.decode`, not a reimplementation of it.
"""

from __future__ import annotations

import glob
import os

import numpy as np
from PIL import Image

from ..decode import decode_frame


def expected_seconds(filename: str) -> float:
    """Parse the MMSSHH label out of a `g_<MMSSHH>_<frame>.png` name."""
    label = os.path.basename(filename).split("_")[1]
    minutes = int(label[1])
    seconds = int(label[2:4])
    hundredths = int(label[4:6])
    return minutes * 60 + seconds + hundredths / 100


def run(frames_dir: str) -> int:
    files = sorted(glob.glob(os.path.join(frames_dir, "g_*.png")))
    if not files:
        print(f"no g_*.png frames in {frames_dir}")
        return 1
    ok = 0
    for f in files:
        a = np.asarray(Image.open(f).convert("RGB"))
        got = decode_frame(a)
        want = expected_seconds(f)
        good = got is not None and abs(got - want) < 0.005
        ok += good
        print(
            f"{os.path.basename(f):22s} -> {got}  expect {want}  "
            f"{'OK' if good else 'FAIL'}"
        )
    print(f"{ok}/{len(files)}")
    return 0 if ok == len(files) else 1
