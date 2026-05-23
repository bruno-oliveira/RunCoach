"""Coach summary — cross-context assembler for the analytics "Coach" hub.

Orchestrates the plan adaptation engine, runner fitness services, and
coaching feedback into the read-only payloads the Coach tab renders:

- ``build_coach_summary``  — the 6-signal breakdown ("what your coach sees"),
  current multiplier/direction, form (TSB/CTL/ATL), and race readiness.
- ``build_adaptation_history`` — the persisted adaptation timeline, normalized.
- ``build_coach_patterns`` — recency-weighted pace patterns + week pulse.

All functions are read-only: they never commit. ``preview_adjust_signals``
gathers signals with ``run_map=False`` so no run→workout mapping is written
on a GET request.
"""

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.adaptation import AdaptationService
from app.contexts.plan.plan_date_utils import compute_current_week
from app.contexts.runner.enrichment.week_pulse_generator import get_week_pulse
from app.contexts.runner.fitness.readiness_service import ReadinessService
from app.core.coaching.pattern_analyzer import pattern_feedback
from app.models import RunLog, TrainingPlan
from app.utils import to_date as _to_date

# Dead-zone around 1.0 below which an adjustment is treated as "hold" — mirrors
# the ±2% hysteresis the recommendation evaluator uses.
_HOLD_BAND = 0.02

_EVENT_LABELS = {
    "adjust": "Plan adjusted",
    "reset": "Reset to baseline",
    "recalibrate": "Recalibrated",
    "auto_accept": "Auto-applied recommendation",
    "auto_dismiss": "Recommendation dismissed",
}

_PATTERN_TYPES = ("easy", "recovery", "long", "tempo", "interval")


def build_coach_summary(
    plan: TrainingPlan, user_id: str, db: Session
) -> Dict[str, Any]:
    """The consolidated "what your coach sees" payload for a plan."""
    signals = AdaptationService().preview_adjust_signals(plan.id, user_id, db)
    if signals is None:
        return {
            "available": False,
            "reason": "Log at least 3 runs linked to this plan to unlock your coach summary.",
        }

    weights = signals.get("phase_weights", {})
    signals_block = {
        "volume": {
            "factor": signals.get("volume_ratio"),
            "weight": weights.get("volume", 0.0),
            "has_data": True,
        },
        "effort": {
            "factor": signals.get("effort_factor"),
            "weight": weights.get("effort", 0.0),
            "has_data": signals.get("avg_effort") is not None,
        },
        "completion": {
            "factor": signals.get("completion_factor"),
            "weight": weights.get("completion", 0.0),
            "has_data": True,
        },
        "hr_zone": {
            "factor": signals.get("hr_zone_factor"),
            "weight": weights.get("hr_zone", 0.0),
            "has_data": signals.get("hr_zone_adherence") is not None,
        },
        "feedback": {
            "factor": signals.get("feedback_factor"),
            "weight": weights.get("feedback", 0.0),
            "has_data": True,
        },
        "readiness": {
            "factor": signals.get("readiness_factor"),
            "weight": weights.get("readiness", 0.0),
            "has_data": (signals.get("readiness_log_count") or 0) >= 3,
        },
    }

    multiplier = signals.get("multiplier", 1.0)
    direction = _direction(multiplier)

    readiness: Optional[Dict[str, Any]] = None
    try:
        readiness = ReadinessService.compute_readiness(plan, user_id, db)
    except Exception:  # readiness is best-effort; never block the summary
        readiness = None

    return {
        "available": True,
        "plan_id": plan.id,
        "multiplier": multiplier,
        "direction": direction,
        "would_change": direction != "hold",
        "overreach_detected": signals.get("overreach_detected", False),
        "current_phase": signals.get("current_phase"),
        "current_week": signals.get("current_week"),
        "signals": signals_block,
        "per_type_ratios": signals.get("per_type_ratios", {}),
        "effort_trend": signals.get("effort_trend"),
        "quality_drift": signals.get("quality_drift"),
        "hr_zone_trend": signals.get("hr_zone_trend"),
        "vdot_trend": signals.get("vdot_trend"),
        "form": {
            "tsb": signals.get("tsb"),
            "ctl": signals.get("ctl"),
            "atl": signals.get("atl"),
            "tsb_form": signals.get("tsb_form"),
        },
        "readiness": readiness,
        "headline_reason": _build_headline(signals, direction, multiplier),
    }


