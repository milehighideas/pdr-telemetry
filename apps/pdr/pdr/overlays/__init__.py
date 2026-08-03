"""Registry of the PDR's overlay modes."""

from __future__ import annotations

from .base import Field, NotCalibrated, Overlay, Region
from .none import NONE
from .sport import SPORT
from .timing import TIMING
from .track import TRACK

OVERLAYS: dict[str, Overlay] = {o.name: o for o in (NONE, SPORT, TRACK, TIMING)}


def get(name: str) -> Overlay:
    try:
        return OVERLAYS[name]
    except KeyError:
        raise KeyError(
            f"unknown overlay {name!r}; known: {', '.join(sorted(OVERLAYS))}"
        ) from None


__all__ = [
    "Field", "NotCalibrated", "Overlay", "Region",
    "OVERLAYS", "get", "NONE", "SPORT", "TRACK", "TIMING",
]
