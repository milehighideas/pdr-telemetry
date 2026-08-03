"""Timing overlay — known to exist, geometry not yet derived.

No footage recorded in Timing mode is available, so nothing here is measured.
Asking for its fields raises NotCalibrated rather than returning plausible-looking
coordinates that would silently decode the wrong pixels.

To calibrate: record a short clip in Timing mode, extract frames, and work through
the same route used for Track —

    pdr calibrate profile <frames>   # where lit content sits
    pdr calibrate bands   <frames>   # digit cell x/y bands
    pdr calibrate verify  <frames>   # decode vs hand-labelled frames
"""

from __future__ import annotations

from .base import Overlay

TIMING = Overlay(
    name="timing",
    description="Lap-timing focused HUD. NOT YET CALIBRATED — needs sample footage.",
    fields=(),
    supports_lap_timing=True,
    calibrated=False,
)
