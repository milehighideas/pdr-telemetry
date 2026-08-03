"""Decode the PDR's embedded 'marl' telemetry track.

Every recording carries a third stream alongside video and audio holding the car's
own instrumentation — GPS, altitude, accelerometer, per-wheel speeds and more, at
about 11 Hz. It is present even in recordings made with no on-screen overlay, so
it is a strictly better source than reading the HUD.

Record format, 16 bytes big-endian:

    0..1   0xe000    constant marker
    2..3   channel   parameter id
    4..7   value     signed 32-bit
    8..11  (unused in all footage seen so far — always zero)
    12..15 ticks     100 ns units, wrapping every 2**32 ticks = 429.4967296 s

The wrap is why the raw tick field cannot be read as a running clock: a 43-minute
file laps it six times, and records are grouped by channel within a sample rather
than sorted by time, so naive unwrapping finds tens of thousands of phantom
rollovers. Each container sample carries its own presentation time, though, so
the tick field only has to resolve position *within* one ~1.8 s sample — which it
does unambiguously.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .mp4 import data_track, read_sample_bytes

RECORD = 16
MARKER = 0xE000
TICK_HZ = 10_000_000
WRAP = 2**32 / TICK_HZ  # 429.4967296 s

# Channels identified by decoding known footage and cross-checking against GPS
# geometry and the on-screen readouts. Names are descriptive, not official.
#
# Evidence for each scale:
#  - latitude/longitude at 1e-7 deg put the 2026-07-30 drive in Colorado, and the
#    resulting track follows the roads driven.
#  - altitude in cm gives 2346-3457 m, right for the passes on that route.
#  - the four wheel channels correlate 1.000 with GPS ground speed and, read as
#    1/32 km/h per bit (a standard GM CAN encoding), match the on-screen speed to
#    within 0.8 mph at every point checked.
#  - 0x1C correlates 1.000 at exactly half the wheel scale: 1/64 km/h per bit.
#  - the accelerometer triad reads a vector magnitude of 3233 units at standstill.
#    Taking that as 1 g gives 1/3276.8 g per bit — a +/-10 g full scale — which it
#    matches to 1.3%. Treat accelerometer values as approximate until a static
#    calibration on level ground pins it exactly.
KMH = 1 / 3.6
G_PER_BIT = 1 / 3276.8

# Wheel and tyre channels come in fours, but which corner each one is has not been
# established — they are numbered, not named, rather than guess at LF/RF/LR/RR.
CHANNELS: dict[int, tuple[str, str, float]] = {
    # --- GPS block, all at exactly 11 Hz ---
    0x26: ("latitude", "deg", 1e-7),
    0x27: ("longitude", "deg", 1e-7),
    0x28: ("altitude", "m", 0.01),
    0x29: ("gps_heading", "deg", 0.01),
    0x2B: ("gps_fix", "code", 1.0),
    0x2C: ("gps_satellites", "count", 1.0),
    # --- speed ---
    0x1C: ("speed", "m/s", KMH / 64),
    0x3B: ("wheel_1", "m/s", KMH / 32),
    0x3C: ("wheel_2", "m/s", KMH / 32),
    0x3D: ("wheel_3", "m/s", KMH / 32),
    0x3E: ("wheel_4", "m/s", KMH / 32),
    # --- motion ---
    0x23: ("accel_lat", "g", G_PER_BIT),
    0x24: ("accel_long", "g", G_PER_BIT),
    0x25: ("accel_vert", "g", G_PER_BIT),
    0x43: ("steering", "raw", 1.0),
    # --- driver inputs and engine ---
    0x06: ("engine_rpm", "rpm", 0.25),
    # Throttle saturates hard at 253: across all recordings that value occurs
    # 2824 times against ~600 each for 249-251, and never higher. That ceiling is
    # wide-open throttle, so 253 is full scale and the channel converts to percent.
    0x07: ("throttle", "%", 100 / 253),
    # Brake has no such ceiling — its top values tail off smoothly (122 once, 121
    # twice, 120 twice) rather than piling up, so there is no "fully pressed" value
    # to normalise against. It behaves like a pressure or force signal: correlation
    # with deceleration is +0.83 and the response is close to linear at roughly
    # 0.0067 g per count. Left in raw counts rather than invent a percentage.
    0x09: ("brake", "raw", 1.0),
    0x16: ("gear", "code", 1.0),
    # Lap counter. Logged only when it changes, and absent entirely from
    # recordings made with lap timing off — so the gaps between its marks are
    # the lap times, exactly.
    0x2D: ("lap", "count", 1.0),
    # --- tyres ---
    0x0A: ("tyre_pressure_1", "psi", 0.5),
    0x0B: ("tyre_pressure_2", "psi", 0.5),
    0x0C: ("tyre_pressure_3", "psi", 0.5),
    0x0D: ("tyre_pressure_4", "psi", 0.5),
    0x12: ("tyre_temp_1", "C", 1.0),
    0x13: ("tyre_temp_2", "C", 1.0),
    0x14: ("tyre_temp_3", "C", 1.0),
    0x15: ("tyre_temp_4", "C", 1.0),
    # --- fluid temperatures ---
    # Pinned against the driver's own gauge readings: oil ~270 F, coolant in the
    # 220s F, transmission ~150 F. A -40 C offset puts all three within a degree,
    # which also means the offset is right for fluids and the tyre channels above
    # must use some other encoding — not that -40 is wrong everywhere.
    0x05: ("oil_temp", "C", 1.0),
    0x02: ("coolant_temp", "C", 1.0),
    0x22: ("trans_temp", "C", 1.0),
}

# Gear codes. 1-6 are the forward gears; the two out-of-range codes were
# identified by what the car was doing when they appear — 13 shows up at a mean
# of 80 mph (coasting in neutral) and 14 only below 1 mph (reverse).
GEAR_NEUTRAL, GEAR_REVERSE = 13, 14
GEAR_CODES = {GEAR_NEUTRAL: "N", GEAR_REVERSE: "R"}


def gear_label(code: float) -> str:
    """Gear code as it would read on the dash: 'N', 'R' or '1'-'6'."""
    c = int(round(code))
    return GEAR_CODES.get(c, str(c))


# Categorical channels: hold the last value across a resample rather than
# interpolating between codes.
STEP_CHANNELS = frozenset({"gear", "lap", "gps_fix", "gps_satellites"})

# Channels whose raw value has a constant subtracted after scaling.
OFFSETS: dict[int, float] = {
    0x12: 40.0, 0x13: 40.0, 0x14: 40.0, 0x15: 40.0,
    0x05: 40.0, 0x02: 40.0, 0x22: 40.0,
}

# Preferred column order. Anything not listed still gets exported, as ch_xx.
CSV_ORDER = (
    "latitude", "longitude", "altitude", "gps_heading",
    "gps_fix", "gps_satellites",
    "speed", "wheel_1", "wheel_2", "wheel_3", "wheel_4",
    "accel_lat", "accel_long", "accel_vert", "steering",
    "engine_rpm", "throttle", "brake", "gear", "lap",
    "tyre_pressure_1", "tyre_pressure_2", "tyre_pressure_3", "tyre_pressure_4",
    "tyre_temp_1", "tyre_temp_2", "tyre_temp_3", "tyre_temp_4",
    "oil_temp", "coolant_temp", "trans_temp",
)


@dataclass
class Series:
    """One channel's samples, in video time order."""

    channel: int
    name: str
    unit: str
    time: np.ndarray
    value: np.ndarray

    def __len__(self) -> int:
        return len(self.time)

    def at(self, t: float) -> float:
        """Value at video time t, linearly interpolated."""
        return float(np.interp(t, self.time, self.value))


