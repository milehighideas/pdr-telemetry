"""Extract lap times from Cadillac PDR dashcam video.

The PDR burns a green 7-segment lap timer into its recordings. This package crops
that region, decodes the digits per frame, and derives laps from the timer's resets.
No external telemetry is involved.
"""

__version__ = "0.1.0"
