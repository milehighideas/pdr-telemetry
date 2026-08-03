"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import overlays, profile as profiles
from .config import DEFAULT_FPS
from .detect import detect
from .export import write_csv
from .laps import fmt, laps_from_csv
from .overlays import NotCalibrated
from .report import per_video, summary
from .video import decode_all


def _videos(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.glob("*.mp4"))


def cmd_decode(args) -> int:
    videos: list[Path] = []
    for p in args.source:
        videos += _videos(Path(p))
    if not videos:
        print("no .mp4 files found", file=sys.stderr)
        return 1
    print(f"decoding {len(videos)} video(s) at {args.fps} fps -> {args.out_dir}")
    for stem, frames in decode_all(videos, Path(args.out_dir), args.fps, args.workers):
        print(f"  {stem}  {frames} frames")
    return 0


def cmd_laps(args) -> int:
    laps = laps_from_csv(Path(args.series), args.fps)
    print(f"{Path(args.series).name}: {len(laps)} resets")
    prev = None
    for lap in laps:
        gap = f"{lap.reset_time - prev:6.1f}s since prev-reset" if prev else ""
        print(
            f"  reset@{lap.reset_time:7.1f}s   lap_time={fmt(lap.lap_time)} "
            f"({lap.lap_time:6.2f}s)   [{lap.kind}] {gap}"
        )
        prev = lap.reset_time
    return 0


def cmd_report(args) -> int:
    if args.summary:
        print(summary(Path(args.csv_dir), args.fps))
    else:
        print(per_video(Path(args.csv_dir), args.fps, args.title))
    return 0


def cmd_export(args) -> int:
    n, fastest = write_csv(Path(args.csv_dir), Path(args.out), args.fps)
    print(f"wrote {args.out}  rows: {n}")
    if fastest:
        print(f"fastest flying lap: {fmt(fastest.lap_time)} ({fastest.lap_time:.2f}s)")
    return 0


def cmd_run(args) -> int:
    """decode -> report -> export, end to end."""
    videos = _videos(Path(args.source))
    if not videos:
        print("no .mp4 files found", file=sys.stderr)
        return 1
    work = Path(args.work)
    csv_dir = work / "csv"
    print(f"decoding {len(videos)} video(s) at {args.fps} fps -> {csv_dir}")
    for stem, frames in decode_all(videos, csv_dir, args.fps, args.workers):
        print(f"  {stem}  {frames} frames")
    print()
    print(per_video(csv_dir, args.fps, args.title))
    if args.out:
        print()
        n, fastest = write_csv(csv_dir, Path(args.out), args.fps)
        print(f"wrote {args.out}  rows: {n}")
    return 0


def cmd_overlays(args) -> int:
    """List overlay modes, the profiles built on them, and what each can read."""
    for name in profiles.names():
        prof = profiles.get(name)
        print(f"{name}")
        print(f"  overlay      {prof.overlay.name} — {prof.overlay.description}")
        print(f"  lap timing   {'on' if prof.lap_timing else 'off'}")
        try:
            fields = prof.fields
        except NotCalibrated as exc:
            print(f"  fields       UNAVAILABLE: {exc}")
            print()
            continue
        if not fields:
            print("  fields       none — nothing is recoverable from the image")
        for f in fields:
            r = f.region
            unit = f" [{f.unit}]" if f.unit else ""
            print(
                f"    {f.name:<12} {r.w:>4}x{r.h:<4} @ ({r.x:>4},{r.y:>4})  "
                f"{f.reader}{unit}"
            )
        print()
    return 0


def cmd_detect(args) -> int:
    videos: list[Path] = []
    for p in args.source:
        videos += _videos(Path(p))
    if not videos:
        print("no .mp4 files found", file=sys.stderr)
        return 1
    mixed = 0
    for v in videos:
        d = detect(v, args.step, args.precision)
        segs = "  ".join(str(s) for s in d.segments) or "unknown"
        flag = "  <== MIXED" if d.mixed else ""
        print(f"{v.name:<18} {segs}{flag}")
        if args.scores:
            print("      " + "  ".join(f"{k}={s:.4f}" for k, s in d.scores.items()))
        mixed += d.mixed
    if mixed:
        print(
            f"\n{mixed} video(s) change overlay mid-recording. "
            f"Use 'pdr split' to cut them into one file per overlay.",
            file=sys.stderr,
        )
    return 0


