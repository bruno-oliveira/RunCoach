"""Compute volume, effort, completion, and trend signals for plan adjustment."""

from collections import defaultdict
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models import RunLog
from app.utils import to_date as _to_date

_PHASE_WEIGHTS = {
    "base":   (0.55, 0.25, 0.20),
    "build":  (0.50, 0.30, 0.20),
    "peak":   (0.40, 0.35, 0.25),
    "taper":  (0.20, 0.30, 0.50),
}

_MIN_RUNS_PER_TYPE = 3
_BAYESIAN_SHRINKAGE_PER_RUN = 0.30


def compute_adjustment_signals(
    all_plan_runs: List,
    past_workouts: List[Tuple],
    past_workout_ids: set,
    today,
    plan_id: str,
    db: Session,
    recency_weight_fn,
    *,
    current_phase: str = "build",
) -> Dict[str, Any]:
    volume_weight, effort_weight, completion_weight = _PHASE_WEIGHTS.get(
        current_phase, _PHASE_WEIGHTS["build"],
    )
    planned_weighted = 0.0
    planned_by_type: Dict[str, float] = defaultdict(float)
    for workout, sched_date in past_workouts:
        w = recency_weight_fn(sched_date)
        dist = workout.baseline_distance_km or workout.distance_km or 0
        planned_weighted += dist * w
        wtype = workout.workout_type or "easy"
        planned_by_type[wtype] += dist * w

    actual_weighted = 0.0
    actual_by_type: Dict[str, float] = defaultdict(float)
    for run in all_plan_runs:
        run_date = _to_date(run.date) if run.date else today
        w = recency_weight_fn(run_date)
        dist = run.distance_km or 0
        actual_weighted += dist * w
        rtype = run.workout_type or "easy"
        actual_by_type[rtype] += dist * w

    volume_ratio = max(0.5, min(1.5,
        actual_weighted / planned_weighted if planned_weighted > 0 else 1.0
    ))

    per_type_ratios: Dict[str, float] = {}
    per_type_run_counts: Dict[str, int] = defaultdict(int)
    for run in all_plan_runs:
        rtype = run.workout_type or "easy"
        per_type_run_counts[rtype] += 1

    for wtype in ("easy", "long", "tempo", "interval", "hill"):
        planned = planned_by_type.get(wtype, 0)
        actual = actual_by_type.get(wtype, 0)
        if planned > 0:
            raw_ratio = max(0.5, min(1.5, actual / planned))
            n_runs = per_type_run_counts.get(wtype, 0)
            confidence = min(1.0, n_runs * _BAYESIAN_SHRINKAGE_PER_RUN)
            per_type_ratios[wtype] = round(
                confidence * raw_ratio + (1.0 - confidence) * volume_ratio, 2,
            )

    effort_sum = 0.0
    effort_weight_sum = 0.0
    recent_efforts: List[float] = []
    for run in all_plan_runs:
        if run.perceived_effort is not None:
            run_date = _to_date(run.date) if run.date else today
            w = recency_weight_fn(run_date)
            effort_sum += run.perceived_effort * w
            effort_weight_sum += w
            recent_efforts.append(run.perceived_effort)

    if effort_weight_sum > 0:
        avg_effort = effort_sum / effort_weight_sum
        effort_factor = max(0.85, min(1.10, 1.10 - (avg_effort - 1.0) * (0.25 / 9.0)))
    else:
        effort_factor = 1.0
        avg_effort = None

    effort_trend = _compute_effort_trend(recent_efforts)
    trend_modifier = {
        "increasing": -0.03,
        "decreasing": +0.02,
        "stable": 0.0,
        "insufficient_data": 0.0,
    }.get(effort_trend, 0.0)

    completed_ids = set()
    if past_workout_ids:
        completed_rows = (
            db.query(RunLog.daily_workout_id)
            .filter(
                RunLog.training_plan_id == plan_id,
                RunLog.daily_workout_id.in_(past_workout_ids),
            )
            .all()
        )
        completed_ids = {row[0] for row in completed_rows}

    scheduled_weighted = 0.0
    completed_weighted = 0.0
    for workout, sched_date in past_workouts:
        w = recency_weight_fn(sched_date)
        scheduled_weighted += w
        if workout.id in completed_ids:
            completed_weighted += w

    completion_rate = (
        completed_weighted / scheduled_weighted
        if scheduled_weighted > 0 else 0.0
    )

    if completion_rate >= 0.9:
        completion_factor = 1.05
    elif completion_rate >= 0.7:
        completion_factor = 1.00
    elif completion_rate >= 0.5:
        completion_factor = 0.95
    else:
        completion_factor = 0.90

    raw_multiplier = (
        (volume_ratio * volume_weight)
        + (effort_factor * effort_weight)
        + (completion_factor * completion_weight)
    )

    raw_multiplier += trend_modifier

    overreach_detected = False
    if volume_ratio > 1.2 and avg_effort is not None and avg_effort > 8.0:
        raw_multiplier = min(raw_multiplier, 0.88)
        overreach_detected = True

    multiplier = round(max(0.85, min(1.15, raw_multiplier)), 2)

    return {
        "multiplier": multiplier,
        "volume_ratio": round(volume_ratio, 2),
        "effort_factor": round(effort_factor, 2),
        "avg_effort": round(avg_effort, 1) if avg_effort is not None else None,
        "effort_trend": effort_trend,
        "completion_rate": round(completion_rate, 2),
        "completion_factor": round(completion_factor, 2),
        "raw_multiplier": round(raw_multiplier, 3),
        "trend_modifier": round(trend_modifier, 3),
        "overreach_detected": overreach_detected,
        "per_type_ratios": {k: round(v, 2) for k, v in per_type_ratios.items()},
        "phase_weights": {
            "volume": round(volume_weight, 2),
            "effort": round(effort_weight, 2),
            "completion": round(completion_weight, 2),
        },
        "current_phase": current_phase,
    }


def _compute_effort_trend(efforts: List[float]) -> str:
    if len(efforts) < 4:
        return "insufficient_data"
    mid_point = len(efforts) // 2
    first_half_avg = sum(efforts[:mid_point]) / mid_point
    second_half_avg = sum(efforts[mid_point:]) / (len(efforts) - mid_point)
    diff = second_half_avg - first_half_avg
    if diff > 1.0:
        return "increasing"
    elif diff < -1.0:
        return "decreasing"
    return "stable"
