"""Per-plan gap analysis across volume, elevation, long-run, pace, consistency.

``GapAnalysisService`` is the facade; setup/data-loading lives in ``context`` and
the per-dimension computations in ``gap_metrics``. Names are re-exported so
callers import from this package unchanged.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.contexts.runner.fitness.gap_analysis_service.context import (
    _bucket_runs_by_week,
    _load_gap_context,
    _weekly_breakpoint,
)
from app.contexts.runner.fitness.gap_analysis_service.gap_metrics import (
    _compute_consistency,
    _compute_elevation_gap,
    _compute_fitness_trajectory,
    _compute_long_run_gap,
    _compute_pace_gap,
    _compute_volume_gap,
    _generate_top_actions,
)
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.contexts.runner.fitness.readiness_scoring import score_mountain_simulation
from app.models import TrainingPlan

logger = logging.getLogger(__name__)


class GapAnalysisService:
    """Computes per-plan gap analysis across multiple dimensions."""

    @staticmethod
    def analyze_gaps(
        plan: TrainingPlan,
        user_id: str,
        db: Session,
    ) -> Optional[Dict[str, Any]]:
        """Build a full gap report for a training plan.

        Returns None if there's insufficient data.
        """
        ctx = _load_gap_context(plan, user_id, db, require_runs=True)
        if ctx is None:
            return None

        prediction_data = RacePredictorService.get_predictions_for_user(user_id, db)

        volume_gap = _compute_volume_gap(
            ctx.plan_data, ctx.runs, ctx.start_date, ctx.current_week
        )
        long_run_gap = _compute_long_run_gap(
            ctx.plan_data, ctx.runs, plan.target_distance_km
        )
        pace_gap = _compute_pace_gap(plan, ctx.runs, prediction_data)
        consistency = _compute_consistency(plan, ctx.runs, db, ctx.current_week)
        fitness = _compute_fitness_trajectory(plan, prediction_data)
        elevation_gap = _compute_elevation_gap(
            plan, ctx.plan_data, ctx.runs, ctx.current_week
        )
        mountain_simulation = score_mountain_simulation(
            ctx.plan_data,
            ctx.runs,
            ctx.start_date,
            ctx.current_week,
            is_trail=getattr(plan, "is_trail", False),
            training_terrain=getattr(plan, "training_terrain", None),
            target_elevation_gain_m=getattr(plan, "target_elevation_gain_m", None),
            plan_id=plan.id,
        )

        top_actions = _generate_top_actions(
            volume_gap,
            long_run_gap,
            pace_gap,
            consistency,
            fitness,
            mountain_simulation,
            ctx.current_week,
            ctx.total_weeks,
        )

        return {
            "volume_gap": volume_gap,
            "long_run_gap": long_run_gap,
            "pace_gap": pace_gap,
            "consistency": consistency,
            "fitness_trajectory": fitness,
            "elevation_gap": elevation_gap,
            "mountain_simulation_gap": mountain_simulation,
            "top_actions": top_actions,
            "current_week": ctx.current_week,
            "total_weeks": ctx.total_weeks,
        }

    @staticmethod
    def analyze_gaps_weekly(
        plan: TrainingPlan,
        user_id: str,
        db: Session,
    ) -> Optional[List[Dict[str, Any]]]:
        """Return per-week gap breakpoints for trend charts.

        Each entry contains the week number and % of target achieved
        for volume and long run.
        """
        ctx = _load_gap_context(plan, user_id, db, require_runs=False)
        if ctx is None:
            return None

        weekly_km, weekly_longest = _bucket_runs_by_week(
            ctx.runs,
            ctx.start_date,
            ctx.current_week,
        )

        breakpoints: list[dict] = []
        for wk_data in ctx.plan_data:
            if wk_data.get("week", 0) > ctx.current_week:
                break
            breakpoints.append(_weekly_breakpoint(wk_data, weekly_km, weekly_longest))

        return breakpoints


__all__ = [
    "GapAnalysisService",
    "_compute_volume_gap",
    "_compute_elevation_gap",
    "_compute_long_run_gap",
    "_compute_pace_gap",
    "_compute_consistency",
    "_compute_fitness_trajectory",
    "_generate_top_actions",
    "_load_gap_context",
    "_bucket_runs_by_week",
    "_weekly_breakpoint",
]