def cmd_split(args) -> int:
    from .split import split_video

    videos: list[Path] = []
    for p in args.source:
        videos += _videos(Path(p))
    if not videos:
        print("no .mp4 files found", file=sys.stderr)
        return 1
    out_dir = Path(args.out_dir)
    written = skipped = 0
    for v in videos:
        parts = split_video(
            v, out_dir, args.min_seconds, args.reencode,
            args.step, args.precision, args.dry_run,
        )
        if len(parts) <= 1 and not args.all:
            print(f"{v.name:<18} single overlay — left alone")
            continue
        for p in parts:
            if p.skipped:
                print(f"{v.name:<18} -> skip {p.path.name}  ({p.reason})")
                skipped += 1
            else:
                print(f"{v.name:<18} -> {p.path.name}  [{p.segment}]")
                written += 1
    verb = "would write" if args.dry_run else "wrote"
    print(f"\n{verb} {written} file(s); skipped {skipped} sub-{args.min_seconds}s run(s)")
    if not args.reencode and written:
        print(
            "Cuts are stream copies, so boundaries snap to the nearest keyframe "
            "(usually well under a second). Use --reencode for exact cuts.",
            file=sys.stderr,
        )
    return 0


def cmd_telemetry(args) -> int:
    """Export the embedded telemetry track as CSV, per file and per folder."""
    import csv as csvmod

    from .telemetry import append_csv, write_csv, write_raw_csv

    groups: dict[Path, list[Path]] = {}
    for p in args.source:
        for v in _videos(Path(p)):
            groups.setdefault(v.parent, []).append(v)
    if not groups:
        print("no .mp4 files found", file=sys.stderr)
        return 1

    total = 0
    for folder, videos in sorted(groups.items()):
        out_dir = Path(args.out_dir) if args.out_dir else folder
        for v in sorted(videos):
            if args.raw:
                dest = out_dir / f"{v.stem}.telemetry-raw.csv"
                rows = write_raw_csv(v, dest)
            else:
                dest = out_dir / f"{v.stem}.telemetry.csv"
                rows = write_csv(v, dest, args.rate)
            total += rows
            print(f"{v.name:<18} -> {dest.name:<34} {rows:>8,} rows")
            if rows == 0:
                print(f"    no telemetry track in {v.name}", file=sys.stderr)

        if len(videos) > 1 and not args.raw:
            combined = out_dir / f"{folder.name}.telemetry.csv"
            combined.parent.mkdir(parents=True, exist_ok=True)
            header = [False]
            offset = 0.0
            with combined.open("w", newline="") as fh:
                w = csvmod.writer(fh)
                for v in sorted(videos):
                    n = append_csv(w, v, args.rate, v.stem, offset, header)
                    offset += n / args.rate
            print(f"{'':<18} -> {combined.name:<34} combined ({len(videos)} files)")
    unit = "records (native rate)" if args.raw else f"rows at {args.rate} Hz"
    print(f"\n{total:,} {unit}")
    return 0


def cmd_channels(args) -> int:
    """Write the channel index: every channel, what it is, and how sure that is."""
    from .glossary import write_glossary

    videos: list[Path] = []
    for p in args.source:
        videos += _videos(Path(p))
    if not videos and args.source:
        print("no .mp4 files found", file=sys.stderr)
        return 1
    n = write_glossary(videos, Path(args.out))
    print(f"wrote {args.out}: {n} channels across {len(videos)} recording(s)")
    return 0


