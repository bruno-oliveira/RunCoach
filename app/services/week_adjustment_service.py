"""Domain logic for per-week plan overrides (skip bump, reduce, scale, etc.)."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import DailyWorkout, TrainingPlan, WeeklyPlan


def get_week_workouts(plan_id: str, week_number: int, db: Session):
    """Fetch weekly plan and its workouts."""
    weekly_plan = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number == week_number,
        )
        .first()
    )
    if not weekly_plan:
        return None, []
    workouts = (
        db.query(DailyWorkout)
        .filter(DailyWorkout.weekly_plan_id == weekly_plan.id)
        .all()
    )
    return weekly_plan, workouts


def sync_plan_data_distances(week_data: dict, workouts: list) -> None:
    """Sync plan_data JSON distances from DB workout objects."""
    for wo_data in week_data.get("daily_workouts", []):
        for db_wo in workouts:
            if db_wo.day_of_week == wo_data.get("day"):
                wo_data["distance"] = db_wo.distance_km
    week_data["total_km"] = round(
        sum(wo.distance_km for wo in workouts if wo.distance_km), 1
    )


def apply_week_action(
    action: str,
    training_plan: TrainingPlan,
    plan_data: list,
    week_data: dict,
    week_number: int,
    plan_id: str,
    db: Session,
) -> None:
    """Dispatch and execute a per-week override action."""
    if action == "skip_bump":
        _action_skip_bump(week_data, plan_id, week_number, db)
    elif action == "reduce_30":
        _action_reduce_30(plan_data, plan_id, week_number, db)
    elif action == "bump":
        _action_bump(week_data, training_plan, plan_id, week_number, db)
    elif action == "ease_deficit":
        _action_scale_week(week_data, plan_id, week_number, 0.85, db)
    elif action == "extend_long_run":
        _action_extend_long_run(week_data, plan_id, week_number, db)
    elif action == "reset_week":
        _action_reset_week(week_data, plan_id, week_number, db)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


def _action_skip_bump(week_data, plan_id, week_number, db):
    _, workouts = get_week_workouts(plan_id, week_number, db)
    for wo in workouts:
        if wo.baseline_distance_km:
            wo.distance_km = wo.baseline_distance_km
    sync_plan_data_distances(week_data, workouts)


def _action_reduce_30(plan_data, plan_id, week_number, db):
    factor = 0.7
    for target_week in range(week_number, min(week_number + 2, len(plan_data) + 1)):
        tw_data = next((w for w in plan_data if w.get("week") == target_week), None)
        if not tw_data:
            continue
        _, workouts = get_week_workouts(plan_id, target_week, db)
        for wo in workouts:
            if wo.distance_km:
                wo.distance_km = round(wo.distance_km * factor, 1)
        for wo_data in tw_data.get("daily_workouts", []):
            if "distance" in wo_data:
                wo_data["distance"] = round(wo_data["distance"] * factor, 1)
        tw_data["total_km"] = round(
            sum(wo.distance_km for wo in workouts if wo.distance_km), 1
        )


def _action_bump(week_data, training_plan, plan_id, week_number, db):
    multiplier = training_plan.adjustment_multiplier or 1.08
    _, workouts = get_week_workouts(plan_id, week_number, db)
    for wo in workouts:
        if wo.distance_km:
            if not wo.baseline_distance_km:
                wo.baseline_distance_km = wo.distance_km
            wo.distance_km = round(wo.distance_km * multiplier, 1)
    for wo_data in week_data.get("daily_workouts", []):
        if "distance" in wo_data:
            wo_data["distance"] = round(wo_data["distance"] * multiplier, 1)
    week_data["total_km"] = round(
        sum(wo.distance_km for wo in workouts if wo.distance_km), 1
    )


def _action_scale_week(week_data, plan_id, week_number, factor, db):
    _, workouts = get_week_workouts(plan_id, week_number, db)
    for wo in workouts:
        if wo.distance_km:
            if not wo.baseline_distance_km:
                wo.baseline_distance_km = wo.distance_km
            wo.distance_km = round(wo.distance_km * factor, 1)
    for wo_data in week_data.get("daily_workouts", []):
        if "distance" in wo_data:
            wo_data["distance"] = round(wo_data["distance"] * factor, 1)
    week_data["total_km"] = round(
        sum(wo.distance_km for wo in workouts if wo.distance_km), 1
    )


def _action_extend_long_run(week_data, plan_id, week_number, db):
    _, workouts = get_week_workouts(plan_id, week_number, db)
    long_wo = next((wo for wo in workouts if wo.workout_type == "long"), None)
    if long_wo and long_wo.distance_km:
        if not long_wo.baseline_distance_km:
            long_wo.baseline_distance_km = long_wo.distance_km
        long_wo.distance_km = round(long_wo.distance_km + 2, 1)
    for wo_data in week_data.get("daily_workouts", []):
        if wo_data.get("type") == "long" and "distance" in wo_data:
            wo_data["distance"] = round(wo_data["distance"] + 2, 1)
            break
    week_data["total_km"] = round(
        sum(wo.distance_km for wo in workouts if wo.distance_km), 1
    )


def _action_reset_week(week_data, plan_id, week_number, db):
    _, workouts = get_week_workouts(plan_id, week_number, db)
    for wo in workouts:
        if wo.baseline_distance_km is not None:
            wo.distance_km = wo.baseline_distance_km
            wo.baseline_distance_km = None
    sync_plan_data_distances(week_data, workouts)
