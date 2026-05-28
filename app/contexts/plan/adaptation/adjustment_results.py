"""Result-shaping helpers for plan adjustments.

These shape the per-event records that the adjuster writes to
``training_plan.adaptation_history`` and the lighter signals view that the
change-plan modal consumes. Factored out of ``plan_adjuster`` so the
orchestration file can focus on the actual adjustment flow.
"""

from typing import Any, Dict, Optional

from app.models import TrainingPlan

from . import change_reasons as _reasons
from ._helpers import today_date
from .change_plan_builder import empty_change_plan


def build_signal_snapshot(signals: Dict[str, Any]) -> Dict[str, Any]:
    """Per-signal factor + weight + form, frozen onto an adaptation event.

    Persisted on each applied "adjust" event so the Coach Hub can chart how
    the six signals evolved over time without recomputing historical state.
    Mirrors the ``signals_block`` shape that ``build_coach_summary`` exposes.
    """
    weights = signals.get("phase_weights", {})
    return {
        "multiplier": signals.get("multiplier"),
        "phase": signals.get("current_phase"),
        "signals": {
            "volume": {
                "factor": signals.get("volume_ratio"),
                "weight": weights.get("volume", 0.0),
            },
            "effort": {
                "factor": signals.get("effort_factor"),
                "weight": weights.get("effort", 0.0),
            },
            "completion": {
                "factor": signals.get("completion_factor"),
                "weight": weights.get("completion", 0.0),
            },
            "hr_zone": {
                "factor": signals.get("hr_zone_factor"),
                "weight": weights.get("hr_zone", 0.0),
            },
            "feedback": {
                "factor": signals.get("feedback_factor"),
                "weight": weights.get("feedback", 0.0),
            },
            "readiness": {
                "factor": signals.get("readiness_factor"),
                "weight": weights.get("readiness", 0.0),
            },
        },
        "form": {
            "ctl": signals.get("ctl"),
            "atl": signals.get("atl"),
            "tsb": signals.get("tsb"),
            "tsb_form": signals.get("tsb_form"),
        },
    }


def build_signals_summary(
    signals: Dict[str, Any], *, runs_count: Optional[int] = None
) -> Dict[str, Any]:
    """Subset of signals safe to expose to the change-plan modal."""
    out = {
        "effort_trend": signals.get("effort_trend"),
        "completion_rate": signals.get("completion_rate"),
        "volume_ratio": signals.get("volume_ratio"),
        "phase": signals.get("current_phase"),
        "avg_effort": signals.get("avg_effort"),
        "tsb_form": signals.get("tsb_form"),
        "overreach_detected": signals.get("overreach_detected"),
    }
    if runs_count is not None:
        out["runs_analyzed"] = runs_count
    return out


def build_no_adjustable_weeks_result(
    *,
    mode: str,
    signals: Dict[str, Any],
    runs_count: int,
) -> Dict[str, Any]:
    """Shape the early-exit result when no future weeks can be adjusted.

    Returned by ``_run_adjust`` when ``adjustable_weeks`` is empty — every
    upcoming session is past the cut-off, so there's nothing to scale.
    Surfaces the same multiplier / signals summary the modal would have
    shown for a successful adjust, just with ``adjusted=False``.
    """
    cp = empty_change_plan(
        action="adjust",
        mode=mode,
        headline_reason=_reasons.NO_CHANGE_NO_REMAINING_WORKOUTS,
    )
    cp["summary"]["multiplier"] = signals["multiplier"]
    cp["signals"] = build_signals_summary(signals, runs_count=runs_count)
    return {
        "adjusted": False,
        **{
            k: signals[k]
            for k in (
                "multiplier",
                "volume_ratio",
                "avg_effort",
                "completion_rate",
            )
        },
        "total_runs": runs_count,
        "weeks_changed": 0,
        "reason": _reasons.NO_CHANGE_NO_REMAINING_WORKOUTS,
        "change_plan": cp,
    }


def record_adaptation_event(training_plan: TrainingPlan, event: Dict[str, Any]) -> None:
    """Append ``event`` to the plan's adaptation history, capped at 20 entries."""
    event["date"] = today_date().isoformat()
    history = list(training_plan.adaptation_history or [])
    history.append(event)
    if len(history) > 20:
        history = history[-20:]
    training_plan.adaptation_history = history
