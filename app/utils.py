"""Shared utility functions for the RunCoach application."""


def format_pace(pace_min_per_km: float) -> str:
    """Convert decimal pace (e.g. 6.60) to 'mm:ss/km' (e.g. '6:36/km').

    Args:
        pace_min_per_km: Pace in decimal minutes per kilometer.

    Returns:
        Formatted pace string like '6:36/km', or '--' for invalid values.
    """
    if not pace_min_per_km or pace_min_per_km <= 0:
        return "--"
    minutes = int(pace_min_per_km)
    seconds = round((pace_min_per_km - minutes) * 60)
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}/km"


def format_pace_bare(pace_min_per_km: float) -> str:
    """Convert decimal pace to 'mm:ss' without the '/km' suffix.

    Args:
        pace_min_per_km: Pace in decimal minutes per kilometer.

    Returns:
        Formatted pace string like '6:36'.
    """
    minutes = int(pace_min_per_km)
    seconds = round((pace_min_per_km - minutes) * 60)
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}"
