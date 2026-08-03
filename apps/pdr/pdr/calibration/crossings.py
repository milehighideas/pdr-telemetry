"""Finish-line crossing detection from a *delta* series — the abandoned approach.

Pairs with `pdr.calibration.red`. Looks for the delta returning to ~0 after
having been meaningfully non-zero, debounced so one crossing isn't counted twice.
Superseded by the reset detection in `pdr.laps`, which works on the absolute
green timer and is far more reliable.
"""

from __future__ import annotations

import csv

import numpy as np


def load(path):
    T = []
    V = []
    for row in csv.reader(open(path)):
        if not row or row[0] == "":
            continue
        t = float(row[0])
        v = row[1]
        T.append(t)
        V.append(float(v) if v != "" else np.nan)
    return np.array(T), np.array(V)


def fill(V):
    """Forward then backward fill NaNs."""
    V = V.copy()
    last = np.nan
    for i in range(len(V)):
        if np.isnan(V[i]):
            V[i] = last
        else:
            last = V[i]
    for i in range(len(V) - 1, -1, -1):
        if np.isnan(V[i]):
            V[i] = V[i + 1] if i + 1 < len(V) else 0.0
        else:
            break
    return V


def crossings(T, V, fps=5, debounce=50.0):
    V = fill(V)
    n = len(V)
    win = int(1.6 * fps)
    res = []
    last = -1e9
    for i in range(1, n):
        if abs(V[i]) < 0.40:
            lo = max(0, i - win)
            pre = V[lo:i]
            if len(pre) and np.nanmax(np.abs(pre)) >= 0.85:
                # candidate reset; ensure this is the first low sample (edge)
                if abs(V[i - 1]) >= 0.40 or (
                    i - 1 >= 0 and abs(V[i - 1]) >= abs(V[i]) + 0.3
                ):
                    if T[i] - last > debounce:
                        # pre-reset gap = last stable value before the reset
                        j = i - 1
                        while j > 0 and abs(V[j]) < 0.40:
                            j -= 1
                        preval = (
                            np.median(V[max(0, j - int(0.8 * fps)) : j + 1])
                            if j >= 0
                            else np.nan
                        )
                        res.append((T[i], preval))
                        last = T[i]
    return res


def run(series_csv: str) -> None:
    T, V = load(series_csv)
    cr = crossings(T, V)
    print(f"file={series_csv}  n_crossings={len(cr)}")
    prev = None
    for k, (t, pre) in enumerate(cr):
        lap = f"{t - prev:7.2f}s" if prev is not None else "   --  "
        mm = ""
        if prev is not None:
            d = t - prev
            mm = f"({int(d // 60)}:{d % 60:05.2f})"
        print(f"  cross#{k:2d} @ {t:8.2f}s  lap={lap} {mm:>10}  preGap={pre:+.2f}")
        prev = t
