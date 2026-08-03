# pdr

Extract telemetry from Cadillac / Chevrolet **Performance Data Recorder** footage.

Every PDR recording carries a third stream alongside video and audio — fourcc
`marl`, handler `ctbx` — holding the car's own instrumentation at up to ~80 Hz:
GPS, altitude, per-wheel speed, three-axis acceleration, engine rpm, throttle,
brake, gear, tyre pressures and temperatures, fluid temperatures, and the lap
counter. Nothing that plays these files will show it to you, and `ffmpeg`'s
default stream selection silently discards it.

This tool reads that stream and writes it out as CSV.

It also contains an older path that reads the numbers off the *on-screen* overlay
by decoding the burned-in 7-segment lap timer. That is kept for reference, but the
embedded telemetry supersedes it: the telemetry is more accurate, far faster, and
present even in recordings made with no overlay at all.

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- `ffmpeg` and `ffprobe` on `PATH`

## Install

```sh
cd apps/pdr
uv venv && uv pip install -e .
```

## Use

Put your `.mp4` files anywhere — `footage/` at the repo root is gitignored and is
a convenient place for them.

```sh
mkdir -p footage/my-session
cp /Volumes/PDR/DCIM/100PDR02/*.mp4 footage/my-session/
```

### Export telemetry

```sh
uv run pdr telemetry footage/my-session
```

Writes one `<video>.telemetry.csv` per recording, plus a combined
`<folder>.telemetry.csv` when a folder holds more than one. Values are resampled
onto a common 10 Hz grid (`--rate` to change it), because channels log at wildly
different native rates.

For a lossless dump — one row per record, native rate, nothing interpolated:

```sh
uv run pdr telemetry footage/my-session --raw
```

That is much larger: expect roughly 40 MB per recording-minute.

### Identify the overlay

```sh
uv run pdr detect footage/my-session
```

Reports which on-screen overlay each recording uses and where it changes
mid-file, which happens whenever the driver switches display mode.

### Split by overlay

```sh
uv run pdr split footage/my-session -o footage/my-session-split
```

Cuts each recording so every output file has a single overlay. Output is written
as `.mov`, because MP4 cannot store a codec it has no name for and would drop the
telemetry stream.

### Channel reference

`apps/pdr/CHANNELS.csv` lists every channel with its name, unit, scale, observed
rate and range — and, for each, what the identification was actually checked
against and how confident it is. Regenerate it over your own footage with:

```sh
uv run pdr channels footage/my-session -o CHANNELS.csv
```

### Lap times from the overlay (legacy)

```sh
uv run pdr run footage/my-session -o lap_times.csv
```

Decodes the green on-screen lap timer frame by frame. Only works for recordings
made in track mode with lap timing enabled. Prefer the `lap` channel in the
telemetry export.

## Caveats

**Reverse-engineered.** Cosworth has never published this format. Everything here
was derived by measurement against known values. `CHANNELS.csv` records the
evidence and marks each channel `confirmed`, `probable` or `unknown` — check it
before trusting a channel for anything that matters.

**Roughly half the channels are still unidentified.** They are exported anyway,
under `ch_<hex>` names, with raw values intact.

**Overlay geometry is resolution-specific.** The on-screen decoding paths, and the
overlay detection, are calibrated against 1920x1080 output. Different resolutions
or HUD layouts need recalibration — see `pdr calibrate`. The telemetry export does
not depend on any of this and should work regardless.

**Telemetry contains full GPS.** A recording knows exactly where it was driven,
even when the picture shows nothing identifying. Bear that in mind before sharing
raw files. To remove it:

```sh
ffmpeg -i in.mp4 -map 0:v -map 0:a -c copy out.mp4
```

That is a lossless stream copy — video and audio are bit-identical — and typically
shrinks the file by 3–9%.

## Layout

```bash
apps/pdr/pdr/
├── telemetry.py     the marl stream: records, channels, scaling, CSV export
├── mp4.py           container sample-table reader (exact payloads + timestamps)
├── glossary.py      channel index generation, with per-channel evidence
├── detect.py        which overlay a recording uses, and where it changes
├── split.py         cut recordings at overlay boundaries
├── overlays/        on-screen field geometry per overlay mode
├── calibration/     tools for deriving that geometry
└── decode.py,
    laps.py, …       the legacy on-screen lap-timer pipeline
```

## Licence

MIT
