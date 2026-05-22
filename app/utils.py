"""Shared utility functions for the RunCoach application."""

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Union

from sqlalchemy.orm.attributes import flag_modified

_TAG_RE = re.compile(r"<[^>]*>")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def persist_json(instance, attr_name: str) -> None:
    # SQLAlchemy's default JSON column type doesn't observe in-place
    # mutations, and reassigning the same Python reference doesn't flag the
    # column dirty either — so any nested dict/list edit (e.g. mutating
    # plan_data[w]["daily_workouts"][i]["distance"]) is silently dropped at
    # commit. Call this after such mutations to force a write.
    flag_modified(instance, attr_name)


def sanitize_user_text(value: Optional[str]) -> Optional[str]:
    """Defense-in-depth scrub for free-text user input rendered back to the UI.

    Templates already autoescape on output, so this is belt-and-braces for paths
    that bypass Jinja (raw API consumers, future innerHTML usage). Strips HTML/XML
    tags and non-printable control characters; preserves tab/newline/CR.
    """
    if value is None:
        return None
    cleaned = _TAG_RE.sub("", value)
    cleaned = _CONTROL_RE.sub("", cleaned)
    cleaned = cleaned.strip()
    return cleaned or None


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


def to_date(value: Union[datetime, date, None]) -> Optional[date]:
    """Coerce a datetime or date to a plain date object.

    Args:
        value: A datetime, date, or None.

    Returns:
        A date object, or None if value is None.
    """
    if value is None:
        return None
    if hasattr(value, "date") and callable(value.date):
        return value.date()
    return value
