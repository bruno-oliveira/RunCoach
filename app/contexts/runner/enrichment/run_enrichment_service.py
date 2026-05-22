"""Run log enrichment: VDOT calculation, prediction snapshots, response building."""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.contexts.runner.fitness.effort_classifier import classify_effort
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.contexts.runner.queries import count_prior_trail_runs
from app.core.training.vdot_calculator import VDOTCalculator
from app.models import RunLog
from app.schemas import RunLogResponse

logger = logging.getLogger(__name__)

# Quality workouts that justify recomputing the user's fitness baseline.
_RECALIBRATION_WORKOUT_TYPES = frozenset(
    {"tempo", "long", "race", "vo2max", "interval"}
)


def enrich_vdot_and_prediction(
    new_run: RunLog,
    distance_km: float,
    duration_minutes: float,
    user_id: str,
    db: Session,
) -> Optional[Dict[str, Any]]:
    """Calculate VDOT, derive effort class, snapshot prediction, and optionally recalibrate plan zones.

    Returns the VDOT recalibration result dict if this run triggered a pace-zone refresh, else None.
    """
    try:
        effort_class = classify_effort(
            distance_km=distance_km,
            avg_pace_min_km=new_run.avg_pace_min_km,
            perceived_effort=new_run.perceived_effort,
            user_id=user_id,
            db=db,
            exclude_run_id=new_run.id,
        )
        if effort_class is not None:
            new_run.effort_class = effort_class
    except Exception as e:
        logger.warning(f"Failed to classify effort for run: {e}")

    if distance_km >= 2.0 and duration_minutes > 0:
        vdot = VDOTCalculator.calculate_vdot(
            distance_km,
            int(duration_minutes * 60),
            elevation_gain_m=new_run.elevation_gain_m,
        )
        if vdot:
            new_run.vdot = vdot

    if distance_km >= 2.0:
        try:
            pre_race_vdot = RacePredictorService.get_best_recent_vdot(
                user_id, weeks=12, db=db
            )
            if pre_race_vdot:
                trail_runs_count = None
                if new_run.elevation_gain_m and new_run.elevation_gain_m > 0:
                    trail_runs_count = count_prior_trail_runs(user_id, db)
                endurance_factor = RacePredictorService.compute_endurance_factor(
                    user_id, distance_km, db, current_vdot=pre_race_vdot
                )
                predicted_seconds = VDOTCalculator.predict_time_for_distance(
                    pre_race_vdot,
                    distance_km,
                    elevation_gain_m=new_run.elevation_gain_m,
                    trail_runs_count=trail_runs_count,
                    endurance_factor=endurance_factor,
                )
                if predicted_seconds:
                    new_run.predicted_time_seconds = float(predicted_seconds)
        except Exception as e:
            logger.warning(f"Failed to snapshot prediction for run: {e}")

    return _maybe_recalibrate_plan_zones(new_run, user_id, db)


def _maybe_recalibrate_plan_zones(
    new_run: RunLog, user_id: str, db: Session
) -> Optional[Dict[str, Any]]:
    """Trigger pace-zone recalibration for the run's plan when this was a quality session."""
    if not new_run.training_plan_id:
        return None

    workout_type = (new_run.workout_type or "").lower()
    effort_class = (new_run.effort_class or "").lower()
    if (
        workout_type not in _RECALIBRATION_WORKOUT_TYPES
        and effort_class != "race_effort"
    ):
        return None

    try:
        plan = SQLAlchemyPlanRepository(db).get_for_user(
            new_run.training_plan_id, user_id
        )
        if not plan:
            return None
        from app.contexts.plan.adaptation.vdot_recalibrator import (
            recalibrate_zones_only,
        )

        return recalibrate_zones_only(plan, user_id, db)
    except Exception as e:
        logger.warning(f"Per-run VDOT recalibration failed: {e}", exc_info=True)
        return None


def build_race_comparison(run: RunLog, duration_minutes: float) -> Optional[dict]:
    """Build predicted vs actual comparison dict if prediction data is available."""
    if not run.predicted_time_seconds:
        return None
    actual_seconds = int(duration_minutes * 60)
    predicted_seconds = int(run.predicted_time_seconds)
    delta = actual_seconds - predicted_seconds
    return {
        "predicted_seconds": predicted_seconds,
        "predicted_formatted": VDOTCalculator.format_duration(predicted_seconds),
        "actual_seconds": actual_seconds,
        "actual_formatted": VDOTCalculator.format_duration(actual_seconds),
        "delta_seconds": delta,
        "delta_formatted": VDOTCalculator.format_duration(abs(delta)),
        "faster_than_predicted": delta < 0,
    }


def run_to_response(run: RunLog) -> RunLogResponse:
    """Convert a RunLog model instance to a RunLogResponse schema."""
    return RunLogResponse(
        id=run.id,
        date=run.date,
        distance_km=run.distance_km,
        duration_minutes=run.duration_minutes,
        avg_pace_min_km=round(run.avg_pace_min_km, 2) if run.avg_pace_min_km else None,
        avg_heart_rate=run.avg_heart_rate,
        max_heart_rate=run.max_heart_rate,
        avg_cadence=run.avg_cadence,
        elevation_gain_m=run.elevation_gain_m,
        notes=run.notes,
        workout_type=run.workout_type,
        perceived_effort=run.perceived_effort,
        effort_quality_score=round(run.effort_quality_score, 1)
        if run.effort_quality_score
        else None,
        quality_label=run.quality_label,
        vdot=run.vdot,
        predicted_time_seconds=run.predicted_time_seconds,
        created_at=run.created_at,
    )
