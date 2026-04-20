"""View-assembly logic for training plan pages.

Extracts enrichment, nutrition formatting, logged-run mapping,
adjustment hints, feedback, completion stats, and the full
get_plan_view_data orchestrator from PlanService.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.training.hr_zone_calculator import HRZoneCalculator
from app.models import (
    DailyWorkout,
    RunLog,
    TrainingPlan,
    User,
    WeeklyPlan,
)
from app.services.adaptation_service import AdaptationService
from app.services.hr_zone_service import HRZoneService

logger = logging.getLogger(__name__)


class PlanViewService:
    """Assembles view-layer data for training plan templates."""

    def __init__(self) -> None:
        self._adaptation_service = AdaptationService()

    # ------------------------------------------------------------------
    # Plan data enrichment
    # ------------------------------------------------------------------

    def enrich_plan_data_with_ids(
        self,
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

    def nutrition_for_template(self, nutrition_plan_data: str) -> dict[str, Any]:
        """Convert stored nutrition plan JSON to a template-compatible dict."""
        if not nutrition_plan_data:
            return {}

        nutrition_plan = nutrition_plan_data

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

    def get_logged_runs_map(
        self,
        training_plan_id: str,
        db: Session,
    ) -> tuple[dict, list]:
        """Return (workout_id -> RunLog map, all logged runs) for a plan."""
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

    def get_adjustment_hints(
        self,
        training_plan: TrainingPlan,
        performance_analysis: dict,
        db: Session,
    ) -> dict[str, Any]:
        """Compute skipped/rescheduled counts and whether adjustment is needed.

        Only counts misses that occurred **after** the most recent adjustment
        (if any), so the banner doesn't re-appear for already-addressed issues.
        """
        skipped_count = 0
        rescheduled_count = 0
        needs_adjustment = False
        avg_effort = performance_analysis.get("avg_effort")

        if training_plan.start_date:
            try:
                since = training_plan.last_adjusted_at
                skip_result = self._adaptation_service.detect_skipped_workouts(
                    training_plan.id, db, since=since,
                )
                skipped_count = skip_result["skipped"]
                rescheduled_count = skip_result["rescheduled"]

                effort_extreme = False
                if avg_effort is not None and not since:
                    effort_extreme = avg_effort >= 8 or avg_effort <= 3
                elif since:
                    recent_runs = (
                        db.query(RunLog.perceived_effort)
                        .filter(
                            RunLog.training_plan_id == training_plan.id,
                            RunLog.perceived_effort.isnot(None),
                            RunLog.date > since,
                        )
                        .all()
                    )
                    if len(recent_runs) >= 3:
                        recent_avg = sum(r[0] for r in recent_runs) / len(recent_runs)
                        effort_extreme = recent_avg >= 8 or recent_avg <= 3

                needs_adjustment = skipped_count >= 2 or effort_extreme
            except Exception as e:
                logger.warning(f"Could not detect skipped workouts: {e}")

        return {
            "skipped_count": skipped_count,
            "rescheduled_count": rescheduled_count,
            "needs_adjustment": needs_adjustment,
        }

    def get_feedback_map(self, logged_runs: list, db: Session) -> dict[str, Any]:
        """Load coaching feedback keyed by run_log_id."""
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

    def get_completion_stats(
        self,
        training_plan: TrainingPlan,
        db: Session,
    ) -> dict[str, Any]:
        """Compute summary stats for a completed plan from its run logs."""
        runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == training_plan.id)
            .all()
        )

        if not runs:
            return {"has_data": False}

        distances = [r.distance_km for r in runs if r.distance_km]
        total_km = sum(distances) if distances else 0
        longest_run = max(distances) if distances else 0

        paces = [r.avg_pace_min_km for r in runs if r.avg_pace_min_km]
        best_pace = min(paces) if paces else None

        efforts = [r.perceived_effort for r in runs if r.perceived_effort]
        avg_effort = round(sum(efforts) / len(efforts), 1) if efforts else None

        plan_data = training_plan.plan_data if training_plan.plan_data else []
        peak_km = max((w.get("total_km", 0) for w in plan_data), default=0)

        return {
            "has_data": bool(distances),
            "total_km": round(total_km, 1),
            "total_runs": len(runs),
            "longest_run_km": round(longest_run, 1),
            "best_pace_min_km": best_pace,
            "avg_effort": avg_effort,
            "start_km_per_week": training_plan.current_weekly_km,
            "peak_km_per_week": round(peak_km, 1),
        }

    _NEXT_PLAN_MAP: dict[float, dict[str, str]] = {
        5.0: {
            "label": "10K",
            "url": "/?target_distance=10",
            "message": "Ready to double the distance? Take on the 10K.",
        },
        10.0: {
            "label": "Half Marathon",
            "url": "/?target_distance=21.1",
            "message": "You've got the base. The Half Marathon is your next big step.",
        },
        21.1: {
            "label": "Marathon",
            "url": "/?target_distance=42.2",
            "message": "Go the full distance. You're ready for the Marathon.",
        },
        42.2: {
            "label": "Trail Running",
            "url": "/?target_distance=30",
            "message": "Take your fitness off-road with a Trail Running plan.",
        },
        30.0: {
            "label": "Marathon",
            "url": "/?target_distance=42.2",
            "message": "Bring your trail strength to the road with a Marathon plan.",
        },
    }

    def get_next_plan_cta(self, target_distance_km: float) -> dict[str, str]:
        """Return a next-step CTA dict based on the completed plan's target distance."""
        return self._NEXT_PLAN_MAP.get(target_distance_km, {
            "label": "New Plan",
            "url": "/",
            "message": "Keep the momentum going -- start your next training plan.",
        })

    def get_plan_view_data(
        self,
        training_plan: TrainingPlan,
        current_user: Optional[User],
        db: Session,
    ) -> dict[str, Any]:
        """Assemble view-layer data for plan.html without rendering.

        Returns extra context keys: performance_analysis, logged_runs,
        progress_data, skipped_count, rescheduled_count, needs_adjustment.
        """
        from app.services.performance_service import PerformanceService

        performance_analysis = self._adaptation_service.analyze_performance(
            training_plan.id, db
        )

        logged_runs_map, logged_runs = self.get_logged_runs_map(
            training_plan.id, db
        )

        progress_data = None
        if current_user and logged_runs:
            try:
                progress_data = PerformanceService(db).get_plan_progress(training_plan)
            except Exception as e:
                logger.warning(f"Could not compute progress data: {e}")

        # Adjustment hints
        hints = {"skipped_count": 0, "rescheduled_count": 0, "needs_adjustment": False}
        if current_user:
            hints = self.get_adjustment_hints(
                training_plan, performance_analysis, db
            )

        # Completion stats
        completion_stats = None
        next_plan_cta = None
        if training_plan.start_date and current_user:
            from datetime import date as _date, datetime as _datetime
            sd = training_plan.start_date
            start_d = sd.date() if isinstance(sd, _datetime) else sd
            delta_days = (_date.today() - start_d).days
            current_wk = (delta_days // 7) + 1 if delta_days >= 0 else 0
            if current_wk > training_plan.weeks_duration:
                completion_stats = self.get_completion_stats(training_plan, db)
                next_plan_cta = self.get_next_plan_cta(training_plan.target_distance_km)

        # Weeks that have had suggestion overrides applied
        overridden_week_rows = (
            db.query(WeeklyPlan.week_number)
            .join(DailyWorkout, DailyWorkout.weekly_plan_id == WeeklyPlan.id)
            .filter(
                WeeklyPlan.training_plan_id == training_plan.id,
                DailyWorkout.baseline_distance_km.isnot(None),
            )
            .distinct()
            .all()
        )
        overridden_weeks = {row[0] for row in overridden_week_rows}

        return {
            "performance_analysis": performance_analysis,
            "logged_runs": logged_runs_map,
            "progress_data": progress_data,
            **hints,
            "hr_zones": HRZoneService.get_zones_for_plan(training_plan),
            "feedback_map": self.get_feedback_map(logged_runs, db),
            "completion_stats": completion_stats,
            "next_plan_cta": next_plan_cta,
            "overridden_weeks": overridden_weeks,
        }
