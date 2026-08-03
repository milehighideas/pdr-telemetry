"""Track overlay — the Sport HUD plus the track map and lap-timing readouts.

The timer and delta geometry here is the original 2026-07-12 calibration and is the
only geometry in this package proven against real output: it reproduces
`lap_times_2026-07-12_HPR.csv` byte for byte. Do not adjust it without re-running
that regression.

Track is only ever recorded with lap timing on, so `available()` for this overlay is
normally called with `lap_timing=True`.
"""

from __future__ import annotations

from ..config import CROP_H, CROP_W, CROP_X, CROP_Y
from .base import Field, Overlay, Region
from .sport import FIELDS as SPORT_FIELDS

LAP_TIMER = Field(
    "lap_timer",
    Region(CROP_X, CROP_Y, CROP_W, CROP_H),
    "seven_segment_green",
    "s",
    "green MM:SS.ss elapsed lap timer; unlit ghost segments are always drawn, "
    "which is why the green mask is strict",
)
DELTA = Field(
    "delta",
    Region(1600, 378, 300, 72),
    "seven_segment_delta",
    "s",
    "signed time gained/lost against a reference lap; green negative, red positive. "
    "Decodable but not a reliable lap source — see pdr.calibration.red",
)
TRACK_MAP = Field(
    "track_map",
    Region(120, 110, 280, 170),
    "presence",
    "",
    "outline of the circuit with a position marker; drawn only when lap timing is "
    "active, so it doubles as the lap-timing-enabled probe",
)

TRACK = Overlay(
    name="track",
    description="Sport HUD plus track map, lap timer and delta.",
    fields=SPORT_FIELDS,
    timing_fields=(LAP_TIMER, DELTA, TRACK_MAP),
    supports_lap_timing=True,
    calibrated=True,
)
