"""Resolve the week review for a plan — which week, and what was logged in it.

A plan week runs from the plan's start weekday, not necessarily Monday, so the
review is anchored to the plan: it is "due" on the **last day** of a plan week
(evening push, and the card appears) and stays on the page through the **first
day** of the next, so a runner who opens the app on Monday morning still sees
how last week landed before the new one takes over.

Cross-context by nature (plan weeks + the runner's logged runs), hence the
application layer. The judgement is pure: :mod:`app.core.coaching.week_review`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.coaching.week_review import WeekReview, build_week_review
from app.core.training.periodization.plan_calendar import compute_current_week
from app.models import RunLog, TrainingPlan
from app.utils import to_date


@dataclass(frozen=True)
class DueReview:
    review: WeekReview
    week_start: date
    # The plan week's last day — the natural idempotency key for the push.
    week_end: date
    change_headline: Optional[str] = None


def due_review(
    plan: TrainingPlan, user_id: str, db: Session, today: date
) -> Optional[DueReview]:
    """The review to show today, or ``None`` outside the review window."""
    start = to_date(plan.start_date)
    if start is None:
        return None
    current = compute_current_week(start, today, pre_start=0)
    if not current:
        return None
    days_into_week = (today - start).days % 7

    if days_into_week == 6:
        week_number = current  # the week's last day
    elif days_into_week == 0 and current > 1:
        week_number = current - 1  # first day of the next week
    else:
        return None
    if week_number > (plan.weeks_duration or 0):
        return None

    return review_for_week(plan, user_id, db, week_number)


def review_for_week(
    plan: TrainingPlan, user_id: str, db: Session, week_number: int
) -> Optional[DueReview]:
    start = to_date(plan.start_date)
    weeks = plan.plan_data or []
    week = next((w for w in weeks if w.get("week") == week_number), None)
    if start is None or week is None:
        return None
    next_week = next((w for w in weeks if w.get("week") == week_number + 1), None)

    week_start = start + timedelta(weeks=week_number - 1)
    week_end = week_start + timedelta(days=6)
    rows = (
        db.query(RunLog.date, RunLog.distance_km)
        .filter(
            RunLog.user_id == user_id,
            RunLog.date >= datetime.combine(week_start, datetime.min.time()),
            RunLog.date
            < datetime.combine(week_end + timedelta(days=1), datetime.min.time()),
        )
        .all()
    )
    runs = [(to_date(r[0]), float(r[1] or 0)) for r in rows if r[0] is not None]
    review = build_week_review(
        week,
        week_start=week_start,
        runs=[(d, km) for d, km in runs if d is not None],
        next_week=next_week,
    )
    return DueReview(
        review=review,
        week_start=week_start,
        week_end=week_end,
        change_headline=_recent_change(plan, week_start),
    )


def _recent_change(plan: TrainingPlan, since: date) -> Optional[str]:
    """The last automatic plan change, if it happened during this week."""
    change: Dict[str, Any] = plan.last_change_plan or {}
    if not change.get("did_change"):
        return None
    computed = change.get("computed_at")
    try:
        when = datetime.fromisoformat(str(computed)[:19]).date() if computed else None
    except ValueError:
        when = None
    if when is None or when < since:
        return None
    return change.get("reason")
