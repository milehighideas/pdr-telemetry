"""Human-readable lap tables."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .config import DEFAULT_FPS
from .laps import (
    FLYING,
    Lap,
    fill,
    fmt,
    laps_from_csv,
    load_series,
    median_filt,
    series_csvs,
    source_name,
)
from .config import MEDIAN_K

RULE = "=" * 68


def per_video(csv_dir: Path, fps: float = DEFAULT_FPS, title: str = "LAP TABLE") -> str:
    """Full per-video breakdown, then every flying lap ranked fastest first."""
    lines = [RULE, f"  {title} (by video)", RULE]
    flying: list[tuple[str, Lap]] = []

    for path in series_csvs(csv_dir):
        name = source_name(path)
        laps = laps_from_csv(path, fps)
        if not laps:
            times, values = load_series(path)
            note = "idle / no complete lap"
            if len(values):
                peak = float(np.max(median_filt(fill(values), MEDIAN_K)))
                if peak > 30:
                    note += f"  (1 partial lap reached {fmt(peak)}, not completed on-camera)"
            lines.append(f"\n{name}.mp4   — {note}")
            continue

        lines.append(f"\n{name}.mp4")
        for n, lap in enumerate(laps, 1):
            label = "FLYING" if lap.kind == FLYING else lap.kind.replace("_", " ")
            if lap.kind == FLYING:
                flying.append((name, lap))
            span = f"{fmt(max(0.0, lap.reset_time - lap.lap_time))}–{fmt(lap.reset_time)}"
            lines.append(
                f"   lap {n}: {fmt(lap.lap_time):>8}   [{label}]   footage ~{span}"
            )

    flying.sort(key=lambda r: r[1].lap_time)
    lines += ["", RULE, "  FLYING LAPS RANKED (fastest first)", RULE]
    for i, (name, lap) in enumerate(flying, 1):
        tag = "  <== FASTEST LAP OF THE DAY" if i == 1 else ""
        span = f"{fmt(max(0.0, lap.reset_time - lap.lap_time))}–{fmt(lap.reset_time)}"
        lines.append(f"  {i:2d}. {fmt(lap.lap_time):>8}   {name}.mp4  footage ~{span}{tag}")
    lines.append(f"\nTotal flying laps: {len(flying)}")
    return "\n".join(lines)


def summary(csv_dir: Path, fps: float = DEFAULT_FPS) -> str:
    """One line per video plus a global fastest-laps list. Useful while calibrating."""
    header = (
        f"{'file':16s} {'#laps':>5} {'firstG':>7} {'lastG':>7} "
        f"{'lastT':>7} {'maxG':>7}   lap_times"
    )
    lines = [header]
    everything: list[tuple[str, Lap]] = []

    for path in series_csvs(csv_dir):
        name = source_name(path)
        times, values = load_series(path)
        if len(times) == 0:
            lines.append(f"{name:16s} {0:5d} {'-':>7} {'-':>7} {'-':>7} {'-':>7}")
            continue
        smoothed = median_filt(fill(values), MEDIAN_K)
        laps = laps_from_csv(path, fps)
        everything += [(name, lap) for lap in laps]
        times_str = ", ".join(fmt(lap.lap_time) for lap in laps)
        lines.append(
            f"{name:16s} {len(laps):5d} {smoothed[0]:7.1f} {smoothed[-1]:7.1f} "
            f"{times[-1]:7.1f} {float(np.max(smoothed)):7.1f}   {times_str}"
        )

    everything.sort(key=lambda r: r[1].lap_time)
    lines.append("\n=== ALL laps sorted by time ===")
    for name, lap in everything[:15]:
        lines.append(
            f"  {fmt(lap.lap_time)}  ({lap.lap_time:6.2f}s)  "
            f"in {name} @ {lap.reset_time:.1f}s"
        )
    return "\n".join(lines)
