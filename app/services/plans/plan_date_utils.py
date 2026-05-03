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


def compute_current_week(start_date: date, today: date) -> Optional[int]:
    """Compute 1-indexed current week number, or None if plan hasn't started or is over."""
    delta_days = (today - start_date).days
    if delta_days < 0:
        return None
    return (delta_days // 7) + 1


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
