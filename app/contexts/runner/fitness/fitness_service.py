"""Fitness plan creation and business logic."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from app.contexts.runner.fitness.hr_zone_service import HRZoneService
from app.core.training.vdot_calculator import VDOTCalculator
from app.models import DailyWorkout, TrainingPlan, User, WeeklyPlan
from app.schemas import FitnessPlanRequest
from app.utils import parse_race_time_to_seconds

if TYPE_CHECKING:
    # Type-only: the engine is injected by the caller.
    from app.application.ports import NutritionEngine

logger = logging.getLogger(__name__)


class FitnessService:
    """Encapsulates fitness plan lifecycle operations."""

    def __init__(self, db: Session) -> None:
        # Deferred imports keep the runner context free of static edges into the
        # plan context (cross-context orchestration happens at call time).
        from app.application.ports import (
            FitnessPlanGenerator,
            PlanService,
        )

        self.db = db
        self._plan_service = PlanService()
        self._generator = FitnessPlanGenerator()

    def create_fitness_plan(
        self,
        user: User,
        plan_request: FitnessPlanRequest,
        nutrition_engine: NutritionEngine,
    ) -> tuple[TrainingPlan, list[dict]]:
        """Create a fitness-focused training plan."""
        existing = self._find_duplicate(plan_request, user.id)
        if existing:
            logger.info(
                f"Duplicate fitness plan detected for user {user.id} — returning existing plan {existing.id}"
            )
            return existing, existing.plan_data if existing.plan_data else []

        vdot = plan_request.vdot
        if (
            not vdot
            and plan_request.recent_race_distance_km
            and plan_request.recent_race_time
        ):
            seconds = VDOTCalculator.parse_time_to_seconds(
                plan_request.recent_race_time
            )
            if seconds:
                vdot = VDOTCalculator.calculate_vdot(
                    plan_request.recent_race_distance_km, seconds
                )

        plan_result = self._generator.generate_plan(
            current_weekly_km=plan_request.current_km,
            weeks=plan_request.weeks,
            runs_per_week=plan_request.runs_per_week,
            vdot=vdot,
            max_heart_rate=plan_request.max_heart_rate,
            focus_area=plan_request.focus_area,
            focus_distance=plan_request.focus_distance,
        )

        plan_data = plan_result["weekly_plans"]

        try:
            training_plan = self._persist_plan_core(
                plan_request, user, plan_data, plan_result
            )
            self._persist_weekly_workouts(training_plan, plan_data)
            self._attach_hr_zones(training_plan, user, plan_data, plan_result)
            self._attach_nutrition(
                training_plan, plan_request, plan_data, nutrition_engine
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return training_plan, plan_data

    def _find_duplicate(
        self, plan_request: FitnessPlanRequest, user_id: str
    ) -> Optional[TrainingPlan]:
        """Check for duplicate fitness plans."""
        race_time_seconds = (
            parse_race_time_to_seconds(plan_request.recent_race_time)
            if plan_request.recent_race_time
            else None
        )
        filters = [
            TrainingPlan.user_id == user_id,
            TrainingPlan.plan_type == "fitness",
            TrainingPlan.current_weekly_km == plan_request.current_km,
            TrainingPlan.weeks_duration == plan_request.weeks,
            TrainingPlan.max_runs_per_week == plan_request.runs_per_week,
        ]
        if plan_request.focus_area:
            filters.append(
                TrainingPlan.target_distance == f"fitness_{plan_request.focus_area}"
            )
        if race_time_seconds is not None:
            filters.append(TrainingPlan.recent_race_time_seconds == race_time_seconds)
        else:
            filters.append(TrainingPlan.recent_race_time_seconds.is_(None))
        if plan_request.vdot is not None:
            filters.append(TrainingPlan.vdot == plan_request.vdot)
        else:
            filters.append(TrainingPlan.vdot.is_(None))

        return self.db.query(TrainingPlan).filter(*filters).first()

    def _persist_plan_core(
        self,
        plan_request: FitnessPlanRequest,
        user: User,
        plan_data: list[dict],
        plan_result: dict,
    ) -> TrainingPlan:
        """Create and persist the TrainingPlan ORM record."""
        training_plan = TrainingPlan(
            user_id=user.id,
            current_weekly_km=plan_request.current_km,
            target_distance=f"fitness_{plan_request.focus_area}",
            weeks_duration=plan_request.weeks,
            max_runs_per_week=plan_request.runs_per_week,
            plan_data=plan_data,
            plan_type="fitness",
            body_weight_kg=plan_request.body_weight_kg,
            max_heart_rate=plan_request.max_heart_rate,
            recent_race_distance_km=plan_request.recent_race_distance_km,
            recent_race_time_seconds=(
                parse_race_time_to_seconds(plan_request.recent_race_time)
                if plan_request.recent_race_time
                else None
            ),
            vdot=plan_request.vdot,
            current_pace=plan_request.current_pace_min_km,
        )
        self.db.add(training_plan)
        self.db.flush()
        return training_plan

    def _persist_weekly_workouts(
        self,
        training_plan: TrainingPlan,
        plan_data: list[dict],
    ) -> None:
        """Create WeeklyPlan and DailyWorkout records."""
        for week_data in plan_data:
            weekly_plan = WeeklyPlan(
                training_plan_id=training_plan.id,
                week_number=week_data["week"],
                total_km=week_data["total_km"],
                workout_types={},
            )
            self.db.add(weekly_plan)
            self.db.flush()

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
                self.db.add(daily_workout)

    def _attach_hr_zones(
        self,
        training_plan: TrainingPlan,
        user: User,
        plan_data: list[dict],
        plan_result: dict,
    ) -> None:
        """Compute and store HR zones."""
        try:
            zones = HRZoneService.compute_and_store_zones(training_plan, user, self.db)
            HRZoneService.inject_hr_zones_into_plan_data(plan_data, zones)
            for week_data in plan_data:
                week_num = week_data.get("week")
                for workout in week_data.get("daily_workouts", []):
                    hr_target = workout.get("hr_zone_target")
                    key_wk_id = workout.get("key_workout_id")
                    if hr_target is None and key_wk_id is None:
                        continue
                    dw = (
                        self.db.query(DailyWorkout)
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
                f"HR zone injection failed for fitness plan {training_plan.id}: {e}"
            )

    def _attach_nutrition(
        self,
        training_plan: TrainingPlan,
        plan_request: FitnessPlanRequest,
        plan_data: list[dict],
        nutrition_engine: NutritionEngine,
    ) -> None:
        """Generate and attach nutrition plan."""
        nutrition_plan = nutrition_engine.generate_weekly_meal_plan(
            plan_request.current_km,
            10.0,
            body_weight=plan_request.body_weight_kg,
        )
        training_plan.nutrition_plan_data = nutrition_plan

        nutrition_phases = nutrition_engine.generate_phased_nutrition_plan(
            plan_data,
            plan_request.current_km,
            10.0,
            body_weight_kg=plan_request.body_weight_kg,
        )
        training_plan.nutrition_phases_data = nutrition_phases
