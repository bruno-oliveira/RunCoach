"""Missed week detection (weeks with zero logged runs)."""

from collections import defaultdict
from typing import Dict, List

from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.core.training.plan_calendar import compute_current_week
from app.models import RunLog
from app.utils import to_date as _to_date

from ._helpers import today_date


def detect_missed_weeks(
    plan_id: str,
    user_id: str,
    db: Session,
) -> List[int]:
    training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)

    if not training_plan or not training_plan.start_date:
        return []

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    total_weeks = training_plan.weeks_duration or 0
    current_week = compute_current_week(
        start_date, today, total_weeks=total_weeks, pre_start=1
    )

    runs = (
        db.query(RunLog)
        .filter(
            RunLog.user_id == user_id,
            RunLog.training_plan_id == plan_id,
        )
        .all()
    )

    weekly_runs: Dict[int, int] = defaultdict(int)
    for run in runs:
        rd = _to_date(run.date)
        if rd and start_date:
            d = (rd - start_date).days
            if d >= 0:
                wk = d // 7 + 1
                weekly_runs[wk] += 1

    missed = []
    for wk in range(1, current_week):
        if weekly_runs.get(wk, 0) == 0:
            missed.append(wk)
    return missed
