"""Decode the green 7-segment lap timer out of a single cropped frame."""

from __future__ import annotations

import numpy as np

from .config import (
    CELLS,
    GREEN_MIN,
    GREEN_OVER_BLUE,
    GREEN_OVER_RED,
    PAT,
    SEG,
    SEG_ON,
    SEG_PATCH,
    Y0,
    Y1,
)


def green_mask(frame: np.ndarray) -> np.ndarray:
    """Boolean mask of green-lit HUD pixels in an RGB frame."""
    r = frame[..., 0].astype(int)
    g = frame[..., 1].astype(int)
    b = frame[..., 2].astype(int)
    return (g > GREEN_MIN) & (g - r > GREEN_OVER_RED) & (g - b > GREEN_OVER_BLUE)


def read_digit(mask: np.ndarray, cell: tuple[int, int]) -> str:
    """Read one digit cell. Returns '0' when fully unlit, '?' when unrecognised."""
    cx0, cx1 = cell
    w = cx1 - cx0
    h = Y1 - Y0
    lit = set()
    for name, (fx, fy) in SEG.items():
        px = int(cx0 + fx * w)
        py = int(Y0 + fy * h)
        patch = mask[
            max(0, py - SEG_PATCH) : py + SEG_PATCH + 1,
            max(0, px - SEG_PATCH) : px + SEG_PATCH + 1,
        ]
        if patch.size and patch.mean() > SEG_ON:
            lit.add(name)
    if not lit:
        return "0"
    return PAT.get(frozenset(lit), "?")


def decode_frame(frame: np.ndarray) -> float | None:
    """Decode one cropped RGB frame to elapsed lap seconds.

    Returns None when any digit is unreadable, which happens routinely during
    HUD transitions and is expected — callers should treat it as a gap, not an error.
    """
    mask = green_mask(frame)
    digits = {name: read_digit(mask, cell) for name, cell in CELLS.items()}
    if "?" in digits.values():
        return None
    minutes = int(digits["D2"])
    seconds = int(digits["D3"]) * 10 + int(digits["D4"])
    hundredths = int(digits["D5"]) * 10 + int(digits["D6"])
    return minutes * 60 + seconds + hundredths / 100.0
