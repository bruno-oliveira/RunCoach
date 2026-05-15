"""Adaptation service — facade that delegates to focused sub-modules.

All public methods match the original AdaptationService API so that
existing callers (routers, other services, tests) work unchanged.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from . import alert_checker, plan_adjuster, recalibrator, recommendation_evaluator, run_mapper, suggestion_generator, type_swapper
from .performance_analyzer import analyze_performance as _analyze_performance
from .skipped_detector import detect_skipped_workouts as _detect_skipped


class AdaptationService:
    """Thin facade preserving the original class interface."""

    def analyze_performance(
        self, training_plan_id: str, db: Session
    ) -> Dict[str, Any]:
        return _analyze_performance(training_plan_id, db)

    def detect_skipped_workouts(
        self,
        plan_id: str,
        db: Session,
        *,
        since: Optional[object] = None,
    ) -> Dict[str, int]:
        return _detect_skipped(plan_id, db, since=since)

    def map_runs_to_plan(
        self,
        plan_id: str,
        user_id: str,
        db: Session,
        *,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        return run_mapper.map_runs_to_plan(plan_id, user_id, db, dry_run=dry_run)

    def adjust_plan(
        self, plan_id: str, user_id: str, db: Session
    ) -> Dict[str, Any]:
        return plan_adjuster.adjust_plan(plan_id, user_id, db)

    def reset_adjustment(
        self, plan_id: str, user_id: str, db: Session
    ) -> Dict[str, Any]:
        return plan_adjuster.reset_adjustment(plan_id, user_id, db)

    def check_alerts(
        self, plan_id: str, user_id: str, db: Session
    ) -> Optional[Dict[str, Any]]:
        return alert_checker.check_alerts(plan_id, user_id, db)

    def recalibrate(
        self, plan_id: str, user_id: str, strategy: str, db: Session
    ) -> Dict[str, Any]:
        return recalibrator.recalibrate(plan_id, user_id, strategy, db)

    def get_weekly_suggestions(
        self, plan_id: str, user_id: str, db: Session
    ) -> List[Dict[str, Any]]:
        return suggestion_generator.get_weekly_suggestions(plan_id, user_id, db)

    def evaluate_recommendation(
        self, plan_id: str, user_id: str, db: Session, *, force: bool = False
    ) -> Optional[Dict[str, Any]]:
        return recommendation_evaluator.evaluate_weekly_recommendation(
            plan_id, user_id, db, force=force,
        )

    def accept_recommendation(
        self, plan_id: str, user_id: str, db: Session
    ) -> Dict[str, Any]:
        return recommendation_evaluator.accept_recommendation(plan_id, user_id, db)

    def dismiss_recommendation(
        self, plan_id: str, user_id: str, db: Session
    ) -> Dict[str, Any]:
        return recommendation_evaluator.dismiss_recommendation(plan_id, user_id, db)

    def evaluate_on_run_logged(
        self, plan_id: str, user_id: str, db: Session
    ) -> Optional[Dict[str, Any]]:
        return recommendation_evaluator.evaluate_on_run_logged(plan_id, user_id, db)

    def apply_or_park(
        self,
        plan_id: str,
        user_id: str,
        db: Session,
        evaluation: Dict[str, Any],
        auto_enabled: bool,
    ) -> Dict[str, Any]:
        return recommendation_evaluator.apply_or_park(
            plan_id, user_id, db, evaluation, auto_enabled,
        )
