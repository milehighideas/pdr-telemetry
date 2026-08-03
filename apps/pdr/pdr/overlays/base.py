"""What an overlay is: a named set of readable fields at known screen positions.

The PDR renders one of four overlays over its recordings — none, sport, track,
timing — and lap timing is a separate toggle on top of that. An `Overlay` describes
where each field sits for one 1920x1080 recording mode; a `Profile` (see
`pdr.profile`) pairs an overlay with the lap-timing state to say which fields are
actually present in a given video.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class NotCalibrated(RuntimeError):
    """Raised when an overlay is known to exist but its geometry is not yet derived."""


@dataclass(frozen=True)
class Region:
    """A crop rectangle in source-frame pixels."""

    x: int
    y: int
    w: int
    h: int

    @property
    def ffmpeg_crop(self) -> str:
        return f"crop={self.w}:{self.h}:{self.x}:{self.y}"


@dataclass(frozen=True)
class Field:
    """One readable quantity on screen.

    `reader` names the decoding strategy — see `pdr.readers`. `unit` and `notes` are
    documentation only; nothing dispatches on them.
    """

    name: str
    region: Region
    reader: str
    unit: str = ""
    notes: str = ""


@dataclass(frozen=True)
class Overlay:
    """A named overlay mode and the fields it draws."""

    name: str
    description: str
    fields: tuple[Field, ...] = field(default_factory=tuple)
    # Fields present only when lap timing is switched on.
    timing_fields: tuple[Field, ...] = field(default_factory=tuple)
    supports_lap_timing: bool = False
    calibrated: bool = True

    def available(self, lap_timing: bool = False) -> tuple[Field, ...]:
        """Fields readable in this overlay, given the lap-timing state."""
        if not self.calibrated:
            raise NotCalibrated(
                f"the {self.name!r} overlay has no calibrated geometry yet — "
                f"record a sample in {self.name} mode and run "
                f"'pdr calibrate bands <frames>' against it"
            )
        if lap_timing and not self.supports_lap_timing:
            raise ValueError(f"the {self.name!r} overlay has no lap timing")
        return self.fields + (self.timing_fields if lap_timing else ())

    def get(self, field_name: str, lap_timing: bool = False) -> Field:
        for f in self.available(lap_timing):
            if f.name == field_name:
                return f
        raise KeyError(f"{self.name!r} overlay has no field {field_name!r}")
