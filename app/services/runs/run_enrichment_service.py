"""Run log enrichment: VDOT calculation, prediction snapshots, response building."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.training.vdot_calculator import VDOTCalculator
from app.models import RunLog
from app.schemas import RunLogResponse
from app.services.fitness.race_predictor_service import RacePredictorService

logger = logging.getLogger(__name__)


def enrich_vdot_and_prediction(
    new_run: RunLog, distance_km: float, duration_minutes: float, user_id: str, db: Session
) -> None:
    """Calculate VDOT and snapshot pre-run prediction onto the run."""
    if distance_km >= 2.0 and duration_minutes > 0:
        vdot = VDOTCalculator.calculate_vdot(distance_km, int(duration_minutes * 60))
        if vdot:
            new_run.vdot = vdot

    if distance_km >= 2.0:
        try:
            pre_race_vdot = RacePredictorService.get_best_recent_vdot(user_id, weeks=12, db=db)
            if pre_race_vdot:
                predicted_seconds = VDOTCalculator.predict_time_for_distance(pre_race_vdot, distance_km)
                if predicted_seconds:
                    new_run.predicted_time_seconds = float(predicted_seconds)
        except Exception as e:
            logger.warning(f"Failed to snapshot prediction for run: {e}")


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
        effort_quality_score=round(run.effort_quality_score, 1) if run.effort_quality_score else None,
        quality_label=run.quality_label,
        vdot=run.vdot,
        predicted_time_seconds=run.predicted_time_seconds,
        created_at=run.created_at,
    )
