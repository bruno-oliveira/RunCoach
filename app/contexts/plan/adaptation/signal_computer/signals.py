"""Independent per-signal computers, each returning a SignalContribution.

Each ``_*_signal`` helper isolates one adjustment dimension (volume, effort,
HR-zone, feedback, readiness, completion) so they can evolve independently.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.contexts.plan.adaptation.hr_zone_analyzer import HRZoneAnalyzer
from app.contexts.plan.adaptation.signal_computer.context import SignalContribution
from app.contexts.plan.adaptation.tuning import (
    BAYESIAN_SHRINKAGE_PER_RUN as _BAYESIAN_SHRINKAGE_PER_RUN,
)
from app.contexts.plan.adaptation.tuning import (
    IMPORTANCE_WEIGHTS as _IMPORTANCE_WEIGHTS,
)
from app.contexts.plan.adaptation.tuning import (
    READINESS_MIN_LOGS,
    READINESS_TSB_FRESH,
    READINESS_TSB_FRESH_FACTOR,
    READINESS_TSB_LOADED,
    READINESS_TSB_LOADED_FACTOR,
    READINESS_TSB_OVERLOADED,
    READINESS_TSB_OVERLOADED_FACTOR,
)
from app.core.coaching.adaptation_math import (
    compute_effort_trend as _compute_effort_trend,
)
from app.core.coaching.adaptation_math import (
    compute_quality_drift as _compute_quality_drift,
)
from app.core.coaching.adaptation_math import (
    count_recent_race_efforts as _count_recent_race_efforts,
)
from app.models import RunLog
from app.utils import to_date as _to_date


def _volume_signal(
    past_workouts,
    all_plan_runs,
    recency_weight_fn,
    today,
    weight,
) -> SignalContribution:
    planned_weighted = 0.0
    planned_by_type: Dict[str, float] = defaultdict(float)
    for workout, sched_date in past_workouts:
        w = recency_weight_fn(sched_date)
        dist = workout.baseline_distance_km or workout.distance_km or 0
        wtype = workout.workout_type or "easy"
        importance = _IMPORTANCE_WEIGHTS.get(wtype, 1.0)
        planned_weighted += dist * w * importance
        planned_by_type[wtype] += dist * w * importance

    actual_weighted = 0.0
    actual_by_type: Dict[str, float] = defaultdict(float)
    for run in all_plan_runs:
        run_date = _to_date(run.date) if run.date else today
        w = recency_weight_fn(run_date)
        dist = run.distance_km or 0
        rtype = run.effective_workout_type or "easy"
        importance = _IMPORTANCE_WEIGHTS.get(rtype, 1.0)
        actual_weighted += dist * w * importance
        actual_by_type[rtype] += dist * w * importance

    volume_ratio = max(
        0.5,
        min(
            1.5,
            actual_weighted / planned_weighted if planned_weighted > 0 else 1.0,
        ),
    )

    per_type_run_counts: Dict[str, int] = defaultdict(int)
    for run in all_plan_runs:
        per_type_run_counts[run.effective_workout_type or "easy"] += 1

    per_type_ratios: Dict[str, float] = {}
    for wtype in ("easy", "long", "tempo", "interval", "hill"):
        planned = planned_by_type.get(wtype, 0)
        actual = actual_by_type.get(wtype, 0)
        if planned > 0:
            raw_ratio = max(0.5, min(1.5, actual / planned))
            n_runs = per_type_run_counts.get(wtype, 0)
            confidence = min(1.0, n_runs * _BAYESIAN_SHRINKAGE_PER_RUN)
            per_type_ratios[wtype] = round(
                confidence * raw_ratio + (1.0 - confidence) * volume_ratio,
                2,
            )

    return SignalContribution(
        factor=volume_ratio,
        weight=weight,
        extras={
            "volume_ratio": volume_ratio,
            "per_type_ratios": per_type_ratios,
        },
    )


def _effort_signal(
    all_plan_runs,
    recency_weight_fn,
    today,
    weight,
) -> SignalContribution:
    effort_sum = 0.0
    effort_weight_sum = 0.0
    dated_efforts: List[tuple] = []
    for run in all_plan_runs:
        if run.perceived_effort is not None:
            run_date = _to_date(run.date) if run.date else today
            w = recency_weight_fn(run_date)
            effort_sum += run.perceived_effort * w
            effort_weight_sum += w
            dated_efforts.append((run_date, run.perceived_effort))

    # Sort chronologically so the first/second-half trend split is meaningful
    # regardless of the order the runs were fetched in (DB rowid order, Strava
    # backfill, and edited dates can otherwise invert the trend).
    dated_efforts.sort(key=lambda t: t[0])
    recent_efforts: List[float] = [e for _, e in dated_efforts]

    if effort_weight_sum > 0:
        avg_effort = effort_sum / effort_weight_sum
        effort_factor = max(0.85, min(1.10, 1.10 - (avg_effort - 1.0) * (0.25 / 9.0)))
    else:
        avg_effort = None
        effort_factor = 1.0

    effort_trend = _compute_effort_trend(recent_efforts)
    trend_modifier = {
        "increasing": -0.03,
        "decreasing": +0.02,
    }.get(effort_trend, 0.0)

    quality_drift, quality_drift_modifier = _compute_quality_drift(
        all_plan_runs,
        today,
    )
    recent_race_effort_count = _count_recent_race_efforts(all_plan_runs, today)

    return SignalContribution(
        factor=effort_factor,
        weight=weight,
        extras={
            "avg_effort": avg_effort,
            "effort_trend": effort_trend,
            "effort_factor": effort_factor,
            "trend_modifier": trend_modifier,
            "quality_drift": quality_drift,
            "quality_drift_modifier": quality_drift_modifier,
            "recent_race_effort_count": recent_race_effort_count,
        },
    )


def _hr_signal(
    all_plan_runs,
    hr_zones,
    recency_weight_fn,
    today,
    weight,
) -> SignalContribution:
    hr_result = HRZoneAnalyzer.analyze_runs(
        all_plan_runs,
        hr_zones,
        recency_weight_fn=recency_weight_fn,
        today=today,
    )
    avg_zone_deviation = hr_result["avg_deviation"]
    hr_zone_adherence = hr_result["adherence_rate"]
    hr_zone_trend = hr_result["trend"]

    if avg_zone_deviation >= 1.5:
        hr_zone_factor = 0.90
    elif avg_zone_deviation >= 1.0:
        hr_zone_factor = 0.95
    elif avg_zone_deviation <= -1.0:
        hr_zone_factor = 1.05
    elif avg_zone_deviation <= -0.5:
        hr_zone_factor = 1.02
    else:
        hr_zone_factor = 1.0

    has_data = hr_zones is not None and hr_result["run_count"] > 0
    if not has_data:
        hr_zone_factor = 1.0

    return SignalContribution(
        factor=hr_zone_factor,
        weight=weight,
        has_data=has_data,
        extras={
            "hr_zone_factor": hr_zone_factor,
            "hr_zone_adherence": hr_zone_adherence,
            "avg_zone_deviation": avg_zone_deviation,
            "hr_zone_trend": hr_zone_trend,
            "avg_abs_deviation": hr_result.get("avg_abs_deviation", 0),
        },
    )


def _feedback_signal(
    run_feedback_list,
    all_plan_runs,
    recency_weight_fn,
    today,
    weight,
) -> SignalContribution:
    if not run_feedback_list:
        return SignalContribution(
            factor=1.0,
            weight=weight,
            extras={
                "warning_ratio": 0.0,
                "positive_ratio": 0.0,
                "feedback_factor": 1.0,
            },
        )

    warning_weighted = 0.0
    positive_weighted = 0.0
    total_weighted = 0.0
    for fb in run_feedback_list:
        run_date = None
        for run in all_plan_runs:
            if run.id == fb.run_log_id:
                run_date = _to_date(run.date) if run.date else today
                break
        w = recency_weight_fn(run_date) if run_date else 1.0
        total_weighted += w
        if fb.overall_sentiment == "warning":
            warning_weighted += w
        elif fb.overall_sentiment == "positive":
            positive_weighted += w

    if total_weighted > 0:
        warning_ratio = warning_weighted / total_weighted
        positive_ratio = positive_weighted / total_weighted
        if warning_ratio > 0.6:
            feedback_factor = 0.92
        elif warning_ratio > 0.4:
            feedback_factor = 0.96
        elif positive_ratio > 0.6:
            feedback_factor = 1.05
        elif positive_ratio > 0.4:
            feedback_factor = 1.02
        else:
            feedback_factor = 1.0
    else:
        feedback_factor = 1.0
        warning_ratio = 0.0
        positive_ratio = 0.0

    return SignalContribution(
        factor=feedback_factor,
        weight=weight,
        extras={
            "warning_ratio": warning_ratio,
            "positive_ratio": positive_ratio,
            "feedback_factor": feedback_factor,
        },
    )


def _tsb_from_training_load(training_load) -> Optional[float]:
    if training_load and training_load.get("available"):
        return (training_load.get("current") or {}).get("tsb")
    return None


def _readiness_factor_from_tsb(tsb: float) -> float:
    """Map training-load form (TSB) to a mild readiness factor.

    Positive form (rested) nudges up; accumulated fatigue nudges down. Bounded
    to a narrow band so it complements — rather than fights — the firmer
    extreme-TSB clamp in ``apply_clamps``.
    """
    if tsb >= READINESS_TSB_FRESH:
        return READINESS_TSB_FRESH_FACTOR
    if tsb <= READINESS_TSB_OVERLOADED:
        return READINESS_TSB_OVERLOADED_FACTOR
    if tsb <= READINESS_TSB_LOADED:
        return READINESS_TSB_LOADED_FACTOR
    return 1.0


def _readiness_signal(readiness_logs, training_load, weight) -> SignalContribution:
    count = len(readiness_logs) if readiness_logs else 0
    source = "none"
    if count >= READINESS_MIN_LOGS:
        scores = [getattr(log, "score", 0) or 0 for log in readiness_logs]
        readiness_pct = (sum(scores) / len(scores)) / 100.0
        readiness_pct = max(0.0, min(1.0, readiness_pct))
        readiness_factor = 0.92 + readiness_pct * 0.13
        has_data = True
        source = "logs"
    else:
        # Fallback: derive readiness from objective training-load form (TSB) so
        # the signal still contributes for the ~all users who never self-report
        # readiness, instead of silently folding its weight onto other signals.
        tsb = _tsb_from_training_load(training_load)
        if tsb is not None:
            readiness_factor = _readiness_factor_from_tsb(tsb)
            has_data = True
            source = "tsb"
        else:
            readiness_factor = 1.0
            has_data = False

    return SignalContribution(
        factor=readiness_factor,
        weight=weight,
        has_data=has_data,
        extras={
            "readiness_factor": readiness_factor,
            "readiness_log_count": count,
            "readiness_source": source,
        },
    )


def _mountain_factor(
    mountain_simulation: Optional[Dict[str, Any]],
) -> Tuple[float, Dict[str, Any]]:
    """Compute the mountain-from-flat proxy factor.

    Returns ``(factor, extras)``. The factor is multiplied directly into
    ``raw_multiplier`` rather than weighted, so it stays out of the linear
    combination and leaves phase weights unchanged for non-trail plans.
    """
    if mountain_simulation is None:
        return 1.0, {
            "mountain_simulation_score": None,
            "mountain_simulation_factor": 1.0,
        }
    score = float(mountain_simulation.get("score", 0) or 0)
    if score >= 85:
        factor = 1.03
    elif score >= 70:
        factor = 1.00
    elif score >= 55:
        factor = 0.97
    else:
        factor = 0.93
    return factor, {
        "mountain_simulation_score": score,
        "mountain_simulation_factor": factor,
    }


def _completion_signal(
    past_workouts,
    past_workout_ids,
    plan_id,
    db,
    recency_weight_fn,
    weight,
) -> SignalContribution:
    completed_ids: set = set()
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
        # Distance-0 days (e.g. a typed "recovery" placeholder) can't be
        # completed with a logged run, so counting them as scheduled would
        # structurally cap completion below 1.0 even for a perfect adherent.
        if not getattr(workout, "distance_km", None) or workout.distance_km <= 0:
            continue
        w = recency_weight_fn(sched_date)
        scheduled_weighted += w
        if workout.id in completed_ids:
            completed_weighted += w

    completion_rate = (
        completed_weighted / scheduled_weighted if scheduled_weighted > 0 else 0.0
    )
    completion_factor = 0.90 + 0.15 * completion_rate

    return SignalContribution(
        factor=completion_factor,
        weight=weight,
        extras={
            "completion_rate": completion_rate,
            "completion_factor": completion_factor,
        },
    )
