"""Pace, distance and race-time text: one way in, one way out.

Every surface that prints a pace or a distance — workout cards, step labels,
coaching notes, the watch export — formats it here, and every form field that
accepts a race time is parsed here. The rules are small but they are rules
(a distance is *truncated* to one decimal, never rounded; a pace never shows
``:60``), and hand-rolled ``:.1f`` / ``round`` copies are how they drifted.

Pure stdlib, so it lives in ``app/core`` and may be imported from any layer.
"""

from typing import Optional


def format_pace_bare(pace_min_per_km: float) -> str:
    """Convert decimal pace to 'mm:ss' without the '/km' suffix.

    Args:
        pace_min_per_km: Pace in decimal minutes per kilometer.

    Returns:
        Formatted pace string like '6:36', or '--' for invalid values.
    """
    if not pace_min_per_km or pace_min_per_km <= 0:
        return "--"
    minutes = int(pace_min_per_km)
    seconds = round((pace_min_per_km - minutes) * 60)
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}"


def format_pace(pace_min_per_km: float) -> str:
    """Convert decimal pace (e.g. 6.60) to 'mm:ss/km' (e.g. '6:36/km').

    Args:
        pace_min_per_km: Pace in decimal minutes per kilometer.

    Returns:
        Formatted pace string like '6:36/km', or '--' for invalid values.
    """
    bare = format_pace_bare(pace_min_per_km)
    return bare if bare == "--" else f"{bare}/km"


def truncate_km(distance_km: Optional[float]) -> float:
    """Truncate a distance to one decimal place, WITHOUT rounding.

    This is the single source of truth for how a distance becomes a
    one-decimal display value across the whole product. A segment computed at
    0.775 km must show as 0.7 km, never 0.8 km: warm-up / cool-down splits are
    derived from integer-meter arithmetic (``int(round(total_m * 0.25))``),
    which routinely yields 3-decimal kilometre values like 1.075 or 1.875. We
    truncate rather than round so the displayed number can never claim more
    distance than the workout actually prescribes, and so the figure shown is
    stable regardless of which code path rendered it.

    Truncation is done in integer space (``int(x * 10) / 10``) to avoid binary
    floating-point surprises around the rounding boundary.
    """
    if not distance_km or distance_km <= 0:
        return 0.0
    return int(distance_km * 10) / 10.0


def format_km(distance_km: Optional[float]) -> str:
    """Render a distance as a one-decimal string, truncated (never rounded).

    Always emits exactly one decimal place (e.g. ``"1.0"``, ``"0.7"``,
    ``"13.0"``) so distances read consistently in the UI. Use this everywhere a
    kilometre value is shown to the runner — segment cards, workout
    descriptions, step labels — instead of ad-hoc ``:g`` / ``round(1)`` /
    ``:.1f`` formatting, which variously rounded, dropped trailing zeros, or
    exposed 3-decimal noise.
    """
    return f"{truncate_km(distance_km):.1f}"


def parse_race_time_to_seconds(time_str: str | None) -> int | None:
    """Convert HH:MM:SS or MM:SS string to integer seconds."""
    if not time_str:
        return None
    parts = time_str.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None
    return None


def parse_time_to_pace(time_str: str, distance_km: float) -> float:
    """Parse a time string (MM:SS or HH:MM:SS) and return pace in min/km."""
    parts = time_str.strip().split(":")
    if len(parts) == 2:
        minutes = int(parts[0])
        seconds = int(parts[1])
        total_minutes = minutes + seconds / 60
    elif len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
        total_minutes = hours * 60 + minutes + seconds / 60
    else:
        raise ValueError("Time must be in MM:SS or HH:MM:SS format")
    return total_minutes / distance_km
