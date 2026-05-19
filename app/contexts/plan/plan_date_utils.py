"""Date utilities for training plan week tracking."""

from datetime import date, timedelta
from typing import Optional


def build_week_dates(start_date: date, num_weeks: int) -> list[dict]:
    """Build a list of week date ranges from a start date."""
    week_dates = []
    for i in range(num_weeks):
        week_start = start_date + timedelta(weeks=i)
        week_end = week_start + timedelta(days=6)
        week_dates.append({
            "week": i + 1,
            "start": f"{week_start.strftime('%b')} {week_start.day}",
            "end": f"{week_end.strftime('%b')} {week_end.day}",
            "start_iso": week_start.isoformat(),
        })
    return week_dates


def compute_current_week(
    start_date: date,
    today: date,
    *,
    total_weeks: Optional[int] = None,
    pre_start: Optional[int] = None,
    clamp_min: Optional[int] = None,
) -> Optional[int]:
    """Compute the 1-indexed current week number.

    Args:
        start_date: Plan start date.
        today: Reference date (usually today).
        total_weeks: If set, clamp the result to at most ``total_weeks``.
        pre_start: Value to return when ``today`` is before ``start_date``.
            Defaults to ``None`` (plan not yet started).
        clamp_min: If set, clamp the result to at least this value. Use
            ``clamp_min=1`` to guarantee a positive week index in callers
            that don't separately gate on the pre-start case.
    """
    delta_days = (today - start_date).days
    if delta_days < 0:
        return pre_start
    week = (delta_days // 7) + 1
    if clamp_min is not None:
        week = max(clamp_min, week)
    if total_weeks is not None:
        week = min(week, total_weeks)
    return week


def next_monday() -> str:
    """Return the ISO date string of the next Monday."""
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return (today + timedelta(days=days_ahead)).isoformat()


def workout_dates(start_date: date, num_weeks: int) -> dict[tuple[int, int], str]:
    """Map (week, day) to formatted date string like 'Mon, Mar 3'."""
    day_abbrevs = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    result = {}
    for w in range(num_weeks):
        week_start = start_date + timedelta(weeks=w)
        for d in range(7):
            dt = week_start + timedelta(days=d)
            result[(w + 1, d + 1)] = f"{day_abbrevs[d]}, {dt.strftime('%b')} {dt.day}"
    return result


def ensure_seven_days(plan_data: list[dict]) -> list[dict]:
    """Fill missing days in each week with rest entries so all 7 days appear."""
    for week in plan_data:
        workouts = week.get("daily_workouts", [])
        existing_days = {w["day"] for w in workouts}
        for d in range(1, 8):
            if d not in existing_days:
                workouts.append({
                    "day": d,
                    "type": "rest",
                    "distance": 0,
                    "intensity": "rest",
                    "description": "Rest day",
                })
        workouts.sort(key=lambda w: w["day"])
    return plan_data
