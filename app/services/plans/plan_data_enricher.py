"""DB ID enrichment, nutrition format conversion, and logged-run mapping."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.training.key_workout_data import WORKOUTS
from app.core.training.key_workout_library import (
    _KEY_WORKOUT_MIN_DISTANCE_KM,
    reconcile_key_workout_text,
)
from app.core.training.key_workout_parser import parse_key_workout_steps
from app.core.training.workout_steps import (
    _compute_distance_from_steps,
    _parse_pace_str_to_min_per_km,
)
from app.models import DailyWorkout, RunLog, WeeklyPlan

logger = logging.getLogger(__name__)

_DURATION_HINT_THRESHOLD_KM = 3.0
_DEFAULT_PACE_MIN_PER_KM_BY_ZONE = {
    "E": 8.0,
    "T": 6.5,
    "I": 5.5,
    "M": 6.0,
    "R": 5.0,
    "10K": 6.0,
}
_DEFAULT_PACE_MIN_PER_KM_BY_TYPE = {
    "easy": 7.0,
    "long": 7.0,
    "tempo": 5.5,
    "interval": 4.8,
    "hill": 5.0,
}
_KEY_DEFAULT_ZONE_BY_ID = {
    w["id"]: w.get("pace_zone")
    for w in WORKOUTS
}


def _has_volume_steps(steps: list[dict]) -> bool:
    for step in steps:
        if step.get("kind") in {"warmup", "cooldown", "rest"}:
            continue
        if step.get("distance_m") or step.get("duration_s"):
            return True
    return False


def _repair_key_workout_steps(workout: dict[str, Any]) -> None:
    key_id = workout.get("key_workout_id")
    if not key_id:
        return

    distance_km = workout.get("distance", 0) or 0
    min_km = _KEY_WORKOUT_MIN_DISTANCE_KM.get(key_id, 0)
    if min_km > 0 and distance_km < min_km:
        distance_km = min_km
        workout["distance"] = distance_km

    reconcile_key_workout_text(workout)

    steps = workout.get("steps")
    if isinstance(steps, list) and _has_volume_steps(steps):
        return

    structure = workout.get("structure")
    if not structure:
        return

    workout_type = workout.get("type", "interval")
    default_zone = _KEY_DEFAULT_ZONE_BY_ID.get(key_id)
    workout["steps"] = parse_key_workout_steps(
        structure,
        workout_type=workout_type,
        default_zone=default_zone,
        total_distance_km=distance_km,
    )


def _estimate_duration_min_from_steps(
    steps: list[dict],
    workout_type: str,
) -> int | None:
    total_seconds = 0.0
    for step in steps:
        try:
            repeat = int(step.get("repeat", 1) or 1)
        except (TypeError, ValueError):
            repeat = 1
        repeat = max(1, repeat)

        duration_s = step.get("duration_s")
        if duration_s:
            total_seconds += float(duration_s) * repeat
            continue

        distance_m = step.get("distance_m")
        if not distance_m:
            continue

        pace_min_per_km = _parse_pace_str_to_min_per_km(
            step.get("pace_str"),
            step.get("pace_zone"),
        )
        if not pace_min_per_km:
            pace_min_per_km = _DEFAULT_PACE_MIN_PER_KM_BY_ZONE.get(
                step.get("pace_zone")
            ) or _DEFAULT_PACE_MIN_PER_KM_BY_TYPE.get(workout_type, 7.0)

        total_seconds += (float(distance_m) / 1000.0) * pace_min_per_km * 60.0 * repeat

    if total_seconds <= 0:
        return None
    return max(1, int(round(total_seconds / 60.0)))


def enrich_plan_data_with_ids(
    plan_data: list[dict],
    training_plan_id: str,
    db: Session,
) -> list[dict]:
    rows = (
        db.query(
            WeeklyPlan.week_number,
            DailyWorkout.day_of_week,
            DailyWorkout.id,
            DailyWorkout.baseline_distance_km,
        )
        .join(DailyWorkout, DailyWorkout.weekly_plan_id == WeeklyPlan.id)
        .filter(WeeklyPlan.training_plan_id == training_plan_id)
        .all()
    )
    id_map = {(wn, dow): wid for wn, dow, wid, _ in rows}
    baseline_map = {(wn, dow): bl for wn, dow, _, bl in rows}

    for week in plan_data:
        week_num = week.get("week")
        for workout in week.get("daily_workouts", []):
            key = (week_num, workout.get("day"))
            workout["id"] = id_map.get(key)
            bl = baseline_map.get(key)

            _repair_key_workout_steps(workout)

            steps = workout.get("steps")
            if not isinstance(steps, list) or not steps:
                continue

            steps_distance_km = _compute_distance_from_steps(steps)
            if steps_distance_km > 0:
                rounded_steps_km = round(steps_distance_km, 1)
                current_distance = workout.get("distance", 0) or 0
                if current_distance <= 0 or abs(current_distance - rounded_steps_km) > 0.2:
                    workout["distance"] = rounded_steps_km

            distance = workout.get("distance", 0) or 0
            if 0 < distance < _DURATION_HINT_THRESHOLD_KM:
                est_min = _estimate_duration_min_from_steps(
                    steps,
                    workout.get("type", "easy"),
                )
                if est_min is not None:
                    workout["duration_min"] = est_min

            if bl is not None and bl != workout.get("distance"):
                workout["baseline_distance"] = bl

    return plan_data


def nutrition_for_template(nutrition_plan_data) -> dict[str, Any]:
    if not nutrition_plan_data:
        return {}

    nutrition_plan = nutrition_plan_data

    if isinstance(nutrition_plan, list):
        if not nutrition_plan:
            return {}
        first_day = nutrition_plan[0]
        if not isinstance(first_day, dict):
            return {}
        targets = first_day.get("nutrition_targets", {})
        if not isinstance(targets, dict):
            targets = {}
        blueprint: dict[str, Any] = {
            "daily_calories": targets.get("calories", 0),
            "protein_g": targets.get("protein", 0),
            "carbs_g": targets.get("carbs", 0),
            "fats_g": targets.get("fat", 0),
            "meal_suggestions": {},
            "general_tips": first_day.get("nutrition_tips", []),
            "hydration_guide": {
                "daily_target": "2000ml",
                "pre_run": "300-500ml, 2 hours before",
                "during_run": "200-400ml per hour",
                "post_run": "150% of fluid lost",
                "tips": ["Stay hydrated throughout the day"],
            },
        }

        for daily_plan in nutrition_plan:
            if not isinstance(daily_plan, dict):
                continue
            meals = daily_plan.get("meals", {})
            if not isinstance(meals, dict):
                continue
            for meal_type, meal_data in meals.items():
                if meal_type not in blueprint["meal_suggestions"]:
                    blueprint["meal_suggestions"][meal_type] = []
                blueprint["meal_suggestions"][meal_type].append(meal_data)

        return blueprint

    if not isinstance(nutrition_plan, dict):
        return {}

    targets = nutrition_plan.get("nutrition_targets", {})
    if not isinstance(targets, dict):
        targets = {}

    meal_options = nutrition_plan.get("meal_options", {})
    if not isinstance(meal_options, dict):
        meal_options = {}

    general_tips = nutrition_plan.get("general_tips", [])
    if not isinstance(general_tips, list):
        general_tips = []

    hydration_guide = nutrition_plan.get("hydration_guide", {})
    if not isinstance(hydration_guide, dict):
        hydration_guide = {}

    return {
        "daily_calories": targets.get("calories", 0),
        "protein_g": targets.get("protein", 0),
        "carbs_g": targets.get("carbs", 0),
        "fats_g": targets.get("fat", 0),
        "meal_suggestions": meal_options,
        "general_tips": general_tips,
        "hydration_guide": hydration_guide,
        "pre_run_meal": nutrition_plan.get("pre_run_meal"),
        "post_run_meal": nutrition_plan.get("post_run_meal"),
    }


def get_logged_runs_map(
    training_plan_id: str,
    db: Session,
) -> tuple[dict, list]:
    logged_runs = (
        db.query(RunLog)
        .filter(RunLog.training_plan_id == training_plan_id)
        .order_by(RunLog.date.desc())
        .all()
    )
    runs_map = {}
    for run in logged_runs:
        if run.daily_workout_id and run.daily_workout_id not in runs_map:
            runs_map[run.daily_workout_id] = run
    return runs_map, logged_runs


def get_feedback_map(logged_runs: list, db: Session) -> dict[str, Any]:
    from app.models.run_feedback import RunFeedback

    if not logged_runs:
        return {}
    try:
        run_ids = [r.id for r in logged_runs]
        feedbacks = (
            db.query(RunFeedback)
            .filter(RunFeedback.run_log_id.in_(run_ids))
            .all()
        )
        return {fb.run_log_id: fb for fb in feedbacks}
    except Exception as e:
        logger.warning(f"Could not load feedback: {e}")
        return {}
