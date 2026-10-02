"""What the runner's plan already has on a given day.

A single run is prescribed alongside whatever plan is in progress, so two
things need to know what that plan holds on the same date: the form (to say
"your plan already has this run today" before a duplicate is created) and the
claim (to decide whether an imported activity was the single run or the planned
session). Both read it from here so they cannot disagree about what was
planned.

Read from the ``daily_workouts`` rows rather than ``plan_data``: those rows are
what the run mapper matches against, and their ids are what the day page links
to.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, TrainingPlan, WeeklyPlan
from app.utils import to_date

_NOT_A_RUN = ("rest", "strength")


@dataclass(frozen=True)
class PlannedRun:
    """One planned running session, placed on its calendar date."""

    on_date: date
    plan_id: str
    workout_id: str
    workout_type: str
    distance_km: float
    # Already matched to a logged run — it is done, so it competes for nothing.
    completed: bool


def planned_runs_between(
    user_id: str, db: Session, start: date, end: date
) -> list[PlannedRun]:
    """The runner's planned runs dated within ``[start, end]``, in date order."""
    rows = (
        db.query(DailyWorkout, WeeklyPlan.week_number, TrainingPlan)
        .join(WeeklyPlan, DailyWorkout.weekly_plan_id == WeeklyPlan.id)
        .join(TrainingPlan, WeeklyPlan.training_plan_id == TrainingPlan.id)
        .filter(TrainingPlan.user_id == user_id, TrainingPlan.start_date.isnot(None))
        .all()
    )

    planned: list[tuple[DailyWorkout, TrainingPlan, date]] = []
    for workout, week_number, plan in rows:
        plan_start = to_date(plan.start_date)
        # Without all three there is no date to put the session on.
        if plan_start is None or not week_number or not workout.day_of_week:
            continue
        if workout.workout_type in _NOT_A_RUN or not workout.distance_km:
            continue
        on_date = plan_start + timedelta(
            weeks=week_number - 1, days=workout.day_of_week - 1
        )
        if start <= on_date <= end:
            planned.append((workout, plan, on_date))

    if not planned:
        return []
    done_ids = {
        workout_id
        for (workout_id,) in db.query(RunLog.daily_workout_id).filter(
            RunLog.daily_workout_id.in_([workout.id for workout, _, _ in planned])
        )
    }
    return sorted(
        (
            PlannedRun(
                on_date=on_date,
                plan_id=plan.id,
                workout_id=workout.id,
                workout_type=workout.workout_type or "",
                distance_km=float(workout.distance_km or 0.0),
                completed=workout.id in done_ids,
            )
            for workout, plan, on_date in planned
        ),
        key=lambda run: run.on_date,
    )
