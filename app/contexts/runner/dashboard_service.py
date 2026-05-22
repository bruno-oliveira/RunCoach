"""Dashboard data service — keeps ORM lookups out of the web layer."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import User
from app.models.run_log import RunLog


def has_runner_profile(
    user: User, db: Session, *, weeks: int = 12, min_runs: int = 3
) -> bool:
    """Return True if the user has logged enough runs to have a runner profile.

    Defaults: at least 3 runs in the last 12 weeks.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(weeks=weeks)).replace(tzinfo=None)
    run_count = (
        db.query(RunLog.id)
        .filter(RunLog.user_id == user.id, RunLog.date >= cutoff)
        .limit(min_runs)
        .count()
    )
    return run_count >= min_runs
