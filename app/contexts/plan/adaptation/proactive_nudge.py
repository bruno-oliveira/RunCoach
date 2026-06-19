"""Proactive adaptation nudges — suggest, never auto-apply.

A thin detector layered over the read-only signal engine
(:func:`plan_adjuster.gather_signals`). When a runner's *own* logged data
shows a clear, safe improvement in fitness, RunCoach surfaces a single
clearly-flagged nudge that opens the existing preview → apply change-plan
modal for the ``feeling_strong`` intent. The plan never reshapes itself
silently: the user reviews the diff and confirms.

This keeps the proactivity the user asked for without re-creating the
"scattered surfaces" (auto-accept toggle, recommendation banners,
recalibrate modal) that were deliberately consolidated into the single
"Adjust my plan" intent menu. One surface, one decision, fully reversible.

First cut covers one scenario — the **fitness jump**:

    Rising VDOT and/or easy-run heart rate drifting *below* the prescribed
    zones (same pace, lower HR) → offer to bump upcoming easy/long volume a
    touch. Only fires when the runner is actually doing the work and there is
    no overreach flag, so a tired runner is never told to push harder.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date as date_cls
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.models import TrainingPlan

from ._helpers import today_date
from .plan_adjuster import gather_signals

logger = logging.getLogger(__name__)

# --- Fitness-jump thresholds -------------------------------------------------
# Deliberately conservative: a proactive suggestion should only fire on a
# clear, safe signal, never on noise.
#
#   _MULTIPLIER_MIN  the engine itself must already recommend a meaningful
#                    increase (its multiplier blends every signal + clamps).
#   _HR_DRIFT_BELOW  easy runs averaging at least this many zones *below* the
#                    prescribed zone — i.e. same pace at a lower heart rate.
#   _MIN_COMPLETION  only bump runners who are genuinely hitting their sessions.
_MULTIPLIER_MIN = 1.04
_HR_DRIFT_BELOW = -0.5
_MIN_COMPLETION = 0.6

# Once a "feeling_strong" bump has been applied recently, stay quiet — the plan
# has already moved, so re-offering the same nudge would just nag.
_SUPPRESS_DAYS = 10

# Intent the nudge maps to — reuses the existing preview → apply machinery.
NUDGE_INTENT = "feeling_strong"


def get_nudge(plan_id: str, user_id: str, db: Session) -> Optional[Dict[str, Any]]:
    """Return the proactive nudge for this plan, or ``None``.

    Read-only: ``gather_signals`` is called with ``run_map=False`` so nothing
    is committed (safe on a GET). Returns ``None`` when there is insufficient
    data, no upcoming weeks to bump, the situation doesn't warrant a nudge, the
    user already dismissed this exact nudge, or a strong bump was applied
    recently.
    """
    plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)
    if plan is None:
        return None

    if _recently_strengthened(plan):
        return None

    gathered = gather_signals(plan_id, user_id, db, run_map=False)
    if gathered is None:
        return None
    if not gathered.get("adjustable_weeks"):
        # No upcoming weeks left to bump — nothing to suggest.
        return None

    nudge = _detect_fitness_jump(gathered["signals"], gathered.get("current_week"))
    if nudge is None:
        return None

    last = plan.last_proactive_nudge or {}
    if last.get("signature") == nudge["signature"] and last.get("dismissed"):
        # The user already dismissed this exact situation — keep quiet until it
        # materially changes (which produces a new signature).
        return None

    return nudge


def dismiss_nudge(
    plan_id: str, user_id: str, signature: Optional[str], db: Session
) -> Dict[str, Any]:
    """Record that the user dismissed a nudge so it isn't re-shown.

    Persists the dismissed ``signature``; a future nudge with the same
    signature is suppressed by :func:`get_nudge`. A different signature (the
    situation moved on) surfaces again.
    """
    plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)
    if plan is None:
        return {"ok": False, "reason": "Plan not found."}

    plan.last_proactive_nudge = {
        "signature": signature,
        "dismissed": True,
        "dismissed_on": today_date().isoformat(),
    }
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _detect_fitness_jump(
    signals: Dict[str, Any], current_week: Optional[int]
) -> Optional[Dict[str, Any]]:
    """Map signal extremes to a fitness-jump nudge, or ``None``.

    Fires when the runner is fitter — rising VDOT and/or easy-run HR drifting
    below the prescribed zones — *and* it is safe to push: no overreach flag,
    solid completion, and the engine already recommends an increase.
    """
    if signals.get("overreach_detected"):
        return None

    multiplier = signals.get("multiplier") or 1.0
    if multiplier < _MULTIPLIER_MIN:
        return None

    completion = signals.get("completion_rate")
    if completion is None or completion < _MIN_COMPLETION:
        return None

    vdot_trend = signals.get("vdot_trend")
    hr_dev = signals.get("avg_zone_deviation")

    fitter_by_vdot = vdot_trend == "improving"
    fitter_by_hr = hr_dev is not None and hr_dev <= _HR_DRIFT_BELOW
    if not (fitter_by_vdot or fitter_by_hr):
        return None

    detail = _build_detail(fitter_by_vdot, fitter_by_hr, hr_dev)
    signature = _signature(current_week, vdot_trend, hr_dev, multiplier)

    return {
        "kind": "fitness_jump",
        "intent": NUDGE_INTENT,
        "signature": signature,
        "headline": "Your fitness is climbing",
        "detail": detail,
        "cta": "Review the bump",
        "evidence": {
            "vdot_trend": vdot_trend,
            "avg_zone_deviation": hr_dev,
            "completion_rate": round(completion, 2),
            "multiplier": multiplier,
        },
    }


def _build_detail(fitter_by_vdot: bool, fitter_by_hr: bool, hr_dev: Any) -> str:
    """Compose human copy from whichever evidence fired."""
    if fitter_by_vdot and fitter_by_hr:
        return (
            "Your predicted race fitness is trending up and your easy runs are "
            "coming in below their target heart-rate zones — same pace, less "
            "effort. Want to nudge up your upcoming easy and long runs?"
        )
    if fitter_by_hr:
        return (
            "Your easy runs are coming in below their target heart-rate zones — "
            "you're holding the same paces at a lower heart rate. Want to nudge "
            "up your upcoming easy and long runs?"
        )
    return (
        "Your predicted race fitness has been trending up across recent runs. "
        "Want to nudge up your upcoming easy and long runs to match?"
    )


def _signature(
    current_week: Optional[int],
    vdot_trend: Optional[str],
    hr_dev: Any,
    multiplier: float,
) -> str:
    """Stable id for a nudge "situation".

    Buckets the continuous signals so trivial wobble doesn't churn the
    signature, but keys on ``current_week`` so a genuinely new week can
    re-surface a previously-dismissed nudge.
    """
    hr_bucket = round(hr_dev, 1) if hr_dev is not None else "na"
    mult_bucket = round(multiplier, 2)
    raw = f"fitness_jump|{current_week}|{vdot_trend}|{hr_bucket}|{mult_bucket}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------


def _recently_strengthened(plan: TrainingPlan) -> bool:
    """True if a ``feeling_strong`` bump was applied within the suppress window.

    Reads the plan's adaptation history so we don't re-offer a bump the runner
    just accepted — the plan has already moved.
    """
    history = plan.adaptation_history or []
    today = today_date()
    for event in reversed(history):
        if event.get("intent") != NUDGE_INTENT:
            continue
        event_date = _parse_iso_date(event.get("date"))
        if event_date is None:
            continue
        if (today - event_date).days <= _SUPPRESS_DAYS:
            return True
    return False


def _parse_iso_date(value: Any) -> Optional[date_cls]:
    """Parse an ISO date/datetime string (as stored on adaptation events)."""
    if isinstance(value, str):
        try:
            return date_cls.fromisoformat(value[:10])
        except ValueError:
            return None
    if isinstance(value, date_cls):
        return value
    return None
