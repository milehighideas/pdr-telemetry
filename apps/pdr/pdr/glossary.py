"""A channel index: what each telemetry channel is, and how well that is known.

The point of this file is to keep the *evidence* next to the claim. A channel map
built by pattern-matching is easy to over-trust — several entries here started as
confident guesses that measurement later overturned, so each row records what it
was checked against and how firmly.

Confidence levels:
  confirmed  validated against independent ground truth — the on-screen readout,
             GPS geometry, or a physical invariant such as gravity at rest
  probable   strong inference from behaviour, not independently validated
  unknown    characterised only by its statistics
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .telemetry import CHANNELS, OFFSETS, read_records

CONFIRMED, PROBABLE, UNKNOWN = "confirmed", "probable", "unknown"

# channel -> (confidence, evidence)
EVIDENCE: dict[int, tuple[str, str]] = {
    0x06: (CONFIRMED, "160 sharp drops while accelerating, before/after ratios "
                      "cluster at 1.20-1.25 (gearbox steps); reads 0 at standstill"),
    0x07: (CONFIRMED, "goes to 0 the instant the driver lifts and stays there "
                      "through every braking zone; correlates +0.75 with "
                      "longitudinal accel derived independently from wheel speed. "
                      "Saturates at 253 (2824 occurrences vs ~600 each at 249-251, "
                      "never higher), so 253 is full scale and this is a percentage"),
    0x09: (CONFIRMED, "exactly 0 while accelerating or coasting, rising as "
                      "deceleration builds and decaying on release; correlates "
                      "-0.78 with longitudinal accel and +0.83 with deceleration "
                      "while braking. NOT a percentage: the top of its range tails "
                      "off smoothly rather than piling up, so there is no "
                      "fully-pressed ceiling. Pressure- or force-like, roughly "
                      "linear at ~0.0067 g per count"),
    0x0A: (CONFIRMED, "rises several psi across a track session and sits several psi "
                      "lower than on road drives, matching pressures being bled "
                      "down for track use"),
    0x0B: (CONFIRMED, "as 0x0a"),
    0x0C: (CONFIRMED, "as 0x0a"),
    0x0D: (CONFIRMED, "as 0x0a"),
    0x12: (PROBABLE, "climbs steeply over consecutive hot laps and stays flat on road "
                     "drives, so the identification is solid. The -40 offset is NOT: "
                     "it yields near-freezing values in summer footage. The peak is "
                     "right for track use, so the scale is likely fine and the "
                     "offset is not"),
    0x13: (PROBABLE, "as 0x12"),
    0x14: (PROBABLE, "as 0x12"),
    0x15: (PROBABLE, "as 0x12"),
    0x16: (CONFIRMED, "exact match against the on-screen gear readout at every point "
                      "checked; mean speed rises monotonically across codes 1-6; "
                      "13 appears at high speed (neutral, coasting) and 14 only "
                      "below walking pace (reverse)"),
    0x1A: (PROBABLE, "correlates -0.936 with lateral accel; appears to be 0x43 "
                     "offset-encoded by +32544 with inverted sign"),
    0x1C: (CONFIRMED, "matches the on-screen speed readout to +/-0.5 mph; exactly half "
                      "the wheel-speed scale, i.e. 1/64 km/h per bit"),
    0x23: (CONFIRMED, "orthogonal to longitudinal (corr -0.03 with d(speed)/dt); "
                      "steering correlates +0.965 with it"),
    0x24: (CONFIRMED, "correlates +0.889 with d(speed)/dt from wheel speed - this "
                      "is the LONGITUDINAL axis, not lateral as first assumed"),
    0x25: (CONFIRMED, "holds the gravity vector at standstill; triad magnitude at "
                      "rest is 3233 units, giving 1/3276.8 g per bit to 1.3%"),
    0x26: (CONFIRMED, "decodes to coordinates that fall on the roads actually "
                      "driven, and closes into a circuit on track footage"),
    0x27: (CONFIRMED, "as 0x26"),
    0x28: (CONFIRMED, "tracks terrain elevation over a drive and agrees with known "
                      "ground height along the route"),
    0x29: (CONFIRMED, "median error 0.26 deg against GPS-derived bearing; 99.4% of "
                      "moving samples within 5 deg"),
    0x2B: (PROBABLE, "sits in the GPS block; 1-4 in a single file but 1-16 across "
                     "all 31, which fits a constellation bitmask better than a "
                     "plain fix-quality code - treat the name as unsettled"),
    0x2C: (PROBABLE, "sits in the GPS block, 3-17 across all recordings, tracking "
                     "sky visibility - consistent with satellite count"),
    0x2D: (CONFIRMED, "logged on change only; intervals between marks reproduce "
                      "independently OCR-derived lap times to within 0.005 s. The "
                      "only mismatches were spurious OCR 'pit fragments' that the "
                      "counter correctly never counted"),
    0x3B: (CONFIRMED, "correlates 1.000 with GPS ground speed; as 1/32 km/h per bit "
                      "(standard GM CAN) matches on-screen speed to 0.8 mph"),
    0x3C: (CONFIRMED, "as 0x3b"),
    0x3D: (CONFIRMED, "as 0x3b"),
    0x3E: (CONFIRMED, "as 0x3b"),
    0x05: (CONFIRMED, "matches a driver-reported oil gauge reading to within a degree "
                      "under a -40 C offset; hottest of the fluid group and the most "
                      "load-responsive (+42 raw over a track session)"),
    0x02: (PROBABLE, "matches a driver-reported coolant gauge reading under a -40 C "
                     "offset. 0x3f sits at near-identical magnitude and cannot be "
                     "ruled out; 0x02 was preferred because it varies with load "
                     "while 0x3f is near-constant"),
    0x22: (PROBABLE, "matches a driver-reported transmission gauge reading under a "
                     "-40 C offset. Caveat: it warms faster than a gearbox plausibly "
                     "would, so 0x17 remains an alternative"),
    0x43: (PROBABLE, "correlates +0.965 with lateral accel, so direction and "
                     "identity are solid; degrees-per-bit is NOT established"),
}

# Characterisation of channels that remain unidentified.
UNKNOWN_NOTES: dict[int, str] = {
    0x01: "correlates +0.61 with longitudinal accel - a pedal or torque signal",
    0x03: "correlates +0.70 with longitudinal accel - pedal or torque signal",
    0x04: "slow, 0-130, weak correlation with anything tested",
    0x08: "0-254, weak negative correlation with longitudinal accel",
    0x0E: "constant 1 - flag. One of four (0x0e-0x11), likely per-wheel TPMS status",
    0x0F: "constant 1 - see 0x0e",
    0x10: "constant 1 - see 0x0e",
    0x11: "constant 1 - see 0x0e",
    0x17: "temperature-shaped, 66-84 C if offset -40",
    0x18: "temperature-shaped, wide range",
    0x1B: "slowly increasing, ~1.04 million - odometer candidate, scale unknown",
    0x1D: "constant 0",
    0x1E: "constant 0",
    0x1F: "constant 0",
    0x20: "constant 0",
    0x21: "two values (1, 10) - a mode or state flag",
    0x2A: "constant 1 - likely a GPS validity flag (sits in the GPS block)",
    0x2E: "1 Hz block member (0x2e-0x39); these look like session or trip "
          "accumulators rather than live sensor values",
    0x3A: "reaches 2147483647 (INT32_MAX) - a saturation or invalid sentinel",
    0x3F: "temperature-shaped and close to coolant in magnitude (~74-121 C at "
          "offset -40), but far more tightly regulated - flat to sd 0.59 on track "
          "and dead constant in some files. A second coolant loop, or a setpoint "
          "rather than a measurement",
    0x40: "narrow band 65-86, steps frequently",
    0x41: "temperature-shaped, 62-67 C if offset -40",
    0x42: "temperature-shaped, 64-75 C if offset -40, ~10 Hz",
}
for _c in range(0x2E, 0x3A):
    UNKNOWN_NOTES.setdefault(_c, UNKNOWN_NOTES[0x2E])


@dataclass
class ChannelStat:
    channel: int
    samples: int
    rate: float
    raw_min: float
    raw_max: float
    files: int


def gather(paths: list[Path]) -> dict[int, ChannelStat]:
    """Aggregate per-channel statistics across many recordings."""
    acc: dict[int, list] = defaultdict(lambda: [0, 0.0, np.inf, -np.inf, 0])
    for p in paths:
        chan, val, t = read_records(p)
        if len(chan) == 0:
            continue
        span = float(t.max() - t.min()) or 1.0
        for c in np.unique(chan):
            m = chan == c
            a = acc[int(c)]
            a[0] += int(m.sum())
            a[1] += int(m.sum()) / span
            a[2] = min(a[2], float(val[m].min()))
            a[3] = max(a[3], float(val[m].max()))
            a[4] += 1
    return {
        c: ChannelStat(c, a[0], a[1] / max(1, a[4]), a[2], a[3], a[4])
        for c, a in acc.items()
    }


def write_glossary(paths: list[Path], out: Path) -> int:
    """Write the channel index.

    With no recordings given, this emits the reference table alone — the channel
    map, scales and evidence, with the observed-statistics columns left empty.
    That is what ships with the project: the ranges in a populated index are
    measurements of whoever's footage generated it, and a latitude/longitude range
    in particular says where that person drove.
    """
    stats = gather(paths) if paths else {
        c: ChannelStat(c, 0, 0.0, float("nan"), float("nan"), 0)
        for c in sorted(set(CHANNELS) | set(EVIDENCE) | set(UNKNOWN_NOTES))
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([
            "channel", "name", "confidence", "unit", "scale", "offset",
            "typical_hz", "raw_min", "raw_max", "scaled_min", "scaled_max",
            "samples", "files_seen", "evidence_or_notes",
        ])
        for c in sorted(stats):
            s = stats[c]
            name, unit, scale = CHANNELS.get(c, (f"ch_{c:02x}", "", 1.0))
            off = OFFSETS.get(c, 0.0)
            if c in EVIDENCE:
                conf, note = EVIDENCE[c]
            else:
                conf, note = UNKNOWN, UNKNOWN_NOTES.get(c, "")
            has_stats = s.files > 0
            scaled = ("", "")
            if c in CHANNELS and has_stats:
                scaled = (f"{s.raw_min * scale - off:g}",
                          f"{s.raw_max * scale - off:g}")
            w.writerow([
                f"0x{c:02x}", name, conf, unit,
                f"{scale:g}" if c in CHANNELS else "",
                f"{off:g}" if off else "",
                f"{s.rate:.2f}" if has_stats else "",
                f"{s.raw_min:g}" if has_stats else "",
                f"{s.raw_max:g}" if has_stats else "",
                scaled[0], scaled[1],
                s.samples if has_stats else "",
                s.files if has_stats else "",
                note,
            ])
    return len(stats)
