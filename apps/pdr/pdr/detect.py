"""Work out which overlay a video was recorded with, and where it changes.

The HUD is drawn in near-white strokes that never move, while the scene behind it
changes between frames. So the pixels that stay near-white across a few frames
spread over several seconds are almost exactly the HUD strokes — bright sky or a
white car will blow out one frame but not hold the same pixels across all of them.

The window is deliberately short. An earlier version intersected across the *whole*
video, which silently assumed one overlay per recording: when the driver changed
overlay mid-recording the intersection collapsed and the video was reported as
unidentifiable. PDR_9983 does exactly that 14 seconds in.

Anchors and thresholds were measured against known footage, not guessed. On the
`tach_left` anchor, the sport/track layout scores 0.096-0.490 while every other
mode scores exactly 0.000; on `gbar` the alternate layout scores 0.015-0.057 and
everything else exactly 0.000; lap timing shows 0.067-0.079 green coverage in the
timer region versus exactly 0.000 when off.
"""

from __future__ import annotations

import functools
import subprocess
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import numpy as np

from .decode import green_mask
from .overlays import TRACK, Region

FRAME_W, FRAME_H = 1920, 1080

# A pixel counts as HUD-white when its dimmest channel clears this.
WHITE = 170

# --- Reference masks -------------------------------------------------------
# Coverage of a single anchor region is not safe to threshold: a sunlit road can
# hold a region near-white for seconds at a time. Measured at one such false
# positive, the g-dial anchor read 0.53 — twenty times its true value — purely
# from road surface. So classification matches the *shape* of the HUD instead,
# scoring how much of each overlay's distinctive stroke pattern is lit. Observed
# separation is wide: the correct overlay scores 0.96-1.00 and the other 0.07-0.11.
MASKS = files("pdr.data") / "refmasks.npz"

# A layout must light this fraction of its own strokes to be considered present,
# and beat the alternative by this factor.
MATCH = 0.50
MARGIN = 2.0
# Below this, no HUD is judged present at all.
BARE = 0.30
# Green coverage of the timer region. Measured: 0.067-0.079 on, exactly 0.000 off.
TIMING_ON = 0.010

# Frames per classification window, and the seconds they span. Short enough to
# localise a change, long enough that moving scenery cannot hold the anchors.
WINDOW_FRAMES = 3
WINDOW_SPAN = 6.0


@dataclass(frozen=True)
class Segment:
    """A contiguous run of one overlay within a video."""

    overlay: str
    lap_timing: bool
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def label(self) -> str:
        return f"{self.overlay}-with-timing" if self.lap_timing else self.overlay

    def __str__(self) -> str:
        return f"{self.label} [{self.start / 60:.2f}-{self.end / 60:.2f}m]"


@dataclass(frozen=True)
class Detection:
    video: str
    segments: list[Segment] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def mixed(self) -> bool:
        return len(self.segments) > 1

    @property
    def overlay(self) -> str:
        """The dominant overlay by duration, for a one-line summary."""
        if not self.segments:
            return "unknown"
        return max(self.segments, key=lambda s: s.duration).overlay


