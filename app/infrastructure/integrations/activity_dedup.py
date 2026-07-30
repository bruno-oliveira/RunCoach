"""Cross-source duplicate detection for imported activities.

A runner whose watch feeds both Strava and Intervals.icu is offered the same
physical run twice, under two unrelated provider ids. Each importer deduplicates
against its own id column only, so without this the second provider inserts a
second row for a run that already exists and every distance total counts it
twice.

Matching is on the activity itself: when it started and how far it went.
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.run_log import RunLog

# Providers report the start of an activity to the second and agree on it; this
# slack only absorbs rounding.
START_TOLERANCE = timedelta(minutes=2)

# ...except when they disagree about the UTC offset. Both send a local start
# time, and around a DST boundary one side can still be on the old offset — the
# same run, with the clock a whole number of hours out. Whole-hour differences
# up to this bound are folded away before START_TOLERANCE is applied.
MAX_CLOCK_SHIFT = timedelta(hours=3)

# Distances differ slightly between providers because they re-derive them from
# the same GPS track.
DISTANCE_TOLERANCE_RATIO = 0.01
DISTANCE_TOLERANCE_KM = 0.05

_HOUR_SECONDS = 3600.0


def is_same_activity(
    date_a: Optional[datetime],
    distance_a: Optional[float],
    date_b: Optional[datetime],
    distance_b: Optional[float],
) -> bool:
    """Whether two runs are the same activity seen through two providers.

    Args:
        date_a: Local start time of the first run.
        distance_a: Distance of the first run, in km.
        date_b: Local start time of the second run.
        distance_b: Distance of the second run, in km.

    Returns:
        True when the pair started at the same moment (allowing for a whole-hour
        offset disagreement) and covered the same distance.
    """
    if date_a is None or date_b is None:
        return False
    if distance_a is None or distance_b is None:
        return False

    delta = abs((date_a - date_b).total_seconds())
    if delta > MAX_CLOCK_SHIFT.total_seconds():
        return False

    # Distance from the nearest whole hour: 0 for an exact match, 0 again for a
    # clean one- or two-hour offset, and the real gap for two genuinely separate
    # runs on the same morning.
    into_hour = delta % _HOUR_SECONDS
    off_hour = min(into_hour, _HOUR_SECONDS - into_hour)
    if off_hour > START_TOLERANCE.total_seconds():
        return False

    tolerance = max(DISTANCE_TOLERANCE_KM, distance_a * DISTANCE_TOLERANCE_RATIO)
    return abs(distance_a - distance_b) <= tolerance


def find_duplicate_run(
    db: Session,
    user_id: str,
    date: Optional[datetime],
    distance_km: Optional[float],
) -> Optional[RunLog]:
    """The runner's existing row for this activity, if another provider brought it in.

    Args:
        db: Database session.
        user_id: Owner of the runs to search.
        date: Local start time of the incoming activity.
        distance_km: Distance of the incoming activity, in km.

    Returns:
        The matching RunLog, or None when this activity is new.
    """
    if date is None or distance_km is None:
        return None

    candidates = (
        db.query(RunLog)
        .filter(
            RunLog.user_id == user_id,
            RunLog.date >= date - MAX_CLOCK_SHIFT,
            RunLog.date <= date + MAX_CLOCK_SHIFT,
        )
        .all()
    )
    for candidate in candidates:
        if is_same_activity(date, distance_km, candidate.date, candidate.distance_km):
            return candidate
    return None


__all__ = ["MAX_CLOCK_SHIFT", "find_duplicate_run", "is_same_activity"]
