"""How much of a plan the runner has run — the shared page's progress block.

Every run in the plan's window counts, matched to a planned day or not, the
same scope the Coach page uses for the goal.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.time_utils import local_today, to_date
from app.models import RunLog, TrainingPlan

_NOT_A_RUN = ("rest", "recovery")


@dataclass(frozen=True)
class _PlanWindow:
    """The plan's weeks on the calendar: from its start, ``weeks`` long."""

    start: date
    weeks: int

    @property
    def end(self) -> date:
        return self.start + timedelta(weeks=self.weeks)

    def week_index(self, day: date) -> Optional[int]:
        """0-based week ``day`` falls in, or ``None`` outside the plan."""
        index = (day - self.start).days // 7
        return index if 0 <= index < self.weeks else None


def _plan_window(plan: TrainingPlan) -> Optional[_PlanWindow]:
    """The plan's window, starting when the row was created if it has no start.

    Neither column is NOT NULL, so both can be absent on a row written outside
    the ORM; there is then no window, rather than a guessed one.
    """
    start = to_date(plan.start_date or plan.created_at)
    if start is None:
        return None
    return _PlanWindow(start=start, weeks=len(plan.plan_data or []))


def _runs_in(db: Session, user_id: str, window: _PlanWindow) -> list[RunLog]:
    return (
        db.query(RunLog)
        .filter(
            RunLog.user_id == user_id,
            RunLog.date >= datetime.combine(window.start, datetime.min.time()),
            RunLog.date < datetime.combine(window.end, datetime.min.time()),
        )
        .order_by(RunLog.date.asc())
        .all()
    )


def _weekly_km(runs: list[RunLog], window: _PlanWindow) -> list[float]:
    weekly = [0.0] * window.weeks
    for run in runs:
        day = to_date(run.date)
        index = window.week_index(day) if day else None
        if index is not None:
            weekly[index] += run.distance_km or 0
    return [round(km, 1) for km in weekly]


def _streak_days(runs: list[RunLog], today: date) -> int:
    run_days = {to_date(run.date) for run in runs}
    streak = 0
    while today - timedelta(days=streak) in run_days:
        streak += 1
    return streak


def _planned_runs(plan: TrainingPlan) -> int:
    return sum(
        1
        for week in plan.plan_data or []
        for workout in week.get("daily_workouts", [])
        if workout.get("type") not in _NOT_A_RUN
    )


def get_plan_progress(db: Session, plan: TrainingPlan) -> Dict[str, Any]:
    """Runs done against runs planned, km logged per week, and the current streak."""
    window = _plan_window(plan)
    if window is None:
        return {"available": False, "reason": "Plan has no start date."}
    runs = _runs_in(db, plan.user_id, window) if plan.user_id else []
    planned = _planned_runs(plan)
    return {
        "actual_weekly_km": _weekly_km(runs, window),
        "completed_count": len(runs),
        "planned_count": planned,
        "completion_pct": round(len(runs) / planned * 100) if planned else 0,
        "streak_days": _streak_days(runs, local_today()),
        "total_km_logged": round(sum(run.distance_km or 0 for run in runs), 1),
    }
