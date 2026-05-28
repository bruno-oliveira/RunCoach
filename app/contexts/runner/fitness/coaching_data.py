"""Data-access helpers feeding the pure coaching-feedback core.

Keeps the SQL out of ``app.core.coaching`` (which must stay pure) while reusing
the exact query shape the feedback engine previously ran inline. Complex filter
chains live in the calling service per ``SQLAlchemyRunRepository``'s documented
convention.
"""

from __future__ import annotations

from datetime import timedelta
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import RunLog, TrainingPlan, WeeklyPlan


def fetch_volume_inputs(run_log, db: Session) -> Optional[Tuple[int, float, float]]:
    """Resolve ``(week_number, logged_km, planned_km)`` for a run's plan week.

    Returns None when the run isn't tied to a started plan, the week is before
    the plan start, the week has no plan row, or the week has no planned volume.
    Pairs with :func:`app.core.coaching.volume_tracker.volume_feedback`.
    """
    if not run_log.training_plan_id:
        return None

    plan = (
        db.query(TrainingPlan)
        .filter(TrainingPlan.id == run_log.training_plan_id)
        .first()
    )
    if not plan or not plan.start_date:
        return None

    run_date = _naive(run_log.date)
    plan_start = _naive(plan.start_date)
    days_since_start = (run_date - plan_start).days
    if days_since_start < 0:
        return None
    week_num = (days_since_start // 7) + 1

    wp = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number == week_num,
        )
        .first()
    )
    if not wp:
        return None

    planned_km = wp.total_km or 0
    if planned_km <= 0:
        return None

    week_start = plan.start_date + timedelta(weeks=week_num - 1)
    week_end = week_start + timedelta(days=7)
    logged_km = sum(
        r.distance_km
        for r in db.query(RunLog)
        .filter(
            RunLog.training_plan_id == plan.id,
            RunLog.user_id == run_log.user_id,
            RunLog.date >= week_start,
            RunLog.date < week_end,
        )
        .all()
    )
    return week_num, logged_km, planned_km


def fetch_pattern_candidates(run_log, db: Session) -> List[RunLog]:
    """Same-user runs within 45 days (excluding ``run_log``) with planned/actual pace.

    Newest first. The workout-type match and recency weighting happen in the
    pure :func:`app.core.coaching.pattern_analyzer.pattern_feedback`.
    """
    if not run_log.avg_pace_min_km or not run_log.planned_pace_min_km:
        return []

    cutoff = run_log.date - timedelta(days=45)
    return (
        db.query(RunLog)
        .filter(
            RunLog.user_id == run_log.user_id,
            RunLog.avg_pace_min_km.isnot(None),
            RunLog.planned_pace_min_km.isnot(None),
            RunLog.date >= cutoff,
            RunLog.id != run_log.id,
        )
        .order_by(RunLog.date.desc())
        .all()
    )


def _naive(dt):
    """Drop tzinfo for naive arithmetic, matching the legacy inline behavior."""
    return dt.replace(tzinfo=None) if hasattr(dt, "replace") and dt.tzinfo else dt
