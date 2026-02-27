"""Shared utility functions for the RunCoach application."""

from datetime import datetime, timedelta, timezone


class TimestampAdapter:
    """Centralizes all timestamp conversions between Strava, the DB, and the UI.

    Three timestamp contexts must stay consistent:
    - Strava API  — uses UTC epoch seconds for the ``after`` filter parameter.
    - DB storage  — stores ``start_date_local`` (runner's local time, no TZ) as a
                    naive datetime.
    - UI display  — filters by local calendar days, using local midnight as the
                    cutoff so that the boundary day is always fully included.

    The key rule: never anchor the ``after`` timestamp to ``now - N×86400s``.
    That anchors to the current time-of-day, silently dropping runs from the early
    hours of calendar day N whenever the sync runs later in the day.  UTC midnight
    is the safe anchor — it always includes the full calendar day.
    """

    @staticmethod
    def days_ago_utc_epoch(days: int) -> int:
        """Return the UTC epoch for 00:00:00 UTC exactly N calendar days ago.

        Use this for every Strava API ``after`` parameter.  Because Strava's
        ``after`` is compared against each activity's ``start_date`` (UTC), anchoring
        to UTC midnight guarantees the complete calendar day is always fetched,
        regardless of what time the sync runs.

        Args:
            days: Number of calendar days to look back.

        Returns:
            UTC epoch (seconds) for 00:00:00 UTC on (today − N days).
        """
        midnight_today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return int((midnight_today - timedelta(days=days)).timestamp())

    @staticmethod
    def parse_strava_local(start_date_local: str) -> datetime:
        """Parse Strava's ``start_date_local`` into a naive datetime for DB storage.

        Strava encodes the activity start time in the athlete's local timezone as an
        ISO 8601 string.  The ``Z`` suffix it sometimes appends is misleading — the
        value is *local*, not UTC — so we strip it before parsing and store a
        timezone-naive datetime that represents the runner's wall-clock time.

        Args:
            start_date_local: ISO 8601 string from Strava, e.g. ``"2026-02-25T07:47:53Z"``.

        Returns:
            Timezone-naive datetime representing the local run start time.
        """
        return datetime.fromisoformat(start_date_local.replace("Z", ""))


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
