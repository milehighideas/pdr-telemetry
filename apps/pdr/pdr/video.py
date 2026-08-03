"""Drive ffmpeg to crop the HUD region and stream raw frames into the decoder."""

from __future__ import annotations

import csv
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from .config import CROP_H, CROP_W, CROP_X, CROP_Y, DEFAULT_FPS
from .decode import decode_frame


def _ffmpeg_cmd(video: Path, fps: float) -> list[str]:
    return [
        "ffmpeg", "-v", "error", "-i", str(video),
        "-vf", f"crop={CROP_W}:{CROP_H}:{CROP_X}:{CROP_Y},fps={fps}",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]


def decode_video(video: Path, fps: float = DEFAULT_FPS) -> list[tuple[float, float | None]]:
    """Decode a whole video to a list of (timestamp_seconds, lap_seconds_or_None)."""
    frame_bytes = CROP_W * CROP_H * 3
    series: list[tuple[float, float | None]] = []
    proc = subprocess.Popen(
        _ffmpeg_cmd(video, fps), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    try:
        idx = 0
        assert proc.stdout is not None
        while True:
            raw = proc.stdout.read(frame_bytes)
            if len(raw) < frame_bytes:
                break
            frame = np.frombuffer(raw, np.uint8).reshape(CROP_H, CROP_W, 3)
            series.append((idx / fps, decode_frame(frame)))
            idx += 1
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait()
    return series


def write_series(series, path: Path) -> None:
    """Write a decoded series as 't_sec,lap_seconds' CSV; gaps become empty cells."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        for t, v in series:
            w.writerow([f"{t:.3f}", "" if v is None else f"{v:.2f}"])


def _decode_one(args: tuple[Path, Path, float]) -> tuple[str, int]:
    video, out_dir, fps = args
    series = decode_video(video, fps)
    write_series(series, out_dir / f"green_{video.stem}.csv")
    return video.stem, len(series)


def decode_all(
    videos: list[Path], out_dir: Path, fps: float = DEFAULT_FPS, workers: int = 4
):
    """Decode many videos in parallel. Yields (stem, frame_count) as each finishes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(v, out_dir, fps) for v in videos]
    if workers <= 1:
        for job in jobs:
            yield _decode_one(job)
        return
    with ProcessPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(_decode_one, jobs)
