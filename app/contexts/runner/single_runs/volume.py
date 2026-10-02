"""The runner's recent weekly volume, read from what they actually logged."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import RunLog

_WINDOW_WEEKS = 4


def recent_weekly_km(user_id: str, db: Session, today: date) -> float:
    """Average weekly distance over the last four weeks.

    A plan knows its weekly volume because it prescribed it. A single run has
    to ask the log instead, and the answer gates how demanding an interval
    session the builder will hand out. No runs means 0.0, which selects the
    most conservative session — the right default for an unknown runner.
    """
    since = datetime.combine(today - timedelta(weeks=_WINDOW_WEEKS), time.min)
    total = (
        db.query(func.sum(RunLog.distance_km))
        .filter(RunLog.user_id == user_id, RunLog.date >= since)
        .scalar()
    )
    return round(float(total or 0.0) / _WINDOW_WEEKS, 1)
