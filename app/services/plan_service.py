"""Plan creation, customization, and deletion business logic."""

import json
import logging
from typing import Any, Optional

from cachetools import TTLCache
from sqlalchemy.orm import Session

from app.core.nutrition_engine import NutritionEngine
from app.core.plan_generator import TrainingPlanGenerator
from app.core.race_protocol_generator import generate_race_protocol
from app.core.vdot_calculator import VDOTCalculator
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

# Process-scoped cache shared across requests
user_plans_cache = TTLCache(maxsize=1000, ttl=300)


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
        """
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
                daily_workout = DailyWorkout(
                    weekly_plan_id=weekly_plan.id,
                    day_of_week=day_workout["day"],
                    workout_type=day_workout["type"],
                    distance_km=day_workout.get("distance", 0),
                    intensity=day_workout.get("intensity", "low"),
                    notes=day_workout.get("description", day_workout.get("notes", "")),
                    coaching_rationale=day_workout.get("coaching_rationale"),
                )
                db.add(daily_workout)

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

        user_plans_cache.pop(f"plans_{user.id}", None)
        logger.info(f"Invalidated plans cache for user {user.id}")

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

        db.query(RunLog).filter(RunLog.training_plan_id == plan_id).delete()

        db.query(PlanCustomization).filter(
            PlanCustomization.training_plan_id == plan_id
        ).delete()

        db.delete(training_plan)
        db.commit()

        user_plans_cache.pop(f"plans_{user_id}", None)

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
        strava_fitness, progress_data.
        """
        from app.services.adaptation_service import AdaptationService
        from app.core.adaptive_plan_generator import AdaptivePlanGenerator
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

        strava_fitness = None
        if current_user and current_user.strava_athlete_id:
            adaptive_gen = AdaptivePlanGenerator()
            strava_fitness = adaptive_gen.calculate_current_fitness_metrics(
                current_user.id, db
            )

        progress_data = None
        if current_user and logged_runs:
            perf_service = PerformanceService(db)
            try:
                progress_data = perf_service.get_plan_progress(training_plan)
            except Exception as e:
                logger.warning(f"Could not compute progress data: {e}")

        return {
            "performance_analysis": performance_analysis,
            "logged_runs": logged_runs_map,
            "strava_fitness": strava_fitness,
            "progress_data": progress_data,
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
                        workout["type"] = "rest"
                        workout["distance"] = 0
                        workout["notes"] = "Additional rest day for recovery"
                        week["total_km"] = round(
                            week["total_km"] - workout.get("distance", 0), 1
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
                        workout["distance"] = round(workout["distance"] * 1.2, 1)
                        week["total_km"] = round(
                            week["total_km"] + (workout["distance"] * 0.2), 1
                        )
                        workout["notes"] = (
                            f'Extended long run: {workout["distance"]}km at '
                            "conversational pace"
                        )
                        break

    return plan_data
