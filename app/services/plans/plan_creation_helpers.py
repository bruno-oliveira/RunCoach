"""Plan persistence helpers — plan core, weekly workouts, HR zones, nutrition, race protocol."""

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.nutrition.nutrition_engine import NutritionEngine
from app.core.race.race_protocol_generator import generate_race_protocol
from app.core.training.vdot_calculator import VDOTCalculator
from app.models import DailyWorkout, TrainingPlan, User, WeeklyPlan
from app.schemas import PlanRequest
from app.services.fitness.hr_zone_service import HRZoneService
from app.utils import parse_race_time_to_seconds

logger = logging.getLogger(__name__)


def persist_plan_core(
    plan_request: PlanRequest,
    user: User,
    plan_data: list[dict],
    db: Session,
) -> TrainingPlan:
    training_plan = TrainingPlan(
        user_id=user.id,
        current_weekly_km=plan_request.current_km,
        target_distance=str(plan_request.target_distance),
        weeks_duration=plan_request.weeks,
        max_runs_per_week=plan_request.max_runs_per_week,
        plan_data=plan_data,
        body_weight_kg=plan_request.body_weight_kg,
        recent_race_distance_km=plan_request.recent_race_distance_km,
        recent_race_time_seconds=(
            parse_race_time_to_seconds(plan_request.recent_race_time)
            if plan_request.recent_race_time
            else None
        ),
        vdot=plan_request.vdot,
        goal_time=plan_request.goal_time,
        goal_pace=plan_request.goal_pace_min_km,
        current_pace=plan_request.current_pace_min_km,
        is_trail=plan_request.is_trail,
        target_elevation_gain_m=plan_request.target_elevation_gain_m,
    )
    db.add(training_plan)
    db.flush()
    return training_plan


def persist_weekly_workouts(
    training_plan: TrainingPlan,
    plan_data: list[dict],
    db: Session,
) -> None:
    for week_data in plan_data:
        weekly_plan = WeeklyPlan(
            training_plan_id=training_plan.id,
            week_number=week_data["week"],
            total_km=week_data["total_km"],
            workout_types=week_data.get("workout_distribution", {}),
        )
        db.add(weekly_plan)
        db.flush()

        for day_workout in week_data.get("daily_workouts", []):
            dist = day_workout.get("distance", 0)
            daily_workout = DailyWorkout(
                weekly_plan_id=weekly_plan.id,
                day_of_week=day_workout["day"],
                workout_type=day_workout["type"],
                distance_km=dist,
                intensity=day_workout.get("intensity", "low"),
                notes=day_workout.get("description", day_workout.get("notes", "")),
                coaching_rationale=day_workout.get("coaching_rationale"),
                baseline_distance_km=dist,
            )
            db.add(daily_workout)


def attach_hr_zones(
    training_plan: TrainingPlan,
    user: User,
    plan_data: list[dict],
    db: Session,
) -> None:
    try:
        zones = HRZoneService.compute_and_store_zones(training_plan, user, db)
        HRZoneService.inject_hr_zones_into_plan_data(plan_data, zones)
        for week_data in plan_data:
            week_num = week_data.get("week")
            for workout in week_data.get("daily_workouts", []):
                hr_target = workout.get("hr_zone_target")
                key_wk_id = workout.get("key_workout_id")
                if hr_target is None and key_wk_id is None:
                    continue
                dw = (
                    db.query(DailyWorkout)
                    .join(WeeklyPlan)
                    .filter(
                        WeeklyPlan.training_plan_id == training_plan.id,
                        WeeklyPlan.week_number == week_num,
                        DailyWorkout.day_of_week == workout.get("day"),
                    )
                    .first()
                )
                if dw:
                    if hr_target is not None:
                        dw.hr_zone_target = hr_target
                    if key_wk_id is not None:
                        dw.key_workout_id = key_wk_id
        training_plan.plan_data = plan_data
    except Exception as e:
        logger.warning(
            f"HR zone injection failed for plan {training_plan.id}: {e}"
        )


def attach_nutrition(
    training_plan: TrainingPlan,
    plan_request: PlanRequest,
    plan_data: list[dict],
    nutrition_engine: NutritionEngine,
) -> None:
    nutrition_plan = nutrition_engine.generate_weekly_meal_plan(
        plan_request.current_km,
        plan_request.target_distance,
        body_weight=plan_request.body_weight_kg,
    )
    training_plan.nutrition_plan_data = nutrition_plan

    nutrition_phases = nutrition_engine.generate_phased_nutrition_plan(
        plan_data,
        plan_request.current_km,
        plan_request.target_distance,
        body_weight_kg=plan_request.body_weight_kg,
    )
    training_plan.nutrition_phases_data = nutrition_phases


def attach_race_protocol(
    training_plan: TrainingPlan,
    plan_request: PlanRequest,
) -> None:
    goal_pace = plan_request.goal_pace_min_km or goal_pace_from_vdot(
        plan_request.vdot, plan_request.target_distance
    )
    race_protocol = generate_race_protocol(
        plan_request.target_distance,
        goal_pace,
    )
    training_plan.race_protocol_data = race_protocol


def goal_pace_from_vdot(
    vdot: Optional[float],
    target_distance: float,
) -> Optional[float]:
    if not vdot:
        return None
    zones = VDOTCalculator.get_pace_zones(vdot)
    if not zones or not all(k in zones for k in ("I", "T", "M")):
        return None
    if target_distance <= 5.0:
        return zones["I"]["pace_min_km"]
    if target_distance <= 10.0:
        return zones["T"]["pace_min_km"]
    if target_distance <= 21.1:
        return zones["M"]["pace_min_km"] * 0.95
    return zones["M"]["pace_min_km"]
