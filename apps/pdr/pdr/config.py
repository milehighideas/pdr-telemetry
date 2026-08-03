"""Decoder geometry and thresholds, calibrated for this camera's 1920x1080 output.

Every constant here was derived empirically by the scripts in `pdr.calibration`
and is reproduced verbatim from the original 2026-07-12 pipeline. Changing a value by
hand changes decoded output silently — recalibrate instead.
"""

# ffmpeg crop of the green lap timer: WxH at (X, Y) in the source frame.
CROP_W, CROP_H = 330, 64
CROP_X, CROP_Y = 1600, 296

# Temporal sampling rate (Hz). The original pipeline decoded at 4.
DEFAULT_FPS = 4

# Digit cells as (x0, x1) column ranges within the crop.
# D1 (tens-of-minutes) is always unlit on this HUD, so it is never sampled.
CELLS = {
    "D2": (51, 91),
    "D3": (105, 143),
    "D4": (147, 185),
    "D5": (202, 241),
    "D6": (242, 281),
}

# Vertical extent of the digits within the crop.
Y0, Y1 = 4, 54

# Slant-aware segment sample points, as (fx, fy) fractions of each cell.
# Derived from an '8' template — the digits are italicised, so these are not
# the symmetric positions a naive 7-segment layout would use.
SEG = {
    "a": (0.52, 0.08),
    "b": (0.80, 0.24),
    "c": (0.72, 0.74),
    "d": (0.40, 0.94),
    "e": (0.12, 0.80),
    "f": (0.20, 0.24),
    "g": (0.46, 0.52),
}

# Lit-segment set -> digit.
PAT = {
    frozenset("abcdef"): "0",
    frozenset("bc"): "1",
    frozenset("abdeg"): "2",
    frozenset("abcdg"): "3",
    frozenset("bcfg"): "4",
    frozenset("acdfg"): "5",
    frozenset("acdefg"): "6",
    frozenset("abc"): "7",
    frozenset("abcdefg"): "8",
    frozenset("abcdfg"): "9",
}

# Green-lit pixel mask. Deliberately strict: a looser mask picks up the unlit
# "ghost" segments the HUD always draws, which decode as 8 everywhere.
GREEN_MIN = 170
GREEN_OVER_RED = 90
GREEN_OVER_BLUE = 90

# A segment counts as lit when this fraction of its sample patch is green.
SEG_ON = 0.34
# Half-size of the square sample patch, in pixels.
SEG_PATCH = 3

# --- Lap detection ---------------------------------------------------------

# The timer must fall at least this many seconds to count as a finish-line reset.
LAP_DROP = 20.0
# Values within this many seconds of the pre-reset peak are the frozen final time.
LAP_PLATEAU = 0.6
# Seconds before a reset searched for that frozen peak.
LAP_LOOKBACK = 2.0
# The HUD holds the final time this long before restarting the count.
FREEZE = 2.0
# Median filter half-width applied to the decoded series.
MEDIAN_K = 2

# --- Lap classification (seconds) ------------------------------------------

FLYING_MIN, FLYING_MAX = 60, 155
