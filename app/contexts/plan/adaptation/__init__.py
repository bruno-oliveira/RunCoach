"""Adaptation service — facade that delegates to focused sub-modules.

All public methods match the original AdaptationService API so that
existing callers (routers, other services, tests) work unchanged.
"""

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from . import (
    intent_service,
    plan_adjuster,
    proactive_nudge,
    run_mapper,
    type_swapper,  # noqa: F401  (re-exported for callers: adaptation.type_swapper)
)
from .performance_analyzer import analyze_performance as _analyze_performance
from .skipped_detector import detect_skipped_workouts as _detect_skipped


class AdaptationService:
    """Thin facade preserving the original class interface."""

    def analyze_performance(self, training_plan_id: str, db: Session) -> Dict[str, Any]:
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

    def preview_adjust_signals(
        self, plan_id: str, user_id: str, db: Session
    ) -> Optional[Dict[str, Any]]:
        return plan_adjuster.preview_adjust_signals(plan_id, user_id, db)

    def reset_adjustment(
        self, plan_id: str, user_id: str, db: Session
    ) -> Dict[str, Any]:
        return plan_adjuster.reset_adjustment(plan_id, user_id, db)

    def preview_reset_adjustment(
        self, plan_id: str, user_id: str, db: Session
    ) -> Dict[str, Any]:
        return plan_adjuster.preview_reset_adjustment(plan_id, user_id, db)

    def mark_change_plan_seen(
        self, plan_id: str, user_id: str, db: Session
    ) -> Dict[str, Any]:
        from app.contexts.plan.repositories import SQLAlchemyPlanRepository

        plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)
        if not plan or not plan.last_change_plan:
            return {"ok": True, "noop": True}
        cp = dict(plan.last_change_plan)
        if cp.get("seen"):
            return {"ok": True, "noop": True}
        cp["seen"] = True
        plan.last_change_plan = cp
        db.commit()
        return {"ok": True}

    # -------------------------------------------------------- proactive nudges

    def get_proactive_nudge(
        self, plan_id: str, user_id: str, db: Session
    ) -> Optional[Dict[str, Any]]:
        return proactive_nudge.get_nudge(plan_id, user_id, db)

    def dismiss_proactive_nudge(
        self,
        plan_id: str,
        user_id: str,
        signature: Optional[str],
        db: Session,
    ) -> Dict[str, Any]:
        return proactive_nudge.dismiss_nudge(plan_id, user_id, signature, db)

    # ------------------------------------------------------------------ intents

    def preview_intent(
        self,
        plan_id: str,
        user_id: str,
        intent: str,
        params: Optional[Dict[str, Any]],
        db: Session,
    ) -> Dict[str, Any]:
        return intent_service.preview_intent(plan_id, user_id, intent, params, db)

    def apply_intent(
        self,
        plan_id: str,
        user_id: str,
        intent: str,
        params: Optional[Dict[str, Any]],
        db: Session,
    ) -> Dict[str, Any]:
        return intent_service.apply_intent(plan_id, user_id, intent, params, db)
