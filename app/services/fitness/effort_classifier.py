"""Derive an effort class for a run from observable signals.

`workout_type` is the user-tagged label and in practice is dead weight: most
Strava activities arrive with `type=Run` / no workout flag, and most users
never tag manually-logged runs as race/tempo either. So almost every VDOT
candidate ends up with effort_weight 0.7 (the "easy" weight) -- the very
distinction VDOT estimation cares about (race vs. easy effort) is collapsed.

This classifier ignores the tag and infers an `effort_class` from:
  * pace percentile against the user's own distribution at similar distance
  * perceived effort, when the user supplied it

Returns one of `race_effort`, `tempo_effort`, `easy_effort`, or None when
there's not enough signal to commit either way (caller should leave the
tag-based fallback in place).
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import RunLog

logger = logging.getLogger(__name__)

EFFORT_RACE = "race_effort"
EFFORT_TEMPO = "tempo_effort"
EFFORT_EASY = "easy_effort"

# A run only counts toward the user's distribution if its distance is within
# +/-50% of the run being classified. A 5K time-trial shouldn't be ranked
# against marathon long runs and vice versa.
_DISTANCE_BAND = 0.5

# Minimum prior runs at similar distance before pace percentile is meaningful.
# Tunes against the "first hard 10K classified as race effort because there
# were no prior 10Ks" failure mode.
_MIN_SAMPLE = 5

# Pace percentile thresholds. Lower percentile = faster pace.
_RACE_PACE_PERCENTILE = 0.10  # top 10% fastest -> race_effort
_TEMPO_PACE_PERCENTILE = 0.25  # top 25% fastest -> tempo_effort

# Perceived-effort thresholds. PE is 1-10; >= 9 reads as "couldn't have gone
# harder", >= 7 reads as a tempo-grade hard effort.
_RACE_PE_THRESHOLD = 9
_TEMPO_PE_THRESHOLD = 7


def _similar_distance_paces(
    user_id: str,
    distance_km: float,
    db: Session,
    *,
    exclude_run_id: Optional[str] = None,
) -> list[float]:
    """Return paces (min/km) from the user's prior runs at similar distance."""
    low = distance_km * (1 - _DISTANCE_BAND)
    high = distance_km * (1 + _DISTANCE_BAND)
    query = (
        db.query(RunLog.avg_pace_min_km)
        .filter(
            RunLog.user_id == user_id,
            RunLog.distance_km >= low,
            RunLog.distance_km <= high,
            RunLog.avg_pace_min_km.isnot(None),
            RunLog.avg_pace_min_km > 0,
        )
    )
    if exclude_run_id is not None:
        query = query.filter(RunLog.id != exclude_run_id)
    return [pace for (pace,) in query.all()]


def classify_effort(
    *,
    distance_km: float,
    avg_pace_min_km: Optional[float],
    perceived_effort: Optional[int],
    user_id: str,
    db: Session,
    exclude_run_id: Optional[str] = None,
) -> Optional[str]:
    """Classify a run's effort class.

    Strategy:
      1. If perceived_effort >= 9, return race_effort directly. The user told us.
      2. Otherwise, look at pace percentile vs. similar-distance history.
      3. If there's no pace or fewer than _MIN_SAMPLE prior runs at similar
         distance, fall back to perceived effort (>=7 -> tempo) or return None.

    Args:
        exclude_run_id: when re-classifying an existing run, exclude it from
            its own distribution so it isn't compared against itself.
    """
    if perceived_effort is not None and perceived_effort >= _RACE_PE_THRESHOLD:
        return EFFORT_RACE

    if avg_pace_min_km is None or avg_pace_min_km <= 0:
        if perceived_effort is not None and perceived_effort >= _TEMPO_PE_THRESHOLD:
            return EFFORT_TEMPO
        return None

    prior_paces = _similar_distance_paces(
        user_id, distance_km, db, exclude_run_id=exclude_run_id
    )
    if len(prior_paces) < _MIN_SAMPLE:
        # Pace alone isn't enough; lean on PE if it's strong.
        if perceived_effort is not None and perceived_effort >= _TEMPO_PE_THRESHOLD:
            return EFFORT_TEMPO
        return None

    sorted_paces = sorted(prior_paces)
    rank = sum(1 for p in sorted_paces if p < avg_pace_min_km)
    percentile = rank / len(sorted_paces)

    if percentile <= _RACE_PACE_PERCENTILE:
        return EFFORT_RACE
    if percentile <= _TEMPO_PACE_PERCENTILE:
        return EFFORT_TEMPO

    # Anything slower than the top quartile against the user's own pace
    # distribution at this distance is, by definition, an easy/steady run.
    return EFFORT_EASY


def backfill_effort_classes(db: Session, *, batch_size: int = 500) -> int:
    """Populate effort_class for existing runs that don't have one.

    Iterates user-by-user so each run is classified against its user's own
    distribution. Returns the number of runs updated.
    """
    updated = 0
    user_ids = [
        uid for (uid,) in db.query(RunLog.user_id).distinct().all()
    ]
    for user_id in user_ids:
        runs = (
            db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.effort_class.is_(None),
                RunLog.distance_km > 0,
            )
            .order_by(RunLog.date.asc())
            .all()
        )
        for run in runs:
            effort = classify_effort(
                distance_km=run.distance_km,
                avg_pace_min_km=run.avg_pace_min_km,
                perceived_effort=run.perceived_effort,
                user_id=user_id,
                db=db,
                exclude_run_id=run.id,
            )
            if effort is not None:
                run.effort_class = effort
                updated += 1
            if updated % batch_size == 0 and updated > 0:
                db.flush()
    db.flush()
    return updated
