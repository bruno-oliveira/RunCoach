"""Compute volume, effort, completion, and trend signals for plan adjustment.

Top-level entry point :func:`compute_adjustment_signals` is a thin dispatcher.
Each independent signal lives in ``signals`` returning a
:class:`SignalContribution`; shared value objects live in ``context``. Tunables,
math, and clamps are sourced from their canonical modules and re-exported here
under the historical underscore names so internal usages and tests are
unchanged.
"""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.contexts.plan.adaptation.clamps import (
    apply_clamps as _apply_clamps,
)
from app.contexts.plan.adaptation.clamps import (
    redistribute_weight as _redistribute_weight,
)
from app.contexts.plan.adaptation.signal_computer.context import (
    SignalContribution,
    _SignalContext,
)
from app.contexts.plan.adaptation.signal_computer.signals import (
    _completion_signal,
    _effort_signal,
    _feedback_signal,
    _hr_signal,
    _mountain_factor,
    _readiness_signal,
    _volume_signal,
)
from app.contexts.plan.adaptation.tuning import (
    BAYESIAN_SHRINKAGE_PER_RUN as _BAYESIAN_SHRINKAGE_PER_RUN,
)
from app.contexts.plan.adaptation.tuning import (
    CONSECUTIVE_THRESHOLD as _CONSECUTIVE_THRESHOLD,
)
from app.contexts.plan.adaptation.tuning import (
    EXPANDED_MAX as _EXPANDED_MAX,
)
from app.contexts.plan.adaptation.tuning import (
    EXPANDED_MIN as _EXPANDED_MIN,
)
from app.contexts.plan.adaptation.tuning import (
    IMPORTANCE_WEIGHTS as _IMPORTANCE_WEIGHTS,
)
from app.contexts.plan.adaptation.tuning import (
    MIN_RUNS_PER_TYPE as _MIN_RUNS_PER_TYPE,
)
from app.contexts.plan.adaptation.tuning import (
    OVERREACH_OVERRIDE_CLAMP,
)
from app.contexts.plan.adaptation.tuning import (
    PHASE_WEIGHTS as _PHASE_WEIGHTS,
)
from app.contexts.plan.adaptation.tuning import (
    STANDARD_MAX as _STANDARD_MAX,
)
from app.contexts.plan.adaptation.tuning import (
    STANDARD_MIN as _STANDARD_MIN,
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

_SIGNAL_REGISTRY = [
    (
        "volume",
        False,
        lambda ctx, w: _volume_signal(
            ctx.past_workouts, ctx.all_plan_runs, ctx.recency_weight_fn, ctx.today, w
        ),
    ),
    (
        "effort",
        False,
        lambda ctx, w: _effort_signal(
            ctx.all_plan_runs, ctx.recency_weight_fn, ctx.today, w
        ),
    ),
    (
        "completion",
        False,
        lambda ctx, w: _completion_signal(
            ctx.past_workouts,
            ctx.past_workout_ids,
            ctx.plan_id,
            ctx.db,
            ctx.recency_weight_fn,
            w,
        ),
    ),
    (
        "hr_zone",
        True,
        lambda ctx, w: _hr_signal(
            ctx.all_plan_runs, ctx.hr_zones, ctx.recency_weight_fn, ctx.today, w
        ),
    ),
    (
        "feedback",
        False,
        lambda ctx, w: _feedback_signal(
            ctx.run_feedback_list,
            ctx.all_plan_runs,
            ctx.recency_weight_fn,
            ctx.today,
            w,
        ),
    ),
    (
        "readiness",
        True,
        lambda ctx, w: _readiness_signal(ctx.readiness_logs, w),
    ),
]


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
    phase_weights = _PHASE_WEIGHTS.get(current_phase, _PHASE_WEIGHTS["build"])

    ctx = _SignalContext(
        all_plan_runs=all_plan_runs,
        past_workouts=past_workouts,
        past_workout_ids=past_workout_ids,
        today=today,
        plan_id=plan_id,
        db=db,
        recency_weight_fn=recency_weight_fn,
        hr_zones=hr_zones,
        run_feedback_list=run_feedback_list,
        readiness_logs=readiness_logs,
    )

    # Compute + weight every registered signal in canonical order.
    contribs: Dict[str, SignalContribution] = {
        name: invoke(ctx, phase_weights[i])
        for i, (name, _optional, invoke) in enumerate(_SIGNAL_REGISTRY)
    }
    weights = {name: c.weight for name, c in contribs.items()}
    # Optional signals with no data fold their weight onto the rest, in registry
    # order (hr_zone before readiness) — preserves the legacy redistribution
    # sequencing where HR folds first, then a missing readiness folds after.
    for name, optional, _invoke in _SIGNAL_REGISTRY:
        if optional and not contribs[name].has_data:
            _redistribute_weight(weights, name)

    # Named aliases for the clamp/assembly logic that consumes each signal's
    # specific extras.
    volume = contribs["volume"]
    effort = contribs["effort"]
    completion = contribs["completion"]
    hr = contribs["hr_zone"]
    feedback = contribs["feedback"]
    readiness = contribs["readiness"]

    mountain_factor, mountain_extras = _mountain_factor(mountain_simulation)

    raw_multiplier = sum(
        contribs[name].factor * weights[name] for name, _o, _i in _SIGNAL_REGISTRY
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


__all__ = [
    "compute_adjustment_signals",
    "SignalContribution",
    "_SignalContext",
    "_apply_clamps",
    "_redistribute_weight",
    # Tunables / math re-exported under historical names for tests.
    "_BAYESIAN_SHRINKAGE_PER_RUN",
    "_MIN_RUNS_PER_TYPE",
    "_PHASE_WEIGHTS",
    "_IMPORTANCE_WEIGHTS",
    "_CONSECUTIVE_THRESHOLD",
    "_EXPANDED_MAX",
    "_EXPANDED_MIN",
    "_STANDARD_MAX",
    "_STANDARD_MIN",
    "_compute_quality_drift",
    "_count_consecutive_direction",
    "_count_recent_race_efforts",
]
