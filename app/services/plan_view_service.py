"""View-assembly logic for training plan pages.

Thin orchestrator delegating to plan_data_enricher, completion_stats,
and week_pulse_generator.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import DailyWorkout, TrainingPlan, User, WeeklyPlan
from app.services.adaptation_service import AdaptationService
from app.services.hr_zone_service import HRZoneService

from . import completion_stats as _cs
from . import plan_data_enricher as _enricher
from . import week_pulse_generator as _pulse

logger = logging.getLogger(__name__)


class PlanViewService:
    """Assembles view-layer data for training plan templates."""

    def __init__(self) -> None:
        self._adaptation_service = AdaptationService()

    def enrich_plan_data_with_ids(self, plan_data, training_plan_id, db):
        return _enricher.enrich_plan_data_with_ids(plan_data, training_plan_id, db)

    def nutrition_for_template(self, nutrition_plan_data):
        return _enricher.nutrition_for_template(nutrition_plan_data)

    def get_logged_runs_map(self, training_plan_id, db):
        return _enricher.get_logged_runs_map(training_plan_id, db)

    def get_feedback_map(self, logged_runs, db):
        return _enricher.get_feedback_map(logged_runs, db)

    def get_adjustment_hints(self, training_plan, performance_analysis, db):
        return _cs.get_adjustment_hints(
            training_plan, performance_analysis, db, self._adaptation_service
        )

    def get_completion_stats(self, training_plan, db):
        return _cs.get_completion_stats(training_plan, db)

    def get_next_plan_cta(self, target_distance_km):
        return _cs.get_next_plan_cta(target_distance_km)

    def get_week_pulse(self, training_plan, current_week, db):
        return _pulse.get_week_pulse(training_plan, current_week, db)

    def get_plan_view_data(
        self,
        training_plan: TrainingPlan,
        current_user: Optional[User],
        db: Session,
    ) -> dict[str, Any]:
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

        hints = {"skipped_count": 0, "rescheduled_count": 0, "needs_adjustment": False}
        if current_user:
            hints = self.get_adjustment_hints(
                training_plan, performance_analysis, db
            )

        comp_stats = None
        next_plan_cta = None
        if training_plan.start_date and current_user:
            from datetime import date as _date, datetime as _datetime
            sd = training_plan.start_date
            start_d = sd.date() if isinstance(sd, _datetime) else sd
            delta_days = (_date.today() - start_d).days
            current_wk = (delta_days // 7) + 1 if delta_days >= 0 else 0
            if current_wk > training_plan.weeks_duration:
                comp_stats = self.get_completion_stats(training_plan, db)
                next_plan_cta = self.get_next_plan_cta(training_plan.target_distance_km)

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

        adaptation_timeline = training_plan.adaptation_history or []
        week_evolution = self._compute_week_evolution(training_plan, db)

        week_pulse = None
        if current_user and training_plan.start_date:
            from datetime import date as _d2, datetime as _dt2
            sd2 = training_plan.start_date
            start_d2 = sd2.date() if isinstance(sd2, _dt2) else sd2
            delta2 = (_d2.today() - start_d2).days
            cw = (delta2 // 7) + 1 if delta2 >= 0 else 0
            if 1 <= cw <= (training_plan.weeks_duration or 0):
                try:
                    week_pulse = self.get_week_pulse(training_plan, cw, db)
                except Exception as e:
                    logger.warning(f"Week pulse failed: {e}")

        weekly_feedback_summaries = {}
        if current_user:
            try:
                from app.services.feedback_service import FeedbackService
                weekly_feedback_summaries = FeedbackService.get_weekly_feedback_summary(
                    training_plan.id, current_user.id, db
                )
            except Exception as e:
                logger.warning(f"Weekly feedback summary failed: {e}")

        return {
            "performance_analysis": performance_analysis,
            "logged_runs": logged_runs_map,
            "progress_data": progress_data,
            **hints,
            "hr_zones": HRZoneService.get_zones_for_plan(training_plan),
            "feedback_map": self.get_feedback_map(logged_runs, db),
            "completion_stats": comp_stats,
            "next_plan_cta": next_plan_cta,
            "overridden_weeks": overridden_weeks,
            "adaptation_timeline": adaptation_timeline,
            "week_evolution": week_evolution,
            "week_pulse": week_pulse,
            "weekly_feedback_summaries": weekly_feedback_summaries,
        }

    def _compute_week_evolution(
        self,
        training_plan: TrainingPlan,
        db: Session,
    ) -> dict[int, dict[str, Any]]:
        plan_data = training_plan.plan_data or []

        weekly_plans = (
            db.query(WeeklyPlan)
            .filter(WeeklyPlan.training_plan_id == training_plan.id)
            .all()
        )

        evolution: dict[int, dict[str, Any]] = {}
        for wp in weekly_plans:
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == wp.id)
                .all()
            )
            original_total = sum(
                w.baseline_distance_km or w.distance_km or 0
                for w in workouts
                if w.workout_type not in ("rest", "recovery")
            )
            current_total = sum(
                w.distance_km or 0
                for w in workouts
                if w.workout_type not in ("rest", "recovery")
            )

            if original_total > 0 and abs(current_total - original_total) > 0.2:
                delta_pct = round((current_total - original_total) / original_total * 100)
                direction = "up" if delta_pct > 0 else "down"
                evolution[wp.week_number] = {
                    "direction": direction,
                    "original_km": round(original_total, 1),
                    "current_km": round(current_total, 1),
                    "delta_pct": delta_pct,
                }

        return evolution
