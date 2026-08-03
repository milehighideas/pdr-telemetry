"""The abandoned red delta-time decoder, kept for reference.

The PDR also renders a red/green *delta* display — time gained or lost against a
reference lap — at crop (1600, 378), 300x72. This decodes it, with sign taken from
whether red or green pixels dominate.

It was abandoned as a lap-timing source: the delta is relative to a reference lap
and does not reset cleanly at the finish line, so crossings are ambiguous. The
green absolute lap timer in `pdr.decode` replaced it. Kept because the sign
and colour-mass logic is the only worked example of reading a two-colour HUD field,
which is likely relevant if the rally overlay ever needs decoding.
"""

from __future__ import annotations

import glob
import os
import sys

import numpy as np
from PIL import Image

# crop coords assume native crop x0=1600 y0=378 w=300 h=72
W, H = 300, 72
CELLS = {"D1": (72, 110), "D2": (119, 159), "D3": (181, 219), "D4": (228, 266)}
Y0, Y1 = 6, 58
SEG = {
    "a": (0.50, 0.10), "b": (0.84, 0.30), "c": (0.84, 0.72),
    "d": (0.50, 0.90), "e": (0.16, 0.72), "f": (0.16, 0.30), "g": (0.50, 0.50),
}
PAT = {
    frozenset("abcdef"): "0", frozenset("bc"): "1", frozenset("abdeg"): "2",
    frozenset("abcdg"): "3", frozenset("bcfg"): "4", frozenset("acdfg"): "5",
    frozenset("acdefg"): "6", frozenset("abc"): "7", frozenset("abcdefg"): "8",
    frozenset("abcdfg"): "9",
}


def lit_masks(a):
    R = a[..., 0].astype(int)
    G = a[..., 1].astype(int)
    B = a[..., 2].astype(int)
    red = (R > 105) & (R - G > 45) & (R - B > 45)
    green = (G > 105) & (G - R > 35) & (G - B > 25)
    return red, green


def seg_on(mask, cx0, cx1, fx, fy):
    w = cx1 - cx0
    h = Y1 - Y0
    px = int(cx0 + fx * w)
    py = int(Y0 + fy * h)
    patch = mask[max(0, py - 4) : py + 5, max(0, px - 5) : px + 6]
    return patch.mean() if patch.size else 0.0


def decode_digit(mask, cell):
    cx0, cx1 = cell
    fr = {k: seg_on(mask, cx0, cx1, *SEG[k]) for k in SEG}
    on = {k for k, v in fr.items() if v > 0.30}
    return PAT.get(frozenset(on)), on, fr


def decode_array(a, debug: bool = False) -> str:
    red, green = lit_masks(a)
    # sign by colour mass across all digit cells
    rx = sum(int(red[Y0:Y1, c[0] : c[1]].sum()) for c in CELLS.values())
    gx = sum(int(green[Y0:Y1, c[0] : c[1]].sum()) for c in CELLS.values())
    mask = red | green
    digs = {name: decode_digit(mask, cell) for name, cell in CELLS.items()}

    def d(n):
        ch, on, _ = digs[n]
        if ch is not None:
            return ch
        return "0" if len(on) == 0 else "?"

    s = f"{d('D1')}{d('D2')}.{d('D3')}{d('D4')}"
    sign = "-" if gx > rx else "+"
    if debug:
        for n in CELLS:
            ch, on, fr = digs[n]
            print(
                f"   {n}: {ch} on={sorted(on)} "
                + " ".join(f"{k}{fr[k]:.2f}" for k in "abcdefg")
            )
        print(f"   red={rx} green={gx}")
    return sign + s


def decode_file(path: str, debug: bool = False) -> str:
    return decode_array(np.asarray(Image.open(path).convert("RGB")), debug)


def run(frames_dir: str) -> None:
    """Decode every PNG crop in a directory."""
    files = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if not files:
        print(f"no PNG frames in {frames_dir}")
        return
    for f in files:
        name = os.path.basename(f)
        print(f"{name}: {decode_file(f, debug=name.startswith('v'))}")


def decode_frame(a) -> float | None:
    """Signed delta value for one raw frame, or None if unreadable."""
    red, green = lit_masks(a)
    mask = red | green
    rx = gx = 0
    for c in CELLS.values():
        rx += int(red[Y0:Y1, c[0] : c[1]].sum())
        gx += int(green[Y0:Y1, c[0] : c[1]].sum())

    def digit(cell):
        cx0, cx1 = cell
        w = cx1 - cx0
        h = Y1 - Y0
        on = set()
        for k, (fx, fy) in SEG.items():
            px = int(cx0 + fx * w)
            py = int(Y0 + fy * h)
            patch = mask[max(0, py - 4) : py + 5, max(0, px - 5) : px + 6]
            if patch.size and patch.mean() > 0.30:
                on.add(k)
        if len(on) == 0:
            return "0"  # blank -> leading zero
        return PAT.get(frozenset(on), "?")

    ds = [digit(CELLS[n]) for n in ("D1", "D2", "D3", "D4")]
    if "?" in ds:
        return None
    val = float(f"{ds[0]}{ds[1]}.{ds[2]}{ds[3]}")
    if gx > rx and (rx + gx) > 50:
        val = -val
    return val


def stream(fps: float) -> None:
    """Read rawvideo rgb24 frames of the delta region on stdin, print t,value."""
    frame_bytes = W * H * 3
    idx = 0
    out = []
    buf = sys.stdin.buffer
    while True:
        raw = buf.read(frame_bytes)
        if len(raw) < frame_bytes:
            break
        v = decode_frame(np.frombuffer(raw, np.uint8).reshape(H, W, 3))
        out.append(f"{idx / fps:.3f},{'' if v is None else f'{v:.2f}'}")
        idx += 1
    sys.stdout.write("\n".join(out) + "\n")
