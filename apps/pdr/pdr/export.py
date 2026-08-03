"""CSV export of the full lap table."""

from __future__ import annotations

import csv
from pathlib import Path

from .config import DEFAULT_FPS
from .laps import FLYING, Lap, fmt, laps_from_csv, series_csvs, source_name

COLUMNS = [
    "video",
    "lap_number",
    "lap_time",
    "lap_time_seconds",
    "type",
    "footage_start_mmss",
    "footage_end_mmss",
    "fastest_of_day",
]


def collect(csv_dir: Path, fps: float = DEFAULT_FPS) -> list[tuple[str, int, Lap]]:
    """Every lap across every decoded video, as (video_stem, lap_number, lap)."""
    rows: list[tuple[str, int, Lap]] = []
    for path in series_csvs(csv_dir):
        name = source_name(path)
        for n, lap in enumerate(laps_from_csv(path, fps), 1):
            rows.append((name, n, lap))
    return rows


def write_csv(csv_dir: Path, out_path: Path, fps: float = DEFAULT_FPS) -> tuple[int, Lap | None]:
    """Write the lap table. Returns (row_count, fastest_flying_lap)."""
    rows = collect(csv_dir, fps)
    flying = [r for r in rows if r[2].kind == FLYING]
    fastest = min(flying, key=lambda r: r[2].lap_time)[2] if flying else None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        for name, n, lap in rows:
            w.writerow([
                f"{name}.mp4",
                n,
                fmt(lap.lap_time),
                round(lap.lap_time, 2),
                lap.kind,
                fmt(lap.footage_start),
                fmt(lap.footage_end),
                "YES" if lap is fastest else "",
            ])
    return len(rows), fastest
