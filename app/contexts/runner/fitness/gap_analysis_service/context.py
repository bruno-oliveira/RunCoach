"""Gap-analysis setup: parsed plan, logged runs, and per-week breakpoints."""

from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.training.plan_calendar import compute_current_week
from app.models import RunLog, TrainingPlan
from app.utils import to_date as _to_date


class _PlanGapContext:
    """Shared setup data for gap analysis: parsed plan, logged runs, and week state."""

    __slots__ = (
        "plan",
        "plan_data",
        "start_date",
        "total_weeks",
        "current_week",
        "runs",
    )

    def __init__(
        self,
        plan: TrainingPlan,
        plan_data: List[dict],
        start_date: date,
        total_weeks: int,
        current_week: int,
        runs: List[RunLog],
    ) -> None:
        self.plan = plan
        self.plan_data = plan_data
        self.start_date = start_date
        self.total_weeks = total_weeks
        self.current_week = current_week
        self.runs = runs


def _load_gap_context(
    plan: TrainingPlan,
    user_id: str,
    db: Session,
    *,
    require_runs: bool,
) -> Optional[_PlanGapContext]:
    """Parse plan data, fetch runs, and compute the current-week cursor.

    Returns None if any precondition for gap analysis is not met:
    plan hasn't started, no duration, no plan_data, or (when
    ``require_runs`` is True) no logged runs yet.
    """
    start_date = _to_date(plan.start_date)
    if not start_date:
        return None

    total_weeks = plan.weeks_duration or 0
    if total_weeks == 0:
        return None

    if (date.today() - start_date).days < 0:
        return None  # plan hasn't started

    current_week = compute_current_week(
        start_date, date.today(), total_weeks=total_weeks
    )
    if current_week < 1:
        return None

    plan_data = plan.plan_data if plan.plan_data else []
    if not plan_data:
        return None

    runs = (
        db.query(RunLog)
        .filter(
            RunLog.user_id == user_id,
            RunLog.date >= datetime.combine(start_date, datetime.min.time()),
        )
        .order_by(RunLog.date.asc())
        .all()
    )
    if require_runs and not runs:
        return None

    return _PlanGapContext(plan, plan_data, start_date, total_weeks, current_week, runs)


def _bucket_runs_by_week(
    runs: List[RunLog], start_date: date, current_week: int
) -> tuple[Dict[int, float], Dict[int, float]]:
    """Group runs into (week_num → total_km) and (week_num → longest_km).

    Runs before plan start or after the current week are dropped.
    """
    weekly_km: Dict[int, float] = {}
    weekly_longest: Dict[int, float] = {}

    for run in runs:
        run_date = _to_date(run.date)
        if not run_date:
            continue
        delta = (run_date - start_date).days
        if delta < 0:
            continue
        wk = delta // 7 + 1
        if wk > current_week:
            continue
        weekly_km[wk] = weekly_km.get(wk, 0) + run.distance_km
        weekly_longest[wk] = max(weekly_longest.get(wk, 0), run.distance_km)

    return weekly_km, weekly_longest


def _weekly_breakpoint(
    wk_data: dict, weekly_km: Dict[int, float], weekly_longest: Dict[int, float]
) -> dict:
    """Build one per-week trend-chart datapoint."""
    wk_num = wk_data.get("week", 0)
    planned_km = wk_data.get("total_km", 0)
    actual_km = weekly_km.get(wk_num, 0)

    planned_long = 0.0
    for wo in wk_data.get("daily_workouts", []):
        if wo.get("type") == "long":
            planned_long = max(planned_long, wo.get("distance", 0))
    actual_long = weekly_longest.get(wk_num, 0)

    volume_pct = round(actual_km / planned_km * 100, 1) if planned_km > 0 else 0
    long_run_pct = round(actual_long / planned_long * 100, 1) if planned_long > 0 else 0

    return {
        "week": wk_num,
        "volume_pct": min(150, volume_pct),
        "long_run_pct": min(150, long_run_pct),
        "actual_km": round(actual_km, 1),
        "planned_km": round(planned_km, 1),
    }
