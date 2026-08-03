"""A profile is an overlay plus the lap-timing state — what a given video contains.

Overlay mode and lap timing are independent settings on the car, so the readable
fields are the product of the two, not a single enum. Named profiles exist for the
combinations that actually get recorded.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import overlays
from .overlays import Field, Overlay


@dataclass(frozen=True)
class Profile:
    """An overlay mode together with whether lap timing was switched on."""

    overlay: Overlay
    lap_timing: bool = False

    @property
    def name(self) -> str:
        suffix = "with-timing" if self.lap_timing else "no-timing"
        return f"{self.overlay.name}-{suffix}"

    @property
    def fields(self) -> tuple[Field, ...]:
        return self.overlay.available(self.lap_timing)

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)

    def get(self, name: str) -> Field:
        return self.overlay.get(name, self.lap_timing)

    def __str__(self) -> str:
        return self.name


# The combinations actually recorded. Track is only ever run with lap timing on,
# so track-no-timing is deliberately absent.
TRACK_TIMED = Profile(overlays.TRACK, lap_timing=True)
SPORT = Profile(overlays.SPORT, lap_timing=False)
NONE = Profile(overlays.NONE, lap_timing=False)
TIMING_TIMED = Profile(overlays.TIMING, lap_timing=True)

PROFILES: dict[str, Profile] = {
    "track": TRACK_TIMED,
    "sport": SPORT,
    "none": NONE,
    "timing": TIMING_TIMED,
}

# Longer aliases, matching how these get described in conversation.
ALIASES = {
    "lap-times-with-track-overlay": "track",
    "track-with-timing": "track",
    "no-lap-times-with-sport-overlay": "sport",
    "sport-no-timing": "sport",
    "no-lap-times-with-no-overlay": "none",
    "no-overlay": "none",
    "lap-times-with-timing-overlay": "timing",
}


def get(name: str) -> Profile:
    key = ALIASES.get(name, name)
    try:
        return PROFILES[key]
    except KeyError:
        raise KeyError(
            f"unknown profile {name!r}; known: {', '.join(sorted(PROFILES))}"
        ) from None


def names() -> list[str]:
    return sorted(PROFILES)
