"""Plan creation, customization, and deletion business logic."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.hr_zone_calculator import HRZoneCalculator
from app.core.nutrition_engine import NutritionEngine
from app.core.plan_generator import TrainingPlanGenerator
from app.core.race_protocol_generator import generate_race_protocol
from app.core.vdot_calculator import VDOTCalculator
from app.services.hr_zone_service import HRZoneService
from app.models import (
    DailyWorkout,
    PlanCustomization,
    RunLog,
    TrainingPlan,
    User,
    WeeklyPlan,
)
from app.schemas import PlanRequest
from app.utils import parse_race_time_to_seconds

logger = logging.getLogger(__name__)


class PlanService:
    """Encapsulates plan lifecycle operations."""

    # ------------------------------------------------------------------
    # User resolution
    # ------------------------------------------------------------------

    @staticmethod
    def get_or_create_anonymous_user(
        current_user: Optional[User],
        anonymous_user_id: Optional[str],
        db: Session,
    ) -> User:
        """Return the authenticated user or resolve/create an anonymous one."""
        if current_user:
            return current_user

        if anonymous_user_id:
            user = db.query(User).filter(User.id == anonymous_user_id).first()
            if not user or (user.google_id or user.email):
                user = User()
                db.add(user)
                db.flush()
        else:
            user = User()
            db.add(user)
            db.flush()

        return user

    # ------------------------------------------------------------------
    # Plan creation
    # ------------------------------------------------------------------

    @staticmethod
    def find_duplicate(
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

    @staticmethod
    def create_plan(
        plan_request: PlanRequest,
        user: User,
        db: Session,
        plan_generator: TrainingPlanGenerator,
        nutrition_engine: NutritionEngine,
    ) -> tuple[TrainingPlan, list[dict]]:
        """Generate a training plan with nutrition and race protocol, persist to DB.

        Returns:
            (training_plan, plan_data) — the saved ORM object and the raw week list.
            If an identical plan already exists for this user, the existing plan is
            returned and no new record is created.
        """
        # --- Duplicate detection ---
        existing = PlanService.find_duplicate(plan_request, user.id, db)
        if existing:
            logger.info(
                f"Duplicate plan detected for user {user.id} — returning existing plan {existing.id}"
            )
            return existing, json.loads(existing.plan_data)

        plan_data = plan_generator.generate_plan(
            plan_request.current_km,
            plan_request.target_distance,
            plan_request.weeks,
            plan_request.max_runs_per_week,
            vdot=plan_request.vdot,
        )

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
        )
        db.add(training_plan)
        db.flush()

        # Weekly plans + daily workouts
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

        # HR zones — compute and inject into plan_data + DailyWorkout rows
        try:
            zones = HRZoneService.compute_and_store_zones(training_plan, user, db)
            HRZoneService.inject_hr_zones_into_plan_data(plan_data, zones)
            # Persist hr_zone_target on DailyWorkout rows
            for week_data in plan_data:
                week_num = week_data.get("week")
                for workout in week_data.get("daily_workouts", []):
                    hr_target = workout.get("hr_zone_target")
                    key_wk_id = workout.get("key_workout_id")
                    if hr_target is not None or key_wk_id is not None:
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
            # Re-serialise plan_data with zone annotations
            training_plan.plan_data = json.dumps(plan_data)
        except Exception as e:
            logger.warning(f"HR zone injection failed: {e}")

        # Nutrition
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

        # Race-day protocol
        goal_pace = None
        if plan_request.vdot:
            zones = VDOTCalculator.get_pace_zones(plan_request.vdot)
            if zones and all(k in zones for k in ("I", "T", "M")):
                if plan_request.target_distance <= 5.0:
                    goal_pace = zones["I"]["pace_min_km"]
                elif plan_request.target_distance <= 10.0:
                    goal_pace = zones["T"]["pace_min_km"]
                elif plan_request.target_distance <= 21.1:
                    goal_pace = zones["M"]["pace_min_km"] * 0.95
                else:
                    goal_pace = zones["M"]["pace_min_km"]

        race_protocol = generate_race_protocol(
            plan_request.target_distance,
            goal_pace,
        )
        training_plan.race_protocol_data = json.dumps(race_protocol)

        db.commit()

        return training_plan, plan_data

    # ------------------------------------------------------------------
    # Plan customization
    # ------------------------------------------------------------------

    @staticmethod
    def customize_plan(
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
        plan_data = json.loads(training_plan.plan_data)

        if adjustment_type == "intensity":
            plan_data = _adjust_intensity(plan_data, week_number, adjustment_value)
        elif adjustment_type == "workout_swap":
            plan_data = _swap_workout(plan_data, week_number, adjustment_value)
        elif adjustment_type == "distance":
            plan_data = _adjust_distance(plan_data, week_number, float(adjustment_value))
        elif adjustment_type == "ai_suggest":
            plan_data = _apply_ai_suggestions(plan_data, week_number, adjustment_value)

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

    @staticmethod
    def delete_plan(training_plan: TrainingPlan, db: Session) -> None:
        """Delete a training plan and all associated records."""
        plan_id = training_plan.id
        user_id = training_plan.user_id

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
    # Plan data enrichment
    # ------------------------------------------------------------------

    @staticmethod
    def enrich_plan_data_with_ids(
        plan_data: list[dict],
        training_plan_id: str,
        db: Session,
    ) -> list[dict]:
        """Inject database DailyWorkout.id into each workout dict.

        The plan_data JSON doesn't include database IDs, but the template
        needs them to look up logged runs via ``logged_runs.get(workout.id)``.
        This method queries the DailyWorkout table and matches by
        (week_number, day_of_week) to inject the ``id`` key.
        """
        # Build mapping: (week_number, day_of_week) -> DailyWorkout.id
        rows = (
            db.query(
                WeeklyPlan.week_number,
                DailyWorkout.day_of_week,
                DailyWorkout.id,
            )
            .join(DailyWorkout, DailyWorkout.weekly_plan_id == WeeklyPlan.id)
            .filter(WeeklyPlan.training_plan_id == training_plan_id)
            .all()
        )
        id_map = {(wn, dow): wid for wn, dow, wid in rows}

        for week in plan_data:
            week_num = week.get("week")
            for workout in week.get("daily_workouts", []):
                key = (week_num, workout.get("day"))
                workout["id"] = id_map.get(key)

        return plan_data

    # ------------------------------------------------------------------
    # Nutrition helpers
    # ------------------------------------------------------------------

    @staticmethod
    def nutrition_for_template(nutrition_plan_data: str) -> dict[str, Any]:
        """Convert stored nutrition plan JSON to a template-compatible dict."""
        if not nutrition_plan_data:
            return {}

        nutrition_plan = json.loads(nutrition_plan_data)

        # Old format: list of daily plans
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

        # New blueprint format
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

    # ------------------------------------------------------------------
    # View data assembly
    # ------------------------------------------------------------------

    @staticmethod
    def get_plan_view_data(
        training_plan: TrainingPlan,
        current_user: Optional[User],
        db: Session,
    ) -> dict[str, Any]:
        """Assemble view-layer data for plan.html without rendering.

        Returns extra context keys: performance_analysis, logged_runs,
        progress_data, skipped_count, rescheduled_count, needs_adjustment.
        """
        from app.services.adaptation_service import AdaptationService
        from app.services.performance_service import PerformanceService

        adaptation_service = AdaptationService()
        performance_analysis = adaptation_service.analyze_performance(
            training_plan.id, db
        )

        logged_runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == training_plan.id)
            .order_by(RunLog.date.desc())
            .all()
        )
        logged_runs_map = {
            run.daily_workout_id: run for run in logged_runs if run.daily_workout_id
        }

        progress_data = None
        if current_user and logged_runs:
            perf_service = PerformanceService(db)
            try:
                progress_data = perf_service.get_plan_progress(training_plan)
            except Exception as e:
                logger.warning(f"Could not compute progress data: {e}")

        # Compute adjustment hints for the UI
        skipped_count = 0
        rescheduled_count = 0
        needs_adjustment = False
        avg_effort = performance_analysis.get("avg_effort")
        if current_user and training_plan.start_date:
            try:
                skip_result = adaptation_service.detect_skipped_workouts(
                    training_plan.id, db
                )
                skipped_count = skip_result["skipped"]
                rescheduled_count = skip_result["rescheduled"]
                # Trigger adjustment on skipped workouts OR extreme effort
                needs_adjustment = (
                    skipped_count >= 2
                    or (avg_effort is not None and (avg_effort >= 8 or avg_effort <= 3))
                )
            except Exception as e:
                logger.warning(f"Could not detect skipped workouts: {e}")

        # HR zones for template rendering
        hr_zones_info = HRZoneService.get_zones_for_plan(training_plan)

        # Coaching feedback for logged runs
        feedback_map: dict[str, Any] = {}
        try:
            from app.models.run_feedback import RunFeedback
            if logged_runs:
                run_ids = [r.id for r in logged_runs]
                feedbacks = (
                    db.query(RunFeedback)
                    .filter(RunFeedback.run_log_id.in_(run_ids))
                    .all()
                )
                feedback_map = {fb.run_log_id: fb for fb in feedbacks}
        except Exception as e:
            logger.warning(f"Could not load feedback: {e}")

        return {
            "performance_analysis": performance_analysis,
            "logged_runs": logged_runs_map,
            "progress_data": progress_data,
            "skipped_count": skipped_count,
            "rescheduled_count": rescheduled_count,
            "needs_adjustment": needs_adjustment,
            "hr_zones": hr_zones_info,
            "feedback_map": feedback_map,
        }


# ------------------------------------------------------------------
# Private customization helpers
# ------------------------------------------------------------------


def _adjust_intensity(
    plan_data: list[dict], week_number: int, intensity_level: str
) -> list[dict]:
    """Adjust workout intensity for a specific week."""
    for week in plan_data:
        if week["week"] == week_number:
            for workout in week.get("daily_workouts", []):
                if workout["type"] != "rest":
                    workout["intensity"] = intensity_level
                    if intensity_level == "low":
                        workout["notes"] = (
                            workout["notes"]
                            .replace("threshold", "easy")
                            .replace("tempo", "easy")
                        )
                    elif intensity_level == "high":
                        workout["notes"] = (
                            workout["notes"]
                            .replace("easy", "tempo")
                            .replace("recovery", "moderate")
                        )
    return plan_data


def _swap_workout(
    plan_data: list[dict], week_number: int, swap_info: str
) -> list[dict]:
    """Swap workout types for a specific week."""
    try:
        day, new_type = swap_info.split(",")
        day = int(day)

        for week in plan_data:
            if week["week"] == week_number:
                for workout in week.get("daily_workouts", []):
                    if workout["day"] == day:
                        old_type = workout["type"]
                        workout["type"] = new_type

                        if new_type == "rest":
                            workout["distance"] = 0
                            workout["notes"] = "Rest day for recovery"
                        elif old_type == "rest" and new_type != "rest":
                            workout["distance"] = 5.0
                            workout["notes"] = f"Easy {new_type} run - focus on form"

                        workout["intensity"] = (
                            "low" if new_type in ["rest", "easy"] else "medium"
                        )
    except (ValueError, TypeError):
        pass

    return plan_data


def _adjust_distance(
    plan_data: list[dict], week_number: int, distance_change: float
) -> list[dict]:
    """Adjust distances for all workouts in a week."""
    for week in plan_data:
        if week["week"] == week_number:
            current_total = sum(
                w.get("distance", 0) for w in week.get("daily_workouts", [])
            )

            if current_total > 0:
                ratio = (current_total + distance_change) / current_total

                for workout in week.get("daily_workouts", []):
                    if workout["distance"] > 0:
                        workout["distance"] = round(workout["distance"] * ratio, 1)

                week["total_km"] = round(week["total_km"] + distance_change, 1)

    return plan_data


def _apply_ai_suggestions(
    plan_data: list[dict], week_number: int, preference: str
) -> list[dict]:
    """Apply AI-powered suggestions based on user preferences."""
    for week in plan_data:
        if week["week"] == week_number:
            if preference == "more_rest":
                for workout in week.get("daily_workouts", []):
                    if workout["type"] == "easy":
                        removed_distance = workout.get("distance", 0)
                        workout["type"] = "rest"
                        workout["distance"] = 0
                        workout["notes"] = "Additional rest day for recovery"
                        week["total_km"] = round(
                            week["total_km"] - removed_distance, 1
                        )
                        break

            elif preference == "more_speed":
                for workout in week.get("daily_workouts", []):
                    if workout["type"] == "easy":
                        workout["type"] = "interval"
                        workout["intensity"] = "high"
                        workout["notes"] = (
                            "Speed work: 6x400m at 5K pace with 400m recovery"
                        )
                        break

            elif preference == "more_endurance":
                for workout in week.get("daily_workouts", []):
                    if workout["type"] == "long":
                        old_distance = workout["distance"]
                        workout["distance"] = round(old_distance * 1.2, 1)
                        week["total_km"] = round(
                            week["total_km"] + (workout["distance"] - old_distance), 1
                        )
                        workout["notes"] = (
                            f'Extended long run: {workout["distance"]}km at '
                            "conversational pace"
                        )
                        break

    return plan_data
