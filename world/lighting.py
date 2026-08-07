from __future__ import annotations

from typing import Dict, Optional, Tuple

RGBA = Tuple[int, int, int, int]


# ---------------------------------------------------------------------------
# Time-of-day palette
# ---------------------------------------------------------------------------
# Anchor tint AND anchor brightness for each named period, paired with the
# hour_of_day (0-23, see world_time.py's WorldClock.hour_of_day) it's
# centered on. Kept as an ordered tuple of (hour, name, tint, brightness)
# -- rather than a plain dict -- since ambient_tint_for_time() needs the
# anchors in hour order to find the two that bracket the current moment
# and blend between them.
#
# Every tint is deliberately desaturated: nothing here is meant to read as
# "daylight", only as "less oppressive than midnight". Brightness now
# ranges well above 1.0 at its peak (noon actually brightens the sprite's
# own colors, not just leaves them unscaled) down to 0.75 at its dimmest,
# so the day/night cycle reads clearly at a glance while the tint curve
# above still keeps the palette itself muted and desaturated.
_PERIODS: Tuple[Tuple[int, str, RGBA, float], ...] = (
    (0,  "midnight", (42, 48, 72, 255), 0.75),     # Deep moonlit blue
    (5,  "late_night", (52, 58, 82, 255), 0.82),   # Before dawn
    (6,  "dawn", (118, 108, 128, 255), 0.95),      # Cold violet-gray
    (8,  "morning", (168, 170, 182, 255), 1.10),   # Cool overcast morning
    (12, "noon", (208, 202, 188, 255), 1.30),      # Muted parchment sunlight
    (16, "afternoon", (186, 168, 145, 255), 1.20), # Dusty warm light
    (18, "evening", (142, 118, 102, 255), 1.00),   # Amber fading light
    (19, "dusk", (96, 84, 118, 255), 0.88),        # Purple-blue twilight
    (21, "night", (58, 66, 94, 255), 0.80),        # Cold blue darkness
)
#: Same anchors keyed by name, for anything that wants a fixed period's
#: tint directly (e.g. a cutscene forcing "it is dusk") without going
#: through the hour-based interpolation below.
TIME_OF_DAY_TINTS: Dict[str, RGBA] = {name: tint for _, name, tint, _brightness in _PERIODS}

#: Same anchors keyed by name, for the brightness half of the pair above.
TIME_OF_DAY_BRIGHTNESS: Dict[str, float] = {name: brightness for _, name, _tint, brightness in _PERIODS}

#: (period_a, period_b) pairs in day order, each spanning from period_a's
#: anchor hour to period_b's -- precomputed once so ambient_tint_for_time()
#: doesn't rebuild this every call. The final pair wraps from "night" back
#: around to "midnight" (the next day's), which is why the wrap uses %24
#: arithmetic rather than a plain last-to-first zip.
_PERIOD_SPANS: Tuple[Tuple[Tuple[int, str, RGBA, float], Tuple[int, str, RGBA, float]], ...] = tuple(
    zip(_PERIODS, _PERIODS[1:] + (_PERIODS[0],))
)


def period_for_hour(hour_of_day: int) -> str:
    """Name of whichever named period's anchor `hour_of_day` sits closest
    to (wrapping around midnight). For HUD/debug display only -- actual
    rendering uses the smoothly-interpolated ambient_tint_for_time()
    below instead of snapping to one named period."""
    hour_of_day %= 24
    closest_name = _PERIODS[0][1]
    closest_distance = 24
    for anchor_hour, name, _tint, _brightness in _PERIODS:
        distance = abs(hour_of_day - anchor_hour)
        distance = min(distance, 24 - distance)  # wrap around midnight
        if distance < closest_distance:
            closest_distance = distance
            closest_name = name
    return closest_name


