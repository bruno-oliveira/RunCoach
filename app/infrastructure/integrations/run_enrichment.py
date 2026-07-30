"""Derived fields filled in on every imported run, whatever the source.

An activity arrives from a connected platform with distance, duration, HR and
splits, but nothing about how hard the session actually was. These fill in the
values RunCoach reasons with: the run's VDOT, its effort class, and the workout
type inferred from pace/HR/distance/splits.

Every step is best-effort and independently guarded — a classifier that fails
must never cost the runner the import.
"""

import logging

from sqlalchemy.orm import Session

from app.core.training.vdot_calculator import VDOTCalculator
from app.models.run_log import RunLog
from app.models.user import User

logger = logging.getLogger(__name__)

# Below this a run is too short for the VDOT model to say anything useful.
MIN_VDOT_DISTANCE_KM = 2.0


def apply_vdot(run_log: RunLog) -> None:
    """Set the run's VDOT when it is long enough to support one."""
    if run_log.distance_km >= MIN_VDOT_DISTANCE_KM and run_log.duration_minutes > 0:
        vdot = VDOTCalculator.calculate_vdot(
            run_log.distance_km,
            int(run_log.duration_minutes * 60),
            elevation_gain_m=run_log.elevation_gain_m,
        )
        if vdot:
            run_log.vdot = vdot


def classify_effort_and_type(run_log: RunLog, user: User, db: Session) -> None:
    """Infer the run's effort class and workout type from its own signals.

    Imported activities arrive untagged — the platform's own ``workout_type``,
    where it has one, is unreliable. These classifiers recover the real effort
    class and workout type. Each is guarded separately so one failing never
    blocks the other or the import itself.
    """
    try:
        from app.contexts.runner.fitness.effort_classifier import classify_effort

        effort_class = classify_effort(
            distance_km=run_log.distance_km,
            avg_pace_min_km=run_log.avg_pace_min_km,
            perceived_effort=run_log.perceived_effort,
            user_id=user.id,
            db=db,
            exclude_run_id=run_log.id,
        )
        if effort_class is not None:
            run_log.effort_class = effort_class
    except Exception as cls_err:
        logger.warning(
            "Effort classification failed for run %s: %s", run_log.id, cls_err
        )

    try:
        from app.contexts.runner.fitness.workout_type_classifier import (
            classify_workout_type,
        )

        wt_result = classify_workout_type(
            distance_km=run_log.distance_km,
            duration_minutes=run_log.duration_minutes,
            avg_pace_min_km=run_log.avg_pace_min_km,
            avg_heart_rate=run_log.avg_heart_rate,
            max_heart_rate=run_log.max_heart_rate,
            elevation_gain_m=run_log.elevation_gain_m,
            perceived_effort=run_log.perceived_effort,
            splits=run_log.splits,
            vdot=run_log.vdot,
            user_id=user.id,
            db=db,
            exclude_run_id=run_log.id,
        )
        if wt_result is not None:
            (
                run_log.inferred_workout_type,
                run_log.inferred_type_confidence,
            ) = wt_result
    except Exception as cls_err:
        logger.warning(
            "Workout-type inference failed for run %s: %s", run_log.id, cls_err
        )


__all__ = ["apply_vdot", "classify_effort_and_type"]
