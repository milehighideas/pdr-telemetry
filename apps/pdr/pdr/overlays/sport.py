"""Sport overlay — the full performance HUD without any lap-timing elements.

Geometry measured against 1920x1080 footage from the 2026-07-30 rally
(PDR_9981/9982). Track draws these same fields at these same positions and adds
the track map and timer on top, so `track.py` builds on this module rather than
repeating it.

Region bounds are deliberately generous: they are crop windows for the readers,
not tight glyph boxes.
"""

from __future__ import annotations

from .base import Field, Overlay, Region

SPEED = Field(
    "speed", Region(740, 25, 380, 180), "glyph_digits", "mph",
    "large white outlined digits, top centre; widens leftward for 3 digits",
)
SPEED_UNIT = Field(
    "speed_unit", Region(850, 218, 160, 58), "glyph_text", "",
    "static 'MPH' label — useful as an overlay-presence probe",
)
GEAR = Field(
    "gear", Region(1720, 15, 200, 245), "glyph_digits", "",
    "single large white digit, top right",
)
ENGINE_BARS = Field(
    "engine_bars", Region(1378, 20, 200, 185), "bar_blocks", "",
    "two 5-block columns, red-outlined left and green-outlined right; "
    "lit from the bottom up",
)
GMETER = Field(
    "gmeter", Region(40, 650, 430, 350), "gmeter", "g",
    "circular dial with a travelling dot and four numeric readouts "
    "(top / left / right / bottom)",
)
TACH = Field(
    "tach", Region(480, 770, 970, 190), "bar_segments", "rpm",
    "segmented 0-7 bar with numeric scale beneath; read by fill, not OCR",
)
TRIP = Field(
    "trip", Region(690, 955, 280, 65), "glyph_digits", "mi",
    "trip distance, e.g. '15.0 mi'",
)
STEERING = Field(
    "steering", Region(1560, 690, 300, 215), "gauge_needle", "deg",
    "semicircular gauge with a red needle and an amber degree readout",
)

FIELDS = (SPEED, SPEED_UNIT, GEAR, ENGINE_BARS, GMETER, TACH, TRIP, STEERING)

SPORT = Overlay(
    name="sport",
    description="Full performance HUD: speed, gear, g-meter, tach, trip, steering. "
    "No lap timing.",
    fields=FIELDS,
    supports_lap_timing=False,
    calibrated=True,
)
