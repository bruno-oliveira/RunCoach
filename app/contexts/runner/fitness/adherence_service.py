"""Workout adherence heatmap computation."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.training.plan_calendar import compute_current_week
from app.models import DailyWorkout, TrainingPlan, WeeklyPlan
from app.models.run_log import RunLog
from app.utils import to_date as _to_date


def compute_adherence_heatmap(
    plan: TrainingPlan,
    user_id: str,
    db: Session,
) -> dict:
    """Build a workout-type adherence heatmap grid for a plan.

    Returns a dict with keys: available, workout_types, grid, current_week, total_weeks.
    """
    start_date = _to_date(plan.start_date)
    if not start_date:
        return {"available": False, "reason": "Plan has no start date."}

    today = date.today()
    total_weeks = plan.weeks_duration or 0
    current_week = compute_current_week(
        start_date, today, total_weeks=total_weeks, pre_start=1
    )

    plan_data = plan.plan_data if plan.plan_data else []

    runs = (
        db.query(RunLog)
        .filter(
            RunLog.user_id == user_id,
            RunLog.training_plan_id == plan.id,
        )
        .all()
    )
    linked_workout_ids = {r.daily_workout_id for r in runs if r.daily_workout_id}

    workouts_raw = (
        db.query(DailyWorkout, WeeklyPlan.week_number)
        .join(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan.id)
        .all()
    )
    workouts_by_week: dict[int, list] = {}
    for workout, wk in workouts_raw:
        workouts_by_week.setdefault(wk, []).append(workout)

    workout_types: set[str] = set()
    for week_data in plan_data:
        for wo in week_data.get("daily_workouts", []):
            wo_type = wo.get("type", "unknown")
            if wo_type not in ("rest", "recovery"):
                workout_types.add(wo_type)

    sorted_types = sorted(workout_types)

    grid = []
    for week_data in plan_data:
        wk_num = week_data.get("week", 0)
        row: dict = {"week": wk_num, "cells": {}}
        for wo_type in sorted_types:
            if wk_num > current_week:
                row["cells"][wo_type] = "future"
            else:
                row["cells"][wo_type] = "skipped"

        for workout in workouts_by_week.get(wk_num, []):
            wo_type = workout.workout_type
            if wo_type in ("rest", "recovery") or wo_type not in sorted_types:
                continue
            if workout.id in linked_workout_ids:
                row["cells"][wo_type] = "completed"
            elif wk_num <= current_week:
                week_start = start_date + timedelta(weeks=wk_num - 1)
                week_end = week_start + timedelta(days=7)
                week_runs = [
                    r
                    for r in runs
                    if r.date and week_start <= _to_date(r.date) < week_end
                ]
                if week_runs:
                    row["cells"][wo_type] = "rescheduled"

        grid.append(row)

    return {
        "available": True,
        "workout_types": sorted_types,
        "grid": grid,
        "current_week": current_week,
        "total_weeks": total_weeks,
    }