def cmd_calibrate(args) -> int:
    from .calibration import bands, bands2, crossings, gbands, gdecode, profile, red

    tools = {
        "profile": lambda: profile.run(args.target),
        "bands": lambda: bands.run(args.target),
        "bands2": lambda: bands2.run(args.target),
        "gbands": lambda: gbands.run(args.target),
        "verify": lambda: gdecode.run(args.target),
        "red-decode": lambda: red.run(args.target),
        "crossings": lambda: crossings.run(args.target),
    }
    result = tools[args.tool]()
    return result if isinstance(result, int) else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pdr",
        description="Extract lap times from Cadillac PDR video by decoding the "
        "on-screen green lap timer.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add_fps(sp):
        sp.add_argument(
            "--fps", type=float, default=DEFAULT_FPS,
            help=f"decode sampling rate (default {DEFAULT_FPS})",
        )

    d = sub.add_parser("decode", help="decode videos to timer-series CSVs")
    d.add_argument("source", nargs="+", help="video files or a directory of .mp4")
    d.add_argument("-o", "--out-dir", default="work/csv")
    d.add_argument("-j", "--workers", type=int, default=4)
    add_fps(d)
    d.set_defaults(func=cmd_decode)

    l = sub.add_parser("laps", help="show laps found in one timer-series CSV")
    l.add_argument("series")
    add_fps(l)
    l.set_defaults(func=cmd_laps)

    r = sub.add_parser("report", help="print a lap table for a directory of CSVs")
    r.add_argument("csv_dir")
    r.add_argument("--title", default="LAP TABLE")
    r.add_argument("--summary", action="store_true", help="compact one-line-per-video form")
    add_fps(r)
    r.set_defaults(func=cmd_report)

    e = sub.add_parser("export", help="write the lap table as CSV")
    e.add_argument("csv_dir")
    e.add_argument("-o", "--out", required=True)
    add_fps(e)
    e.set_defaults(func=cmd_export)

    x = sub.add_parser("run", help="decode, report and export in one pass")
    x.add_argument("source", help="video file or directory of .mp4")
    x.add_argument("--work", default="work")
    x.add_argument("-o", "--out", help="write the lap table CSV here")
    x.add_argument("--title", default="LAP TABLE")
    x.add_argument("-j", "--workers", type=int, default=4)
    add_fps(x)
    x.set_defaults(func=cmd_run)

    o = sub.add_parser("overlays", help="list overlay modes and their fields")
    o.set_defaults(func=cmd_overlays)

    def add_scan(sp):
        sp.add_argument("--step", type=float, default=30.0,
                        help="seconds between coarse scan samples (default 30)")
        sp.add_argument("--precision", type=float, default=1.0,
                        help="seconds of accuracy when refining a boundary (default 1)")

    t = sub.add_parser("detect", help="identify overlays in a video, and where they change")
    t.add_argument("source", nargs="+", help="video files or a directory of .mp4")
    t.add_argument("--scores", action="store_true", help="show raw anchor scores")
    add_scan(t)
    t.set_defaults(func=cmd_detect)

    s = sub.add_parser("split", help="cut recordings so each output has one overlay")
    s.add_argument("source", nargs="+", help="video files or a directory of .mp4")
    s.add_argument("-o", "--out-dir", required=True)
    s.add_argument("--min-seconds", type=float, default=2.0,
                   help="discard runs shorter than this (default 2)")
    s.add_argument("--reencode", action="store_true",
                   help="exact cuts by re-encoding, instead of a fast stream copy")
    s.add_argument("--all", action="store_true",
                   help="also copy videos that contain only one overlay")
    s.add_argument("-n", "--dry-run", action="store_true")
    add_scan(s)
    s.set_defaults(func=cmd_split)

    m = sub.add_parser("telemetry", help="export the embedded telemetry track as CSV")
    m.add_argument("source", nargs="+", help="video files or a directory of .mp4")
    m.add_argument("-o", "--out-dir",
                   help="where to write (default: alongside each video)")
    m.add_argument("--rate", type=float, default=10.0,
                   help="output sample rate in Hz (default 10)")
    m.add_argument("--raw", action="store_true",
                   help="one row per record at native rate, no resampling "
                        "(lossless, but far larger)")
    m.set_defaults(func=cmd_telemetry)

    ch = sub.add_parser("channels",
                        help="write a channel index/glossary CSV")
    ch.add_argument("source", nargs="*",
                    help="video files or directories to survey. Omit to emit the "
                         "reference table with no observed statistics.")
    ch.add_argument("-o", "--out", default="CHANNELS.csv")
    ch.set_defaults(func=cmd_channels)

    c = sub.add_parser("calibrate", help="derive/verify decoder geometry")
    c.add_argument(
        "tool",
        choices=["profile", "bands", "bands2", "gbands", "verify", "red-decode", "crossings"],
    )
    c.add_argument("target", help="directory of PNG frame crops (or a CSV for crossings)")
    c.set_defaults(func=cmd_calibrate)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
