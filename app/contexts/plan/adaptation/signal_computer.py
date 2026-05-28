"""Compute volume, effort, completion, and trend signals for plan adjustment.

Top-level entry point :func:`compute_adjustment_signals` is a thin dispatcher.
Each independent signal lives in its own ``_*_signal`` helper returning a
:class:`SignalContribution` so they can evolve in isolation.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.contexts.plan.adaptation.hr_zone_analyzer import HRZoneAnalyzer

# Tunables live in the centralized adaptation tuning surface; aliased to the
# historical underscore names so internal usages and tests are unchanged.
from app.contexts.plan.adaptation.tuning import (
    BAYESIAN_SHRINKAGE_PER_RUN as _BAYESIAN_SHRINKAGE_PER_RUN,
)
from app.contexts.plan.adaptation.tuning import (
    CONSECUTIVE_THRESHOLD as _CONSECUTIVE_THRESHOLD,
)
from app.contexts.plan.adaptation.tuning import EXPANDED_MAX as _EXPANDED_MAX
from app.contexts.plan.adaptation.tuning import EXPANDED_MIN as _EXPANDED_MIN
from app.contexts.plan.adaptation.tuning import (
    IMPORTANCE_WEIGHTS as _IMPORTANCE_WEIGHTS,
)
from app.contexts.plan.adaptation.tuning import (
    MIN_RUNS_PER_TYPE as _MIN_RUNS_PER_TYPE,  # noqa: F401  (re-exported for tests)
)
from app.contexts.plan.adaptation.tuning import (
    OVERREACH_OVERRIDE_CLAMP,
)
from app.contexts.plan.adaptation.tuning import PHASE_WEIGHTS as _PHASE_WEIGHTS
from app.contexts.plan.adaptation.tuning import STANDARD_MAX as _STANDARD_MAX
from app.contexts.plan.adaptation.tuning import STANDARD_MIN as _STANDARD_MIN
from app.core.coaching.adaptation_math import (
    compute_effort_trend as _compute_effort_trend,
)
from app.core.coaching.adaptation_math import (
    compute_quality_drift as _compute_quality_drift,
)
from app.core.coaching.adaptation_math import (
    count_consecutive_direction as _count_consecutive_direction,
)
from app.core.coaching.adaptation_math import (
    count_recent_race_efforts as _count_recent_race_efforts,
)
from app.models import RunLog
from app.utils import to_date as _to_date


@dataclass
class SignalContribution:
    """One signal's contribution to the final multiplier.

    ``factor`` is the signal's raw factor (e.g. 0.95, 1.05). ``weight`` is the
    base phase weight; the orchestrator may redistribute it onto data-bearing
    signals when ``has_data`` is False. ``extras`` carries signal-specific
    debug fields merged into the final result dict.
    """

    factor: float
    weight: float
    has_data: bool = True
    extras: Dict[str, Any] = field(default_factory=dict)


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
    adaptation_history: List[Dict[str, Any]] | None = None,
    hr_zones: Optional[list[dict]] = None,
    run_feedback_list: Optional[List] = None,
    vdot_trend: str = "stable",
    mountain_simulation: Optional[Dict[str, Any]] = None,
    readiness_logs: Optional[List] = None,
    training_load: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    (vw, ew, cw, hw, fw, rw) = _PHASE_WEIGHTS.get(
        current_phase, _PHASE_WEIGHTS["build"]
    )

    volume = _volume_signal(past_workouts, all_plan_runs, recency_weight_fn, today, vw)
    effort = _effort_signal(all_plan_runs, recency_weight_fn, today, ew)
    completion = _completion_signal(
        past_workouts,
        past_workout_ids,
        plan_id,
        db,
        recency_weight_fn,
        cw,
    )
    hr = _hr_signal(all_plan_runs, hr_zones, recency_weight_fn, today, hw)
    feedback = _feedback_signal(
        run_feedback_list,
        all_plan_runs,
        recency_weight_fn,
        today,
        fw,
    )
    readiness = _readiness_signal(readiness_logs, rw)

    weights = {
        "volume": volume.weight,
        "effort": effort.weight,
        "completion": completion.weight,
        "hr_zone": hr.weight,
        "feedback": feedback.weight,
        "readiness": readiness.weight,
    }
    # Sequential to match legacy ordering: HR weight first folds into the
    # remaining five (including readiness), then a missing readiness folds
    # *its* inflated weight onto the remaining four.
    if not hr.has_data:
        _redistribute_weight(weights, "hr_zone")
    if not readiness.has_data:
        _redistribute_weight(weights, "readiness")

    mountain_factor, mountain_extras = _mountain_factor(mountain_simulation)

    raw_multiplier = (
        volume.factor * weights["volume"]
        + effort.factor * weights["effort"]
        + completion.factor * weights["completion"]
        + hr.factor * weights["hr_zone"]
        + feedback.factor * weights["feedback"]
        + readiness.factor * weights["readiness"]
    )
    raw_multiplier += effort.extras["trend_modifier"]
    raw_multiplier += effort.extras["quality_drift_modifier"]
    raw_multiplier *= mountain_factor

    raw_multiplier, overreach_detected, tsb_info = _apply_clamps(
        raw_multiplier,
        volume_ratio=volume.extras["volume_ratio"],
        avg_effort=effort.extras["avg_effort"],
        hr_extras=hr.extras,
        recent_race_effort_count=effort.extras["recent_race_effort_count"],
        vdot_trend=vdot_trend,
        training_load=training_load,
        current_phase=current_phase,
    )

    consecutive_same_direction = _count_consecutive_direction(adaptation_history)
    expanded_range = (
        consecutive_same_direction >= _CONSECUTIVE_THRESHOLD or tsb_info["peak_primed"]
    )
    clamp_min, clamp_max = (
        (_EXPANDED_MIN, _EXPANDED_MAX)
        if expanded_range
        else (_STANDARD_MIN, _STANDARD_MAX)
    )

    # If any branch flagged overreach, force the multiplier into
    # "reduce or hold" territory so a strong positive volume contribution
    # can't produce an "increase" banner alongside an overreach alert.
    if overreach_detected:
        raw_multiplier = min(raw_multiplier, OVERREACH_OVERRIDE_CLAMP)

    multiplier = round(max(clamp_min, min(clamp_max, raw_multiplier)), 2)

    return _assemble_result(
        multiplier=multiplier,
        raw_multiplier=raw_multiplier,
        weights=weights,
        current_phase=current_phase,
        volume=volume,
        effort=effort,
        completion=completion,
        hr=hr,
        feedback=feedback,
        readiness=readiness,
        mountain_extras=mountain_extras,
        overreach_detected=overreach_detected,
        tsb_info=tsb_info,
        vdot_trend=vdot_trend,
        consecutive_same_direction=consecutive_same_direction,
        expanded_range=expanded_range,
    )


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


def _readiness_signal(readiness_logs, weight) -> SignalContribution:
    count = len(readiness_logs) if readiness_logs else 0
    if count >= 3:
        scores = [getattr(log, "score", 0) or 0 for log in readiness_logs]
        readiness_pct = (sum(scores) / len(scores)) / 100.0
        readiness_pct = max(0.0, min(1.0, readiness_pct))
        readiness_factor = 0.92 + readiness_pct * 0.13
        has_data = True
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


# Re-exported from `clamps` for backward compatibility (tests and any
# external callers still reach in via these underscore names).
from app.contexts.plan.adaptation.clamps import (  # noqa: E402
    apply_clamps as _apply_clamps,
)
from app.contexts.plan.adaptation.clamps import (  # noqa: E402
    redistribute_weight as _redistribute_weight,
)


def _assemble_result(
    *,
    multiplier: float,
    raw_multiplier: float,
    weights: Dict[str, float],
    current_phase: str,
    volume: SignalContribution,
    effort: SignalContribution,
    completion: SignalContribution,
    hr: SignalContribution,
    feedback: SignalContribution,
    readiness: SignalContribution,
    mountain_extras: Dict[str, Any],
    overreach_detected: bool,
    tsb_info: Dict[str, Any],
    vdot_trend: str,
    consecutive_same_direction: int,
    expanded_range: bool,
) -> Dict[str, Any]:
    quality_drift = effort.extras["quality_drift"]
    avg_effort = effort.extras["avg_effort"]
    mountain_score = mountain_extras["mountain_simulation_score"]
    return {
        "multiplier": multiplier,
        "volume_ratio": round(volume.extras["volume_ratio"], 2),
        "effort_factor": round(effort.extras["effort_factor"], 2),
        "avg_effort": round(avg_effort, 1) if avg_effort is not None else None,
        "effort_trend": effort.extras["effort_trend"],
        "completion_rate": round(completion.extras["completion_rate"], 2),
        "completion_factor": round(completion.extras["completion_factor"], 2),
        "raw_multiplier": round(raw_multiplier, 3),
        "trend_modifier": round(effort.extras["trend_modifier"], 3),
        "overreach_detected": overreach_detected,
        "per_type_ratios": {
            k: round(v, 2) for k, v in volume.extras["per_type_ratios"].items()
        },
        "phase_weights": {
            "volume": round(weights["volume"], 2),
            "effort": round(weights["effort"], 2),
            "completion": round(weights["completion"], 2),
            "hr_zone": round(weights["hr_zone"], 2),
            "feedback": round(weights["feedback"], 2),
            "readiness": round(weights["readiness"], 2),
        },
        "current_phase": current_phase,
        "consecutive_same_direction": consecutive_same_direction,
        "expanded_range": expanded_range,
        "hr_zone_adherence": hr.extras["hr_zone_adherence"],
        "avg_zone_deviation": round(hr.extras["avg_zone_deviation"], 2),
        "hr_zone_trend": hr.extras["hr_zone_trend"],
        "hr_zone_factor": round(hr.extras["hr_zone_factor"], 2),
        "warning_ratio": round(feedback.extras["warning_ratio"], 2),
        "positive_ratio": round(feedback.extras["positive_ratio"], 2),
        "feedback_factor": round(feedback.extras["feedback_factor"], 2),
        "mountain_simulation_score": (
            round(mountain_score, 1) if mountain_score is not None else None
        ),
        "mountain_simulation_factor": round(
            mountain_extras["mountain_simulation_factor"],
            2,
        ),
        "vdot_trend": vdot_trend,
        "quality_drift": (
            round(quality_drift, 2) if quality_drift is not None else None
        ),
        "quality_drift_modifier": round(effort.extras["quality_drift_modifier"], 3),
        "recent_race_effort_count": effort.extras["recent_race_effort_count"],
        "readiness_factor": round(readiness.extras["readiness_factor"], 3),
        "readiness_weight": round(weights["readiness"], 3),
        "readiness_log_count": readiness.extras["readiness_log_count"],
        "tsb": round(tsb_info["tsb"], 1) if tsb_info["tsb"] is not None else None,
        "ctl": round(tsb_info["ctl"], 1) if tsb_info["ctl"] is not None else None,
        "atl": round(tsb_info["atl"], 1) if tsb_info["atl"] is not None else None,
        "tsb_form": tsb_info["tsb_form"],
    }