def channel_name(channel: int) -> str:
    return CHANNELS.get(channel, (f"ch_{channel:02x}", "raw", 1.0))[0]


def read_records(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (channel, raw_value, video_time) for every record in the file.

    Times come from each container sample's presentation time, refined by the
    record's own tick field and unwrapped against that sample so the 429 s
    rollover cannot alias.
    """
    track = data_track(path)
    if track is None:
        return np.empty(0, int), np.empty(0, np.int64), np.empty(0, float)

    channels: list[np.ndarray] = []
    values: list[np.ndarray] = []
    times: list[np.ndarray] = []

    for sample, blob in read_sample_bytes(path, track.samples):
        n = len(blob) // RECORD
        if n == 0:
            continue
        r = np.frombuffer(blob[: n * RECORD], np.uint8).reshape(n, RECORD)
        if not np.all(((r[:, 0].astype(int) << 8) | r[:, 1]) == MARKER):
            continue

        chan = (r[:, 2].astype(int) << 8) | r[:, 3]
        val = big_endian_signed(r[:, 4:8])
        ticks = big_endian_unsigned(r[:, 12:16])
        secs = ticks / TICK_HZ

        # Resolve which wrap this sample sits in, then keep records that land
        # near the sample's own timestamp.
        k = np.round((sample.time - secs) / WRAP)
        t = secs + k * WRAP

        channels.append(chan)
        values.append(val)
        times.append(t)

    if not channels:
        return np.empty(0, int), np.empty(0, np.int64), np.empty(0, float)
    return (
        np.concatenate(channels),
        np.concatenate(values),
        np.concatenate(times),
    )


def big_endian_signed(b: np.ndarray) -> np.ndarray:
    v = (
        (b[:, 0].astype(np.int64) << 24)
        | (b[:, 1].astype(np.int64) << 16)
        | (b[:, 2].astype(np.int64) << 8)
        | b[:, 3]
    )
    return np.where(v >= 2**31, v - 2**32, v)


def big_endian_unsigned(b: np.ndarray) -> np.ndarray:
    return (
        (b[:, 0].astype(np.int64) << 24)
        | (b[:, 1].astype(np.int64) << 16)
        | (b[:, 2].astype(np.int64) << 8)
        | b[:, 3]
    )


def read_series(path: Path) -> dict[str, Series]:
    """Decode a recording into one Series per channel, keyed by name."""
    chan, val, t = read_records(path)
    out: dict[str, Series] = {}
    for c in np.unique(chan):
        m = chan == c
        order = np.argsort(t[m], kind="stable")
        name, unit, scale = CHANNELS.get(int(c), (f"ch_{int(c):02x}", "raw", 1.0))
        out[name] = Series(
            channel=int(c),
            name=name,
            unit=unit,
            time=t[m][order],
            value=val[m][order].astype(float) * scale - OFFSETS.get(int(c), 0.0),
        )
    return out


def export_order(series: dict[str, Series]) -> list[str]:
    """Identified channels first in a fixed order, then everything else.

    Unidentified channels are still exported, under their ch_xx name: a channel
    whose meaning is unknown is not the same as a channel with no data, and
    dropping them would lose most of what the car records.
    """
    known = [k for k in CSV_ORDER if k in series]
    rest = sorted(k for k in series if k not in CSV_ORDER)
    return known + rest


def resample(series: dict[str, Series], rate: float,
             names: tuple[str, ...] | None = None) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Put every channel on one evenly spaced time grid.

    Channels arrive at wildly different rates — wheel speeds near 77 Hz, GPS at
    exactly 11 Hz, others once a second — so a tabular export has to resample.
    Values are interpolated; a channel is only carried if it has at least two
    samples to interpolate between.
    """
    usable = {k: s for k, s in series.items() if len(s) >= 2}
    wanted = [k for k in (names or export_order(usable)) if k in usable]
    if not wanted:
        return np.empty(0), {}

    # Span comes from the channels that actually carry the drive — the GPS and
    # speed group. Rare once-a-minute signals would otherwise clip the table to
    # nothing, and slow channels are simply held at their endpoints instead.
    core = [k for k in ("latitude", "speed", "accel_lat") if k in usable] or wanted
    start = max(usable[k].time[0] for k in core)
    stop = min(usable[k].time[-1] for k in core)
    if stop <= start:
        return np.empty(0), {}
    grid = np.arange(start, stop, 1.0 / rate)
    cols = {}
    for k in wanted:
        s = usable[k]
        if k in STEP_CHANNELS:
            # Gear, lap and fix codes are categorical. Interpolating them invents
            # values that never occurred — a gear of 2.5 between shifts — so hold
            # the last value instead.
            idx = np.searchsorted(s.time, grid, side="right") - 1
            cols[k] = s.value[np.clip(idx, 0, len(s.value) - 1)]
        else:
            cols[k] = np.interp(grid, s.time, s.value)
    return grid, cols


def write_csv(path: Path, out: Path, rate: float = 10.0,
              source_label: str | None = None, time_offset: float = 0.0) -> int:
    """Write one recording's telemetry as CSV. Returns the row count."""
    grid, cols = resample(read_series(path), rate)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        head = (["video"] if source_label else []) + ["time_s"] + list(cols)
        w.writerow(head)
        for i, t in enumerate(grid):
            row = ([source_label] if source_label else []) + [f"{t + time_offset:.3f}"]
            row += [f"{cols[k][i]:.6f}" for k in cols]
            w.writerow(row)
    return len(grid)


def append_csv(writer, path: Path, rate: float, label: str,
               time_offset: float, header_written: list[bool]) -> int:
    """Append one recording to an already-open combined CSV writer."""
    grid, cols = resample(read_series(path), rate)
    if not header_written[0]:
        writer.writerow(["video", "time_s", "elapsed_s"] + list(cols))
        header_written[0] = True
    for i, t in enumerate(grid):
        writer.writerow(
            [label, f"{t:.3f}", f"{t + time_offset:.3f}"]
            + [f"{cols[k][i]:.6f}" for k in cols]
        )
    return len(grid)


@dataclass(frozen=True)
class TelemetryLap:
    """One lap, taken straight from the recorder's own lap counter."""

    number: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def lap_times(path: Path) -> list[TelemetryLap]:
    """Laps from the embedded lap counter.

    The counter is written only when it increments, so consecutive marks bound a
    lap exactly — no video decoding, no threshold tuning, and accurate to the
    recorder's own clock rather than to a sampled frame.

    Every interval is returned, including the first. The first mark is the moment
    timing armed, so that interval is usually an out-lap, but not always — classify
    by duration rather than assuming it.
    """
    chan, val, t = read_records(path)
    m = chan == 0x2D
    if not m.any():
        return []
    order = np.argsort(t[m], kind="stable")
    marks = t[m][order]
    nums = val[m][order]
    return [
        TelemetryLap(int(nums[i + 1]) - 1, float(marks[i]), float(marks[i + 1]))
        for i in range(len(marks) - 1)
    ]


def write_raw_csv(path: Path, out: Path) -> int:
    """Write every record exactly as logged: one row per record, no resampling.

    The wide export puts all channels on a common grid, which means interpolating
    and losing resolution on the fast ones — wheel speeds log at ~77 Hz and the
    accelerometers at ~48 Hz, against a 10 Hz grid. This form is lossless: native
    rate, native value, nothing invented. It is correspondingly large.
    """
    chan, val, t = read_records(path)
    if len(chan) == 0:
        return 0
    order = np.argsort(t, kind="stable")
    chan, val, t = chan[order], val[order], t[order]

    meta = {c: CHANNELS.get(int(c), (f"ch_{int(c):02x}", "raw", 1.0))
            for c in np.unique(chan)}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time_s", "channel", "name", "unit", "raw", "value"])
        for i in range(len(chan)):
            c = int(chan[i])
            name, unit, scale = meta[c]
            v = val[i] * scale - OFFSETS.get(c, 0.0)
            w.writerow([f"{t[i]:.4f}", f"0x{c:02x}", name, unit, int(val[i]), f"{v:g}"])
    return len(chan)
