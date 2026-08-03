"""No overlay — clean video, nothing to decode.

Present as a real overlay rather than a null so that profile selection and
auto-detection can name it explicitly instead of failing.
"""

from __future__ import annotations

from .base import Overlay

NONE = Overlay(
    name="none",
    description="Clean recording with no HUD. No telemetry is recoverable from "
    "the image.",
    fields=(),
    supports_lap_timing=False,
    calibrated=True,
)
