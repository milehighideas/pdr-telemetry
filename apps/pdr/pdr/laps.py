"""Turn a decoded timer series into laps.

The HUD counts up during a lap, freezes on the final time for ~2s as you cross the
line, then restarts near zero. A lap is therefore a sharp downward step, and the lap
time is the frozen plateau immediately before it — not the last sample, which is
already counting the next lap.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import (
    DEFAULT_FPS,
    FLYING_MAX,
    FLYING_MIN,
    FREEZE,
    LAP_DROP,
    LAP_LOOKBACK,
    LAP_PLATEAU,
    MEDIAN_K,
)

PIT_FRAGMENT = "pit_fragment"
FLYING = "flying"
IN_LAP = "in_lap_or_cooldown"


@dataclass(frozen=True)
class Lap:
    """One detected lap. Times are seconds within the source video."""

    reset_time: float
    lap_time: float

    @property
    def kind(self) -> str:
        return classify(self.lap_time)

    @property
    def footage_end(self) -> float:
        """When the lap actually ended, backing out the HUD's freeze hold."""
        return self.reset_time - FREEZE

    @property
    def footage_start(self) -> float:
        return max(0.0, self.footage_end - self.lap_time)


def classify(lap_time: float) -> str:
    if lap_time < FLYING_MIN:
        return PIT_FRAGMENT
    if lap_time > FLYING_MAX:
        return IN_LAP
    return FLYING


def fmt(seconds: float | None) -> str:
    """Format seconds as M:SS.hh."""
    if seconds is None:
        return ""
    m = int(seconds // 60)
    return f"{m}:{seconds - 60 * m:05.2f}"


def load_series(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read a decoder CSV. Undecoded frames come back as NaN."""
    times: list[float] = []
    values: list[float] = []
    with Path(path).open() as fh:
        for row in csv.reader(fh):
            if not row or row[0] == "":
                continue
            try:
                t = float(row[0])
            except ValueError:
                continue
            times.append(t)
            values.append(float(row[1]) if row[1] != "" else np.nan)
    return np.array(times), np.array(values)


def fill(values: np.ndarray) -> np.ndarray:
    """Forward-fill NaN gaps with the last good reading."""
    out = values.copy()
    last = 0.0
    for i in range(len(out)):
        if np.isnan(out[i]):
            out[i] = last
        else:
            last = out[i]
    return out


def median_filt(values: np.ndarray, k: int = 3) -> np.ndarray:
    """Median filter with a +/-k window, to kill single-frame misreads."""
    out = values.copy()
    for i in range(len(values)):
        lo = max(0, i - k)
        hi = min(len(values), i + k + 1)
        out[i] = np.median(values[lo:hi])
    return out


def find_laps(
    times: np.ndarray,
    values: np.ndarray,
    fps: float = DEFAULT_FPS,
    drop: float = LAP_DROP,
) -> list[Lap]:
    """Detect laps as sharp resets in a decoded timer series."""
    smoothed = median_filt(fill(values), MEDIAN_K)
    laps: list[Lap] = []
    for i in range(1, len(smoothed)):
        fell = smoothed[i - 1] - smoothed[i] > drop
        if not (fell and smoothed[i] < smoothed[i - 1] * 0.5):
            continue
        lo = max(0, i - int(LAP_LOOKBACK * fps))
        window = smoothed[lo:i]
        peak = np.max(window)
        plateau = window[window > peak - LAP_PLATEAU]
        laps.append(Lap(reset_time=float(times[i]), lap_time=float(np.median(plateau))))
    return laps


def laps_from_csv(path: Path, fps: float = DEFAULT_FPS) -> list[Lap]:
    times, values = load_series(path)
    if len(times) == 0:
        return []
    return find_laps(times, values, fps)


def series_csvs(csv_dir: Path) -> list[Path]:
    """All decoder CSVs in a directory, in stable filename order."""
    return sorted(Path(csv_dir).glob("green_*.csv"))


def source_name(csv_path: Path) -> str:
    """'green_PDR_9977.csv' -> 'PDR_9977'."""
    return csv_path.stem[len("green_") :]
