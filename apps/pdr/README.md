# pdr

Reads the telemetry stream embedded in Cadillac / Chevrolet Performance Data
Recorder footage, and decodes the on-screen overlay where that is useful.

See the [repository README](../../README.md) for installation and general use.
This file covers how the pieces work.

## The embedded telemetry stream

Each recording holds three streams: video, audio, and a data track with fourcc
`marl` under handler `ctbx`. The data track carries the car's instrumentation.

Records are 16 bytes, big-endian:

```bash
0..1    0xe000   constant marker
2..3    channel  parameter id
4..7    value    signed 32-bit
8..11   unused in all footage examined
12..15  ticks    100 ns units, wrapping every 2**32 ticks = 429.4967296 s
```

Two things make this awkward to read:

**Sample boundaries matter.** `ffmpeg -f data` concatenates packet payloads with
no separators, so any framing that is not a whole number of bytes per packet
drifts and the record structure appears to dissolve. `mp4.py` walks the
container's own sample table (`stsd`/`stts`/`stsc`/`stsz`/`stco`) instead, which
gives exact per-sample payloads and real presentation timestamps.

**The tick field wraps.** It laps every 429 s — six times in a 43-minute file —
and records are grouped by channel within a sample rather than sorted by time, so
unwrapping it as a running clock finds tens of thousands of rollovers that are not
there. Each container sample carries its own presentation time, so the tick only
has to resolve position *within* one ~1.8 s sample, which it does unambiguously.

## Channels

`CHANNELS.csv` is the index: name, confidence, unit, scale, observed rate and
range for every channel, plus the evidence behind each identification.

| Confidence | Meaning |
|---|---|
| `confirmed` | validated against independent ground truth — an on-screen readout, GPS geometry, or a physical invariant such as gravity at rest |
| `probable` | strong inference from behaviour, not independently validated |
| `unknown` | characterised only by its statistics — still exported, under `ch_<hex>` |

Encodings worth knowing:

- wheel speeds are **1/32 km/h per bit**, vehicle speed **1/64 km/h** — standard
  GM CAN scalings
- the accelerometer is about **1/3276.8 g per bit** (±10 g full scale)
- fluid temperatures are **°C with a −40 offset**; the tyre temperature channels
  are *not* on that offset and remain unresolved
- `gear` is 1–6 with **13 = Neutral** and **14 = Reverse**
- `lap` is written **only when it increments**, so intervals between its marks are
  lap times directly

Categorical channels (`gear`, `lap`, `gps_fix`, `gps_satellites`) are held rather
than interpolated when resampling — interpolating them invents values that never
occurred, such as a gear of 2.5 mid-shift.

## On-screen decoding

`overlays/` describes where each field is drawn per overlay mode, and `profile.py`
pairs an overlay with the lap-timing state, since the two are independent settings
on the car. `timing.py` is registered but uncalibrated: it raises `NotCalibrated`
rather than returning coordinates that would decode the wrong pixels.

`detect.py` identifies a recording's overlay from the pixels that stay near-white
across a short window — static HUD strokes, as against a scene that changes. It
matches the *shape* of each layout's stroke pattern against reference masks rather
than thresholding a region's coverage, because sunlit road can hold a region
near-white for seconds and fake a match.

The window is deliberately short. Intersecting across a whole recording assumes
one overlay per file, and silently fails when the driver switches mode mid-drive.

All of this is calibrated for 1920x1080. `calibration/` holds the tools for
redoing it against other output.

## Legacy lap timing

`decode.py`, `laps.py`, `report.py` and `export.py` recover lap times by decoding
the green 7-segment timer burned into track-mode footage: crop the region, mask
green-lit pixels, sample seven slant-aware segment points per digit, then call a
lap at each timer reset, taking the lap time from the frozen plateau the HUD holds
before restarting.

It works, but the `lap` channel in the telemetry is better on every axis —
accurate to the recorder's own clock, no threshold tuning, and it does not require
the overlay to be present at all.