def build_adaptation_history(plan: TrainingPlan) -> Dict[str, Any]:
    """Normalize the persisted ``adaptation_history`` into display rows.

    Events are appended chronologically (capped at 20 by the writers); we
    return them newest-first with a uniform shape and defensive ``.get``
    since the writers store heterogeneous fields.
    """
    raw = plan.adaptation_history or []
    events = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        etype = entry.get("type", "adjust")
        multiplier = entry.get("multiplier")
        pct = (
            round((multiplier - 1.0) * 100)
            if isinstance(multiplier, (int, float))
            else None
        )
        events.append(
            {
                "date": entry.get("date"),
                "type": etype,
                "label": _EVENT_LABELS.get(etype, etype.replace("_", " ").title()),
                "direction": entry.get("direction"),
                "multiplier": multiplier,
                "pct": pct,
                "phase": entry.get("phase"),
                "overreach": entry.get("overreach"),
                "weeks_changed": entry.get("weeks_changed"),
                "week_evaluated": entry.get("week_evaluated"),
                "reason": entry.get("reason"),
            }
        )
    events.reverse()
    return {"available": True, "events": events}


def build_coach_patterns(
    plan: TrainingPlan, user_id: str, db: Session
) -> Dict[str, Any]:
    """Recency-weighted pace patterns + the inline week-pulse mood line.

    Trend fields (effort/quality drift) are intentionally left to
    ``build_coach_summary`` to avoid a second signal-gather; this endpoint
    stays light: one ``pattern_feedback`` call per workout type plus the
    week pulse.
    """
    runs = (
        db.query(RunLog)
        .filter(
            RunLog.training_plan_id == plan.id,
            RunLog.workout_type.isnot(None),
        )
        .order_by(RunLog.date.desc())
        .all()
    )

    patterns = []
    seen: set = set()
    for run in runs:
        wtype = run.workout_type
        if wtype not in _PATTERN_TYPES or wtype in seen:
            continue
        seen.add(wtype)
        message = pattern_feedback(run, db)
        if message:
            patterns.append({"workout_type": wtype, "message": message})

    week_pulse = None
    if plan.start_date:
        start = _to_date(plan.start_date)
        current_week = compute_current_week(
            start, date.today(), clamp_min=1, pre_start=1
        )
        week_pulse = get_week_pulse(plan, current_week, db)

    return {
        "available": True,
        "patterns": patterns,
        "week_pulse": week_pulse,
    }


def _direction(multiplier: float) -> str:
    if multiplier > 1.0 + _HOLD_BAND:
        return "increase"
    if multiplier < 1.0 - _HOLD_BAND:
        return "decrease"
    return "hold"


def _build_headline(signals: Dict[str, Any], direction: str, multiplier: float) -> str:
    """A short, human-readable summary of the current adaptation stance."""
    if direction == "hold":
        parts = ["Your plan is on track — no scaling needed right now."]
    else:
        verb = "step up" if direction == "increase" else "ease back"
        parts = [f"Your coach would {verb} remaining workouts (×{multiplier:.2f})."]

    phase = signals.get("current_phase")
    if phase:
        parts.append(f"You're in the {phase} phase.")

    if signals.get("overreach_detected"):
        parts.append(
            "Overreach detected — load is being held back to protect recovery."
        )

    tsb_form = signals.get("tsb_form")
    tsb = signals.get("tsb")
    if tsb_form and tsb is not None:
        parts.append(f"Form is {tsb_form} (TSB {tsb}).")

    effort_trend = signals.get("effort_trend")
    if effort_trend and effort_trend != "stable":
        parts.append(f"Perceived effort is {effort_trend}.")

    if signals.get("vdot_trend") == "declining":
        parts.append("VDOT is declining — capping volume to avoid overtraining.")

    return " ".join(parts)