def duration(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def grab(video: Path, t: float) -> np.ndarray | None:
    """Decode a single full-resolution frame at time t."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", str(video),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
    ).stdout
    if len(raw) != FRAME_W * FRAME_H * 3:
        return None
    return np.frombuffer(raw, np.uint8).reshape(FRAME_H, FRAME_W, 3)


def crop(frame: np.ndarray, r: Region) -> np.ndarray:
    return frame[r.y : r.y + r.h, r.x : r.x + r.w]


def persistent_white(frames: list[np.ndarray], r: Region) -> float:
    """Fraction of a region that is near-white in every frame of the window."""
    held = None
    for f in frames:
        white = crop(f, r).min(axis=2) > WHITE
        held = white if held is None else (held & white)
    return float(held.mean()) if held is not None else 0.0


def window_frames(video: Path, t: float, span: float = WINDOW_SPAN) -> list[np.ndarray]:
    """Frames spread over a short window centred on t."""
    offsets = np.linspace(-span / 2, span / 2, WINDOW_FRAMES)
    out = []
    for o in offsets:
        f = grab(video, t + float(o))
        if f is not None:
            out.append(f)
    return out


@functools.lru_cache(maxsize=1)
def reference_masks() -> dict[str, np.ndarray]:
    """Distinctive stroke pattern of each layout, as boolean full-frame masks."""
    with np.load(MASKS) as z:
        shape = tuple(z["shape"])
        n = int(np.prod(shape))
        return {
            "sport": np.unpackbits(z["sport"])[:n].astype(bool).reshape(shape),
            "alt": np.unpackbits(z["alt"])[:n].astype(bool).reshape(shape),
        }


def held_white(frames: list[np.ndarray]) -> np.ndarray:
    """Full-frame mask of pixels near-white in every frame of the window."""
    held = None
    for f in frames:
        white = f.min(axis=2) > WHITE
        held = white if held is None else (held & white)
    return held


def classify(frames: list[np.ndarray]) -> tuple[str, bool, dict[str, float]]:
    """Classify one window of frames into (overlay, lap_timing, scores)."""
    if not frames:
        return "unknown", False, {}
    refs = reference_masks()
    held = held_white(frames)
    sport = float((held & refs["sport"]).sum() / refs["sport"].sum())
    alt = float((held & refs["alt"]).sum() / refs["alt"].sum())

    timer_region = TRACK.get("lap_timer", lap_timing=True).region
    green = float(np.mean([green_mask(crop(f, timer_region)).mean() for f in frames]))
    timing = green > TIMING_ON
    scores = {"sport": sport, "alt": alt, "green_timer": green}

    if max(sport, alt) < BARE:
        return "none", False, scores
    if sport >= MATCH and sport > alt * MARGIN:
        return ("track" if timing else "sport"), timing, scores
    if alt >= MATCH and alt > sport * MARGIN:
        return "timing", timing, scores
    return "unknown", timing, scores


def classify_at(video: Path, t: float) -> tuple[str, bool]:
    overlay, timing, _ = classify(window_frames(video, t))
    return overlay, timing


def refine_boundary(video: Path, lo: float, hi: float, before: tuple[str, bool],
                    precision: float = 1.0) -> float:
    """Bisect for the moment the overlay changes, to within `precision` seconds."""
    while hi - lo > precision:
        mid = (lo + hi) / 2
        if classify_at(video, mid) == before:
            lo = mid
        else:
            hi = mid
    return hi


def segments(video: Path, step: float = 30.0, precision: float = 1.0) -> list[Segment]:
    """Scan a video and return its overlay runs, with refined boundaries."""
    total = duration(video)
    if total <= 0:
        return []
    marks: list[tuple[float, tuple[str, bool]]] = []
    t = min(2.0, total / 2)
    while t < total - 1:
        marks.append((t, classify_at(video, t)))
        t += step
    if not marks:
        return []
    marks = despeckle(marks)

    runs: list[Segment] = []
    kind = marks[0][1]
    start = 0.0
    for (prev_t, _), (this_t, this_kind) in zip(marks, marks[1:]):
        if this_kind == kind:
            continue
        boundary = refine_boundary(video, prev_t, this_t, kind, precision)
        runs.append(Segment(kind[0], kind[1], start, boundary))
        start, kind = boundary, this_kind
    runs.append(Segment(kind[0], kind[1], start, total))
    return runs


def despeckle(
    marks: list[tuple[float, tuple[str, bool]]],
) -> list[tuple[float, tuple[str, bool]]]:
    """Drop lone dissenting samples between two agreeing neighbours.

    A real overlay change persists; a single odd sample is a windowed misread —
    a passing white vehicle, a tunnel mouth, a frame grabbed mid-transition. Left
    in, each one would manufacture a spurious two-second segment and an extra
    output file.
    """
    if len(marks) < 3:
        return marks
    out = list(marks)
    for i in range(1, len(marks) - 1):
        before, here, after = marks[i - 1][1], marks[i][1], marks[i + 1][1]
        if here != before and before == after:
            out[i] = (marks[i][0], before)
    return out


def detect(video: Path, step: float = 30.0, precision: float = 1.0) -> Detection:
    segs = segments(video, step, precision)
    _, _, scores = classify(window_frames(video, min(2.0, duration(video) / 2)))
    return Detection(video.name, segs, scores)
