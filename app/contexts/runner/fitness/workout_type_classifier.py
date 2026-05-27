"""Infer a run's workout_type from its signals.

Strava rarely sets ``workout_type``; the sync mapper defaults the blank to
"easy", so tempo, interval, and long sessions all masquerade as easy and
poison every consumer that reads ``workout_type`` (adaptation volume ratios,
coaching patterns, profile counts, zone recalibration).

This resolves the runner's own VDOT pace zones, HR zones, and distance
distribution, then defers to the pure ``app.core.training.workout_inference``
math to decide the type. Writes go to the dedicated ``inferred_workout_type``
column; the raw tag is left untouched and reconciled at read time by
``RunLog.effective_workout_type``.

Mirror of ``effort_classifier.py`` in shape (per-user, db-backed, with a
backfill), but on the workout-type axis rather than the effort axis.
"""

from __future__ import annotations

import logging
import statistics
from typing import Optional

from sqlalchemy.orm import Session

from app.contexts.runner.fitness.hr_zone_service import get_user_max_hr
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.core.training.hr_zone_calculator import HRZoneCalculator
from app.core.training.vdot_calculator import TRAIL_ELEVATION_M_PER_KM, VDOTCalculator
from app.core.training.workout_inference import (
    combine,
    hr_to_tier,
    pace_to_tier,
    splits_variability,
)
from app.models import RunLog

logger = logging.getLogger(__name__)

# A run is "long" when it's clearly longer than the runner's typical outing or
# simply long in absolute terms. The relative test scales to the runner (a 10K
# is a long run for someone whose median is 5K); the duration floor catches a
# first long run before there's enough history to compare against.
_LONG_RUN_DISTANCE_MULTIPLE = 1.5
_LONG_RUN_MIN_DURATION_MIN = 75.0
_LONG_RUN_MIN_SAMPLE = 5


def _recent_distances(
    user_id: str, db: Session, exclude_run_id: Optional[str]
) -> list[float]:
    """Return the user's logged run distances (km), excluding the given run."""
    query = db.query(RunLog.distance_km).filter(
        RunLog.user_id == user_id,
        RunLog.distance_km.isnot(None),
        RunLog.distance_km > 0,
    )
    if exclude_run_id is not None:
        query = query.filter(RunLog.id != exclude_run_id)
    return [d for (d,) in query.all()]


def _is_long_run(
    distance_km: float,
    duration_minutes: Optional[float],
    user_id: str,
    db: Session,
    exclude_run_id: Optional[str],
) -> bool:
    """Whether this run reads as a long run for this runner."""
    if duration_minutes and duration_minutes >= _LONG_RUN_MIN_DURATION_MIN:
        return True
    distances = _recent_distances(user_id, db, exclude_run_id)
    if len(distances) < _LONG_RUN_MIN_SAMPLE:
        return False
    return distance_km >= _LONG_RUN_DISTANCE_MULTIPLE * statistics.median(distances)


def _resolve_max_hr(
    avg_heart_rate: Optional[int],
    run_max_heart_rate: Optional[int],
    user_id: str,
    db: Session,
) -> Optional[int]:
    """Best max-HR ceiling for zone classification, or None to skip HR.

    Prefers a detected/estimated max HR; supplements it with this run's own max
    when higher (so zones aren't compressed). The universal 190 default is too
    coarse to classify against, so HR is skipped when that's all we have and
    the run carries no max of its own.
    """
    detected, source = get_user_max_hr(user_id, db)
    if source != "default":
        if run_max_heart_rate and run_max_heart_rate > detected:
            return run_max_heart_rate
        return detected
    # Only the generic default is available.
    return run_max_heart_rate or None


def classify_workout_type(
    *,
    distance_km: Optional[float],
    duration_minutes: Optional[float],
    avg_pace_min_km: Optional[float],
    avg_heart_rate: Optional[int],
    max_heart_rate: Optional[int],
    elevation_gain_m: Optional[int],
    perceived_effort: Optional[int],
    splits: Optional[list] = None,
    vdot: Optional[float] = None,
    user_id: str,
    db: Session,
    exclude_run_id: Optional[str] = None,
) -> Optional[tuple[str, float]]:
    """Infer ``(workout_type, confidence)`` for a run, or None if no signal.

    Resolves the runner's pace zones (from ``vdot`` or their recent best) and
    HR zones (from their max HR), classifies the average pace and HR into
    intensity tiers, refines tempo-vs-interval with split variance when splits
    are present, and applies long-run / hilly context. Degrades gracefully:
    with neither a usable pace nor HR signal it returns None and the caller
    keeps the raw tag.
    """
    if not distance_km or distance_km <= 0:
        return None

    # Pace zones: prefer this run's own VDOT, fall back to the recent best.
    pace_tier = None
    resolved_vdot = vdot
    if resolved_vdot is None:
        try:
            resolved_vdot = RacePredictorService.get_best_recent_vdot(user_id, db=db)
        except Exception:  # pragma: no cover - defensive
            resolved_vdot = None
    if resolved_vdot and avg_pace_min_km:
        pace_tier = pace_to_tier(
            avg_pace_min_km, VDOTCalculator.get_pace_zones(resolved_vdot)
        )

    # HR zones from the runner's max HR.
    hr_tier = None
    if avg_heart_rate:
        max_hr = _resolve_max_hr(avg_heart_rate, max_heart_rate, user_id, db)
        if max_hr:
            hr_tier = hr_to_tier(
                avg_heart_rate, HRZoneCalculator.calculate_zones(max_hr)
            )

    hilly = bool(
        elevation_gain_m
        and distance_km > 0
        and elevation_gain_m / distance_km >= TRAIL_ELEVATION_M_PER_KM
    )
    is_long = _is_long_run(distance_km, duration_minutes, user_id, db, exclude_run_id)
    splits_cv = splits_variability(splits)[0] if splits else None

    return combine(
        pace_tier,
        hr_tier,
        splits_cv=splits_cv,
        is_long=is_long,
        hilly=hilly,
        perceived_effort=perceived_effort,
    )


def backfill_inferred_workout_types(db: Session, *, batch_size: int = 500) -> int:
    """Populate inferred_workout_type for runs that don't have one.

    Classifies from stored averages (historical runs have no splits) -- still a
    large improvement over the all-"easy" default. Iterates user-by-user so
    each run is judged against its own distribution. Returns the count updated.
    """
    updated = 0
    user_ids = [uid for (uid,) in db.query(RunLog.user_id).distinct().all()]
    for user_id in user_ids:
        runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.inferred_workout_type.is_(None),
                RunLog.distance_km > 0,
            )
            .order_by(RunLog.date.asc())
            .all()
        )
        for run in runs:
            try:
                result = classify_workout_type(
                    distance_km=run.distance_km,
                    duration_minutes=run.duration_minutes,
                    avg_pace_min_km=run.avg_pace_min_km,
                    avg_heart_rate=run.avg_heart_rate,
                    max_heart_rate=run.max_heart_rate,
                    elevation_gain_m=run.elevation_gain_m,
                    perceived_effort=run.perceived_effort,
                    splits=run.splits,
                    vdot=run.vdot,
                    user_id=user_id,
                    db=db,
                    exclude_run_id=run.id,
                )
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("Workout-type backfill failed for run %s: %s", run.id, e)
                result = None
            if result is not None:
                run.inferred_workout_type, run.inferred_type_confidence = result
                updated += 1
            if updated and updated % batch_size == 0:
                db.flush()
    db.flush()
    return updated
