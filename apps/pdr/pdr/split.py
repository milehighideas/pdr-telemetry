"""Cut recordings at overlay boundaries, so each output file has one overlay.

A single recording can contain more than one overlay — the driver changes the PDR
display mid-drive. PDR_9983 runs the sport layout for 14 seconds and then switches
for the remaining 43 minutes. Anything that reads telemetry needs one overlay per
file, so this splits them.

Cuts are stream copies by default: no re-encode, so a 43-minute 4 GB source splits
in seconds and the video is bit-identical to the source. The cost is that a copy
cut can only land on a keyframe, so a boundary may be off by up to one GOP —
typically well under a second, but see `reencode=True` for an exact cut.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .detect import Segment, segments

# fourcc of the PDR's telemetry data track: GPS, accelerometer, wheel speeds and
# more, at ~11 Hz. ffmpeg has no decoder for it and mp4 refuses to store a stream
# whose codec it cannot name, so a split that writes .mp4 silently loses it. The
# mov muxer will carry the stream through untouched — verified byte-identical —
# so any source carrying telemetry is written as .mov instead.
DATA_TAG = "marl"


def has_telemetry(source: Path) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "d",
         "-show_entries", "stream=codec_tag_string", "-of", "csv=p=0", str(source)],
        capture_output=True, text=True,
    ).stdout
    return DATA_TAG in out


def container_suffix(source: Path) -> str:
    return ".mov" if has_telemetry(source) else source.suffix


@dataclass(frozen=True)
class Part:
    """One output file produced from a source segment."""

    path: Path
    segment: Segment
    skipped: bool = False
    reason: str = ""


def part_name(source: Path, index: int, segment: Segment, total: int) -> str:
    """PDR_9983.mp4 -> PDR_9983_01_sport.mov (unsuffixed when there is one part)."""
    suffix = container_suffix(source)
    if total == 1:
        return source.stem + suffix
    return f"{source.stem}_{index:02d}_{segment.label}{suffix}"


def cut(source: Path, segment: Segment, dest: Path, reencode: bool = False) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    codec = (
        ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-c:a", "aac", "-c:d", "copy"]
        if reencode
        else ["-c", "copy"]
    )
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-ss", f"{segment.start:.3f}", "-i", str(source),
        "-t", f"{segment.duration:.3f}",
        # -map 0 keeps every stream. Without it ffmpeg's default selection takes
        # one stream per type and silently discards the PDR's 'marl' data track —
        # the embedded GPS and vehicle telemetry, which is the most valuable
        # thing in the file. -copy_unknown allows through a stream ffmpeg has no
        # decoder for; the mov container (chosen in container_suffix) is what
        # actually accepts it, since mp4 will not store an unnamed codec.
        "-map", "0", "-copy_unknown",
        *codec, "-avoid_negative_ts", "make_zero", str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {source.name}: {result.stderr.strip()}")


def split_video(
    source: Path,
    out_dir: Path,
    min_seconds: float = 2.0,
    reencode: bool = False,
    step: float = 30.0,
    precision: float = 1.0,
    dry_run: bool = False,
) -> list[Part]:
    """Split one recording into one file per overlay run.

    Segments shorter than `min_seconds` are skipped rather than written — they are
    almost always the moment of the mode change itself, not real footage.
    """
    segs = segments(source, step, precision)
    if not segs:
        return []
    parts: list[Part] = []
    for i, seg in enumerate(segs, 1):
        dest = out_dir / part_name(source, i, seg, len(segs))
        if seg.duration < min_seconds:
            parts.append(Part(dest, seg, skipped=True,
                              reason=f"only {seg.duration:.1f}s"))
            continue
        if not dry_run:
            cut(source, seg, dest, reencode)
        parts.append(Part(dest, seg))
    return parts
