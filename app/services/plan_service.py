"""Plan creation, customization, and deletion business logic."""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.nutrition.nutrition_engine import NutritionEngine
from app.core.generators.plan_generator import TrainingPlanGenerator
from app.core.race.race_protocol_generator import generate_race_protocol
from app.core.training.vdot_calculator import VDOTCalculator
from app.services.adaptation_service import AdaptationService
from app.services.hr_zone_service import HRZoneService
from app.services.plan_view_service import PlanViewService
from app.models import (
    DailyWorkout,
    PlanCustomization,
    RunLog,
    TrainingPlan,
    User,
    WeeklyPlan,
)
from app.models.triathlon_plan import TriathlonPlan
from app.schemas import PlanRequest
from app.services.plan_adjustments import (
    adjust_distance,
    adjust_intensity,
    apply_ai_suggestions,
    swap_workout,
)
from app.utils import parse_race_time_to_seconds

logger = logging.getLogger(__name__)


class PlanService:
    """Encapsulates plan lifecycle operations."""

    MAX_PLANS_PER_USER = 3

    def __init__(self) -> None:
        self._adaptation_service = AdaptationService()
        self._plan_view_service = PlanViewService()

    # ------------------------------------------------------------------
    # Plan limit
    # ------------------------------------------------------------------

    def has_reached_plan_limit(self, user_id: str, db: Session) -> bool:
        """Return True if the user has reached the maximum number of active plans.

        Counts both regular training plans and triathlon plans, excluding
        completed training plans (past their end date).
        """
        today = date.today()
        training_plans = db.query(TrainingPlan).filter(TrainingPlan.user_id == user_id).all()
        active_training = sum(
            1 for p in training_plans
            if not self._is_plan_completed(p, today)
        )
        triathlon_count = db.query(TriathlonPlan).filter(TriathlonPlan.user_id == user_id).count()
        return (active_training + triathlon_count) >= self.MAX_PLANS_PER_USER

    @staticmethod
    def _is_plan_completed(plan: TrainingPlan, today: date) -> bool:
        if not plan.start_date:
            return False
        start_d = plan.start_date.date() if isinstance(plan.start_date, datetime) else plan.start_date
        end_date = start_d + timedelta(weeks=plan.weeks_duration)
        return today > end_date

    # ------------------------------------------------------------------
    # User resolution
    # ------------------------------------------------------------------

    def get_or_create_anonymous_user(self,
        current_user: Optional[User],
        anonymous_user_id: Optional[str],
        db: Session,
    ) -> User:
        """Return the authenticated user or resolve/create an anonymous one."""
        if current_user:
            return current_user

        if anonymous_user_id:
            user = db.query(User).filter(User.id == anonymous_user_id).first()
            if user and not user.google_id and not user.email:
                return user
            # Stale or authenticated user — fall through to create new anonymous user

        # Use the provided anonymous_user_id (from the cookie middleware) so
        # the plan's user_id matches the browser cookie for ownership checks.
        user = User(id=anonymous_user_id) if anonymous_user_id else User()
        db.add(user)
        db.flush()
        return user

    # ------------------------------------------------------------------
    # Plan creation
    # ------------------------------------------------------------------

    def find_duplicate(self,
        plan_request: PlanRequest,
        user_id: str,
        db: Session,
    ) -> Optional[TrainingPlan]:
        """Return an existing plan that matches all inputs, or None."""
        race_time_seconds = (
            parse_race_time_to_seconds(plan_request.recent_race_time)
            if plan_request.recent_race_time
            else None
        )
        filters = [
            TrainingPlan.user_id == user_id,
            TrainingPlan.current_weekly_km == plan_request.current_km,
            TrainingPlan.target_distance == str(plan_request.target_distance),
            TrainingPlan.weeks_duration == plan_request.weeks,
            TrainingPlan.max_runs_per_week == plan_request.max_runs_per_week,
        ]
        if plan_request.body_weight_kg is not None:
            filters.append(TrainingPlan.body_weight_kg == plan_request.body_weight_kg)
        else:
            filters.append(TrainingPlan.body_weight_kg.is_(None))
        if plan_request.recent_race_distance_km is not None:
            filters.append(
                TrainingPlan.recent_race_distance_km == plan_request.recent_race_distance_km
            )
        else:
            filters.append(TrainingPlan.recent_race_distance_km.is_(None))
        if race_time_seconds is not None:
            filters.append(TrainingPlan.recent_race_time_seconds == race_time_seconds)
        else:
            filters.append(TrainingPlan.recent_race_time_seconds.is_(None))
        if plan_request.vdot is not None:
            filters.append(TrainingPlan.vdot == plan_request.vdot)
        else:
            filters.append(TrainingPlan.vdot.is_(None))
        return db.query(TrainingPlan).filter(*filters).first()

    def create_plan(self,
        plan_request: PlanRequest,
        user: User,
        db: Session,
        plan_generator: TrainingPlanGenerator,
        nutrition_engine: NutritionEngine,
        profile: Optional[dict] = None,
    ) -> tuple[TrainingPlan, list[dict]]:
        """Generate a training plan with nutrition and race protocol, persist to DB.

        Returns:
            (training_plan, plan_data) — the saved ORM object and the raw week list.
            If an identical plan already exists for this user, the existing plan is
            returned and no new record is created.
        """
        existing = self.find_duplicate(plan_request, user.id, db)
        if existing:
            logger.info(
                f"Duplicate plan detected for user {user.id} — returning existing plan {existing.id}"
            )
            return existing, json.loads(existing.plan_data) if existing.plan_data else []

        effective_vdot = plan_request.goal_vdot or plan_request.vdot
        plan_data = plan_generator.generate_plan(
            plan_request.current_km,
            plan_request.target_distance,
            plan_request.weeks,
            plan_request.max_runs_per_week,
            vdot=effective_vdot,
            profile=profile,
            terrain=plan_request.terrain,
        )

        try:
            training_plan = self._persist_plan_core(plan_request, user, plan_data, db)
            self._persist_weekly_workouts(training_plan, plan_data, db)
            self._attach_hr_zones(training_plan, user, plan_data, db)
            self._attach_nutrition(training_plan, plan_request, plan_data, nutrition_engine)
            self._attach_race_protocol(training_plan, plan_request)
            db.commit()
        except Exception:
            db.rollback()
            raise

        return training_plan, plan_data

    # ------------------------------------------------------------------
    # create_plan helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _persist_plan_core(
        plan_request: PlanRequest,
        user: User,
        plan_data: list[dict],
        db: Session,
    ) -> TrainingPlan:
        """Create and flush the TrainingPlan row."""
        training_plan = TrainingPlan(
            user_id=user.id,
            current_weekly_km=plan_request.current_km,
            target_distance=str(plan_request.target_distance),
            weeks_duration=plan_request.weeks,
            max_runs_per_week=plan_request.max_runs_per_week,
            plan_data=json.dumps(plan_data),
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
        )
        db.add(training_plan)
        db.flush()
        return training_plan

    @staticmethod
    def _persist_weekly_workouts(
        training_plan: TrainingPlan,
        plan_data: list[dict],
        db: Session,
    ) -> None:
        """Persist WeeklyPlan and DailyWorkout rows for each week of the plan."""
        for week_data in plan_data:
            weekly_plan = WeeklyPlan(
                training_plan_id=training_plan.id,
                week_number=week_data["week"],
                total_km=week_data["total_km"],
                workout_types=json.dumps(week_data.get("workout_distribution", {})),
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

    @staticmethod
    def _attach_hr_zones(
        training_plan: TrainingPlan,
        user: User,
        plan_data: list[dict],
        db: Session,
    ) -> None:
        """Compute HR zones, inject them into plan_data, and persist per-workout targets.

        Non-fatal: HR zones are optional enrichment — a failure here must not
        roll back the plan, so the exception is logged and swallowed.
        """
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
            training_plan.plan_data = json.dumps(plan_data)
        except Exception as e:
            logger.warning(
                f"HR zone injection failed for plan {training_plan.id}: {e}"
            )

    @staticmethod
    def _attach_nutrition(
        training_plan: TrainingPlan,
        plan_request: PlanRequest,
        plan_data: list[dict],
        nutrition_engine: NutritionEngine,
    ) -> None:
        """Generate weekly + phased nutrition plans and attach as JSON."""
        nutrition_plan = nutrition_engine.generate_weekly_meal_plan(
            plan_request.current_km,
            plan_request.target_distance,
            body_weight=plan_request.body_weight_kg,
        )
        training_plan.nutrition_plan_data = json.dumps(nutrition_plan)

        nutrition_phases = nutrition_engine.generate_phased_nutrition_plan(
            plan_data,
            plan_request.current_km,
            plan_request.target_distance,
            body_weight_kg=plan_request.body_weight_kg,
        )
        training_plan.nutrition_phases_data = json.dumps(nutrition_phases)

    @staticmethod
    def _attach_race_protocol(
        training_plan: TrainingPlan,
        plan_request: PlanRequest,
    ) -> None:
        """Compute a VDOT-derived goal pace and attach the race protocol.

        User-provided goal_pace wins when set; otherwise fall back to the
        VDOT-derived race pace.
        """
        goal_pace = plan_request.goal_pace_min_km or PlanService._goal_pace_from_vdot(
            plan_request.vdot, plan_request.target_distance
        )
        race_protocol = generate_race_protocol(
            plan_request.target_distance,
            goal_pace,
        )
        training_plan.race_protocol_data = json.dumps(race_protocol)

    @staticmethod
    def _goal_pace_from_vdot(
        vdot: Optional[float],
        target_distance: float,
    ) -> Optional[float]:
        """Return a goal race pace (min/km) from VDOT zones, or None if unavailable.

        Zone selection is distance-specific:
        - ≤5K: I zone (VO2max)
        - ≤10K: T zone (threshold)
        - ≤half: M zone, held 5% faster than marathon pace
        - longer: straight M zone
        """
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

    # ------------------------------------------------------------------
    # Plan customization
    # ------------------------------------------------------------------

    def customize_plan(self,
        training_plan: TrainingPlan,
        week_number: int,
        adjustment_type: str,
        adjustment_value: str,
        db: Session,
    ) -> list[dict]:
        """Apply a customization to a plan and persist the change.

        Returns:
            The updated plan_data list.
        """
        plan_data = json.loads(training_plan.plan_data) if training_plan.plan_data else []

        if adjustment_type == "intensity":
            plan_data = adjust_intensity(plan_data, week_number, adjustment_value)
        elif adjustment_type == "workout_swap":
            plan_data = swap_workout(plan_data, week_number, adjustment_value)
        elif adjustment_type == "distance":
            plan_data = adjust_distance(plan_data, week_number, float(adjustment_value))
        elif adjustment_type == "ai_suggest":
            plan_data = apply_ai_suggestions(plan_data, week_number, adjustment_value)

        customization = PlanCustomization(
            training_plan_id=training_plan.id,
            week_number=week_number,
            adjustment_type=adjustment_type,
            adjustment_value=adjustment_value,
        )
        db.add(customization)

        training_plan.plan_data = json.dumps(plan_data)
        db.commit()

        return plan_data

    # ------------------------------------------------------------------
    # Plan deletion
    # ------------------------------------------------------------------

    def delete_plan(self, training_plan: TrainingPlan, db: Session) -> None:
        """Delete a training plan and all associated records."""
        plan_id = training_plan.id
        user_id = training_plan.user_id

        from app.models.run_feedback import RunFeedback

        # Unlink runs FIRST — must happen before DailyWorkout deletion to
        # avoid FK constraint violations (RunLog.daily_workout_id →
        # daily_workouts.id). Runs are preserved so they remain available
        # for mapping to other plans.
        db.query(RunLog).filter(RunLog.training_plan_id == plan_id).update(
            {RunLog.training_plan_id: None, RunLog.daily_workout_id: None},
            synchronize_session="fetch",
        )

        weekly_plans = (
            db.query(WeeklyPlan)
            .filter(WeeklyPlan.training_plan_id == plan_id)
            .all()
        )
        # NULL out RunFeedback.planned_workout_id before deleting DailyWorkouts
        workout_ids = []
        for wp in weekly_plans:
            wids = [
                w.id
                for w in db.query(DailyWorkout.id)
                .filter(DailyWorkout.weekly_plan_id == wp.id)
                .all()
            ]
            workout_ids.extend(wids)
        if workout_ids:
            db.query(RunFeedback).filter(
                RunFeedback.planned_workout_id.in_(workout_ids)
            ).update(
                {RunFeedback.planned_workout_id: None},
                synchronize_session="fetch",
            )

        for wp in weekly_plans:
            db.query(DailyWorkout).filter(
                DailyWorkout.weekly_plan_id == wp.id
            ).delete()
        db.query(WeeklyPlan).filter(
            WeeklyPlan.training_plan_id == plan_id
        ).delete()

        db.query(PlanCustomization).filter(
            PlanCustomization.training_plan_id == plan_id
        ).delete()

        db.delete(training_plan)
        db.commit()

    # ------------------------------------------------------------------
    # Delegation to PlanViewService
    # ------------------------------------------------------------------

    def enrich_plan_data_with_ids(
        self,
        plan_data: list[dict],
        training_plan_id: str,
        db: Session,
    ) -> list[dict]:
        return self._plan_view_service.enrich_plan_data_with_ids(plan_data, training_plan_id, db)

    def nutrition_for_template(self, nutrition_plan_data: str) -> dict[str, Any]:
        return self._plan_view_service.nutrition_for_template(nutrition_plan_data)

    def get_logged_runs_map(
        self,
        training_plan_id: str,
        db: Session,
    ) -> tuple[dict, list]:
        return self._plan_view_service.get_logged_runs_map(training_plan_id, db)

    def get_adjustment_hints(
        self,
        training_plan: TrainingPlan,
        performance_analysis: dict,
        db: Session,
    ) -> dict[str, Any]:
        return self._plan_view_service.get_adjustment_hints(training_plan, performance_analysis, db)

    def get_feedback_map(self, logged_runs: list, db: Session) -> dict[str, Any]:
        return self._plan_view_service.get_feedback_map(logged_runs, db)

    def get_completion_stats(
        self,
        training_plan: TrainingPlan,
        db: Session,
    ) -> dict[str, Any]:
        return self._plan_view_service.get_completion_stats(training_plan, db)

    def get_next_plan_cta(self, target_distance_km: float) -> dict[str, str]:
        return self._plan_view_service.get_next_plan_cta(target_distance_km)

    def get_plan_view_data(
        self,
        training_plan: TrainingPlan,
        current_user: Optional[User],
        db: Session,
    ) -> dict[str, Any]:
        return self._plan_view_service.get_plan_view_data(training_plan, current_user, db)

