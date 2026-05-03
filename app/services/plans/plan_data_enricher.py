"""DB ID enrichment, nutrition format conversion, and logged-run mapping."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, WeeklyPlan

logger = logging.getLogger(__name__)


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
