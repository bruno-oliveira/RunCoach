"""Plan persistence helpers — plan core, weekly workouts, HR zones, nutrition, race protocol."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from app.core.race.race_protocol_generator import generate_race_protocol
from app.core.training.road_profile import classify_road
from app.core.training.vdot_calculator import VDOTCalculator
from app.models import DailyWorkout, RunLog, TrainingPlan, User, WeeklyPlan
from app.schemas import PlanRequest
from app.utils import parse_race_time_to_seconds

# Half a minute of tolerance when matching an already-persisted race effort, so
# regenerating a plan with the same stated race never stacks up duplicate runs.
_RACE_DUP_SECONDS_TOLERANCE = 30.0
# The stated race is a genuine maximal effort; label it so the VDOT weighting
# (``_effort_weight``) and race-calibration paths treat it as one.
_RACE_EFFORT_CLASS = "race_effort"

if TYPE_CHECKING:
    # Type-only: the engine is injected by the caller (PlanService.create_plan),
    # so the plan context does not depend on the nutrition context at runtime.
    from app.application.ports import NutritionEngine

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
        training_terrain=plan_request.resolved_training_terrain(),
        is_backyard=plan_request.is_backyard,
        backyard_target_loops=plan_request.backyard_target_loops,
        backyard_loop_km=(
            plan_request.backyard_loop_km if plan_request.is_backyard else None
        ),
        backyard_loop_elevation_gain_m=(
            plan_request.backyard_loop_elevation_gain_m
            if plan_request.is_backyard
            else None
        ),
    )
    db.add(training_plan)
    db.flush()
    return training_plan


def persist_race_effort_run(
    plan_request: PlanRequest,
    user: User,
    db: Session,
) -> None:
    """Persist the onboarding "recent race" as a race-effort ``RunLog``.

    The signup form captures a recent hard effort ("5 km in 22:30") only to
    VDOT-pace the plan being generated, then discards it -- throwing away the
    single most trustworthy fitness number the runner has handed us. Without it
    persisted, ``get_best_recent_vdot`` (and through it the pace<->HR-at-
    threshold LTHR estimate and every race prediction) has to infer fitness
    passively from whatever runs happen to be logged.

    Storing it as a ``race_effort`` run folds the stated number into all of that
    machinery with no special-casing. It carries no heart rate (so it never
    lands in the HR-zone trend) and a ``race_effort`` class (so it never
    pollutes the easy-pace trend), and it is idempotent -- regenerating a plan
    with the same race does not stack up duplicates.
    """
    distance_km = plan_request.recent_race_distance_km
    vdot = plan_request.vdot
    if not distance_km or distance_km <= 0 or not vdot:
        return

    seconds = (
        parse_race_time_to_seconds(plan_request.recent_race_time)
        if plan_request.recent_race_time
        else None
    )
    if not seconds or seconds <= 0:
        return

    duration_minutes = seconds / 60.0
    if _race_effort_already_logged(user.id, distance_km, duration_minutes, db):
        return

    db.add(
        RunLog(
            user_id=user.id,
            distance_km=distance_km,
            duration_minutes=duration_minutes,
            avg_pace_min_km=(
                plan_request.current_pace_min_km or duration_minutes / distance_km
            ),
            workout_type="race",
            effort_class=_RACE_EFFORT_CLASS,
            vdot=vdot,
            notes="Recent race entered when generating a plan.",
        )
    )


def _race_effort_already_logged(
    user_id: str,
    distance_km: float,
    duration_minutes: float,
    db: Session,
) -> bool:
    """Whether a matching race-effort run is already logged for this user."""
    tolerance_min = _RACE_DUP_SECONDS_TOLERANCE / 60.0
    existing = (
        db.query(RunLog.id)
        .filter(
            RunLog.user_id == user_id,
            RunLog.workout_type == "race",
            RunLog.distance_km >= distance_km - 0.1,
            RunLog.distance_km <= distance_km + 0.1,
            RunLog.duration_minutes >= duration_minutes - tolerance_min,
            RunLog.duration_minutes <= duration_minutes + tolerance_min,
        )
        .first()
    )
    return existing is not None


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
    # Local import keeps the plan context free of a static edge to the runner
    # context's HR-zone service (cross-context runtime call during creation).
    from app.application.ports import HRZoneService

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
        logger.warning(f"HR zone injection failed for plan {training_plan.id}: {e}")


def attach_nutrition(
    training_plan: TrainingPlan,
    plan_request: PlanRequest,
    plan_data: list[dict],
    nutrition_engine: NutritionEngine,
) -> None:
    trail_kwargs = {
        "is_trail": plan_request.is_trail,
        "target_elevation_gain_m": plan_request.target_elevation_gain_m or 0.0,
    }
    nutrition_plan = nutrition_engine.generate_weekly_meal_plan(
        plan_request.current_km,
        plan_request.target_distance,
        body_weight=plan_request.body_weight_kg,
        **trail_kwargs,
    )
    training_plan.nutrition_plan_data = nutrition_plan

    nutrition_phases = nutrition_engine.generate_phased_nutrition_plan(
        plan_data,
        plan_request.current_km,
        plan_request.target_distance,
        body_weight_kg=plan_request.body_weight_kg,
        **trail_kwargs,
    )
    training_plan.nutrition_phases_data = nutrition_phases


def attach_race_protocol(
    training_plan: TrainingPlan,
    plan_request: PlanRequest,
) -> None:
    goal_pace = plan_request.goal_pace_min_km or goal_pace_from_vdot(
        plan_request.vdot, plan_request.target_distance
    )
    trail_profile = None
    if plan_request.is_trail:
        from app.core.training.trail_profile import classify_trail

        trail_profile = classify_trail(
            plan_request.target_distance,
            plan_request.target_elevation_gain_m or 0.0,
        )
    # A backyard's "goal pace" is its loop budget, not a VDOT prediction over
    # the projected distance — the protocol reads it straight off the profile.
    backyard_profile = plan_request.backyard_profile()
    race_protocol = generate_race_protocol(
        plan_request.target_distance,
        goal_pace,
        trail_profile=trail_profile,
        backyard_profile=backyard_profile,
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
    band = classify_road(target_distance)
    if band == "5k":
        return zones["I"]["pace_min_km"]
    if band == "10k":
        return zones["T"]["pace_min_km"]
    if band == "half":
        return zones["M"]["pace_min_km"] * 0.95
    return zones["M"]["pace_min_km"]