def ambient_tint_for_time(hour_of_day: int, minute_of_hour: int = 0) -> RGBA:
    """
    Smoothly-interpolated ambient light tint for the given time of day,
    with the period's brightness (see TIME_OF_DAY_BRIGHTNESS) already
    folded in via apply_brightness() -- callers get back one RGBA that
    captures both "what color is the light" and "how much of it is
    there", and can stack it into combine_tints() exactly as before.

    Rather than snapping straight from one named period's tint/brightness
    to the next, this linearly blends between whichever two anchors
    bracket the current moment, so the world doesn't visibly "jump" the
    instant the clock crosses from, say, dusk into night. `minute_of_hour`
    only refines *where within the hour* that blend sits -- the day/night
    cycle itself is granular to the hour, matching world_time.py's
    WorldClock.hour_of_day.
    """
    hour = (hour_of_day + minute_of_hour / 60.0) % 24

    for (hour_a, _name_a, tint_a, brightness_a), (hour_b, _name_b, tint_b, brightness_b) in _PERIOD_SPANS:
        span = (hour_b - hour_a) % 24
        if span == 0:
            continue
        position = (hour - hour_a) % 24
        if position > span:
            continue  # `hour` isn't within this bracket -- try the next
        fraction = position / span
        blended_tint = _lerp_tint(tint_a, tint_b, fraction)
        blended_brightness = brightness_a + (brightness_b - brightness_a) * fraction
        return apply_brightness(blended_tint, blended_brightness)

    # Unreachable in practice (the spans above always cover the full
    # 24-hour cycle), but fall back to the nearest named anchor rather
    # than raising if a future edit to _PERIODS ever leaves a gap.
    name = period_for_hour(int(hour))
    return apply_brightness(TIME_OF_DAY_TINTS[name], TIME_OF_DAY_BRIGHTNESS[name])


def _lerp_tint(tint_a: RGBA, tint_b: RGBA, fraction: float) -> RGBA:
    fraction = max(0.0, min(1.0, fraction))
    return tuple(
        int(round(tint_a[channel] + (tint_b[channel] - tint_a[channel]) * fraction))
        for channel in range(4)
    )


# ---------------------------------------------------------------------------
# Stack stages
# ---------------------------------------------------------------------------

def apply_brightness(tint: RGBA, factor: float) -> RGBA:
    """Scale a tint's RGB channels by `factor` (1.0 = unchanged, <1.0
    darker, >1.0 brighter), clamped to a valid byte range. Alpha is left
    untouched -- brightness affects how lit a tile looks, not how
    transparent it is."""
    r, g, b, a = tint
    return (_clamp_byte(r * factor), _clamp_byte(g * factor), _clamp_byte(b * factor), a)


def apply_contrast(tint: RGBA, factor: float) -> RGBA:
    """Push a tint's RGB channels toward (factor > 1.0) or away from
    (factor < 1.0) middle gray, clamped to a valid byte range. A factor
    of 1.0 is a no-op; a factor pulled toward 0.0 is useful for a foggy/
    overcast weather effect flattening everything toward gray."""
    r, g, b, a = tint
    midpoint = 127.5
    return (
        _clamp_byte(midpoint + (r - midpoint) * factor),
        _clamp_byte(midpoint + (g - midpoint) * factor),
        _clamp_byte(midpoint + (b - midpoint) * factor),
        a,
    )


def combine_tints(*tints: Optional[RGBA]) -> RGBA:
    """
    Stack any number of RGBA tints into the single tint value
    graphics.draw_tile() actually accepts, by multiplying each channel
    together (as a fraction of 255) in order -- the same math a
    multiply-blend layer stack in an image editor uses, so every stage
    in this module's docstring only ever darkens what came before it,
    never brightens past the base sprite. This is what keeps a dark-
    fantasy scene from accidentally washing out no matter how many
    tinting stages get stacked onto it.

    `None` entries are skipped, so a caller can pass a stage that simply
    doesn't apply right now (e.g. no ambient tint indoors, no local
    light nearby) without wrapping every call in its own `if`. Passing
    no real tints at all returns opaque white (255, 255, 255, 255) --
    the identity tint, i.e. "draw the sprite unmodified".
    """
    result: RGBA = (255, 255, 255, 255)
    for tint in tints:
        if tint is None:
            continue
        result = (
            _clamp_byte(result[0] * tint[0] / 255.0),
            _clamp_byte(result[1] * tint[1] / 255.0),
            _clamp_byte(result[2] * tint[2] / 255.0),
            _clamp_byte(result[3] * tint[3] / 255.0),
        )
    return result


def _clamp_byte(value: float) -> int:
    return max(0, min(255, int(round(value))))