"""Proactive adaptation nudges — suggest, never auto-apply.

A thin detector layered over the read-only signal engine
(:func:`plan_adjuster.gather_signals`). When a runner's *own* logged data
shows something worth acting on, RunCoach surfaces a single clearly-flagged
nudge that opens the existing preview → apply change-plan modal for a mapped
life-event intent. The plan never reshapes itself silently: the user reviews
the diff and confirms.

This keeps the proactivity the user asked for without re-creating the
"scattered surfaces" (auto-accept toggle, recommendation banners,
recalibrate modal) that were deliberately consolidated into the single
"Adjust my plan" intent menu. One surface, one decision, fully reversible.

Three guards, checked in priority order (safety first, opportunity last):

    overtraining   – easy runs drifting *above* their zones (same pace, higher
                     HR) or an overreach flag → ease this week (feeling_tired).
    missed_session – recent skipped sessions with a hard workout coming up →
                     ease back in instead of jumping into intervals cold
                     (feeling_tired).
    fitness_jump   – rising VDOT and/or easy-run HR drifting *below* their
                     zones (same pace, lower HR) → bump upcoming volume
                     (feeling_strong).

Only the highest-priority firing guard is shown. Safety guards (ease back)
always win over the opportunistic bump, so a tired runner is never told to
push harder.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date as date_cls
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.models import DailyWorkout, TrainingPlan

from ._helpers import today_date
from .intent_service import _HARD_TYPES
from .plan_adjuster import gather_signals

logger = logging.getLogger(__name__)

# --- Thresholds --------------------------------------------------------------
# Deliberately conservative: a proactive suggestion should only fire on a
# clear signal, never on noise.
#
#   _MULTIPLIER_MIN     engine itself already recommends a meaningful increase.
#   _MULTIPLIER_REDUCE  engine itself already recommends a meaningful decrease.
#   _HR_DRIFT_BELOW     easy runs averaging this many zones *below* prescribed
#                       (same pace, lower HR — fitter).
#   _HR_DRIFT_ABOVE     easy runs averaging this many zones *above* prescribed
#                       (same pace, higher HR — running hot / fatigued).
#   _MIN_COMPLETION     only bump runners who are genuinely hitting sessions.
#   _MISSED_COMPLETION  weighted completion at/below this reads as "skipping".
_MULTIPLIER_MIN = 1.04
_MULTIPLIER_REDUCE = 0.97
_HR_DRIFT_BELOW = -0.5
_HR_DRIFT_ABOVE = 0.5
_MIN_COMPLETION = 0.6
_MISSED_COMPLETION = 0.6

# Once a mapped intent has been applied recently, stay quiet — the plan has
# already moved, so re-offering the same correction would just nag.
_SUPPRESS_DAYS = 10

# Intents the nudges map to — reuses the existing preview → apply machinery.
_INTENT_STRONG = "feeling_strong"
_INTENT_TIRED = "feeling_tired"


def get_nudge(plan_id: str, user_id: str, db: Session) -> Optional[Dict[str, Any]]:
    """Return the highest-priority proactive nudge for this plan, or ``None``.

    Read-only: ``gather_signals`` is called with ``run_map=False`` so nothing
    is committed (safe on a GET). Returns ``None`` when there is insufficient
    data, no guard fires, the matching action can't change anything, the user
    already dismissed this exact nudge, or the mapped intent was applied
    recently.
    """
    plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)
    if plan is None:
        return None

    gathered = gather_signals(plan_id, user_id, db, run_map=False)
    if gathered is None:
        return None

    signals = gathered["signals"]
    current_week = gathered.get("current_week")
    current_dow = gathered.get("current_day_of_week")
    has_future_weeks = bool(gathered.get("adjustable_weeks"))

    # Workouts still ahead in the current week — what feeling_tired can ease.
    remaining = _current_week_remaining(plan_id, current_week, current_dow, db)
    remaining_hard = [w for w in remaining if (w.workout_type or "") in _HARD_TYPES]

    # Priority: safety guards (ease back) before the opportunistic bump.
    nudge = (
        _detect_overtraining(signals, current_week, bool(remaining))
        or _detect_missed_session(signals, current_week, remaining_hard)
        or _detect_fitness_jump(signals, current_week, has_future_weeks)
    )
    if nudge is None:
        return None

    if _recently_applied(plan, nudge["intent"]):
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
# Detectors — each returns a nudge dict or None
# ---------------------------------------------------------------------------


def _detect_overtraining(
    signals: Dict[str, Any], current_week: Optional[int], has_remaining: bool
) -> Optional[Dict[str, Any]]:
    """The "holy grail": easy runs running hot, or an overreach flag.

    Fires on an overreach flag, or on easy-run HR drifting above the prescribed
    zones *corroborated* by the engine already recommending a reduction. Gated
    on there being remaining sessions this week — otherwise easing this week
    would change nothing.
    """
    if not has_remaining:
        return None

    overreach = bool(signals.get("overreach_detected"))
    hr_dev = signals.get("avg_zone_deviation")
    multiplier = signals.get("multiplier") or 1.0

    hr_hot = hr_dev is not None and hr_dev >= _HR_DRIFT_ABOVE
    engine_reducing = multiplier <= _MULTIPLIER_REDUCE
    if not (overreach or (hr_hot and engine_reducing)):
        return None

    if overreach:
        detail = (
            "Your recent training load is flagging overreaching"
            + (
                " and your easy runs are drifting above their target heart-rate zones"
                if hr_hot
                else ""
            )
            + " — a classic sign you need to back off. Want to ease the rest "
            "of this week and drop the hard sessions to easy?"
        )
    else:
        detail = (
            "Your easy runs are coming in above their target heart-rate zones "
            "— you're working harder than the plan intends at these paces, "
            "which often means accumulated fatigue. Want to ease the rest of "
            "this week so you recover?"
        )

    return {
        "kind": "overtraining",
        "intent": _INTENT_TIRED,
        "signature": _signature(
            "overtraining",
            current_week,
            overreach,
            _bucket(hr_dev),
            round(multiplier, 2),
        ),
        "headline": "Ease back — you're running hot",
        "detail": detail,
        "cta": "Review the ease-off",
        "tone": "caution",
        "evidence": {
            "overreach_detected": overreach,
            "avg_zone_deviation": hr_dev,
            "multiplier": multiplier,
        },
    }


def _detect_missed_session(
    signals: Dict[str, Any],
    current_week: Optional[int],
    remaining_hard: List[DailyWorkout],
) -> Optional[Dict[str, Any]]:
    """Recent skipped sessions with a hard workout still ahead this week.

    The frustration the friend called out: miss a couple of sessions to life,
    then get thrown straight into hard intervals. Fires when weighted
    completion reads as "skipping" and there's a hard session left this week to
    soften. Overreach is handled by the overtraining guard, so skip it here.
    """
    if not remaining_hard:
        return None
    if signals.get("overreach_detected"):
        return None

    completion = signals.get("completion_rate")
    if completion is None or completion > _MISSED_COMPLETION:
        return None

    return {
        "kind": "missed_session",
        "intent": _INTENT_TIRED,
        "signature": _signature(
            "missed_session", current_week, _bucket(completion), len(remaining_hard)
        ),
        "headline": "Ease back in after the gap",
        "detail": (
            "You've missed a few recent sessions and there's a hard workout "
            "still coming up this week. Jumping straight back into hard "
            "intervals when you're not ready is how runners get hurt or "
            "discouraged. Want to ease this week and soften that session so "
            "you build back in?"
        ),
        "cta": "Review the reshape",
        "tone": "caution",
        "evidence": {
            "completion_rate": round(completion, 2),
            "hard_sessions_remaining": len(remaining_hard),
        },
    }


def _detect_fitness_jump(
    signals: Dict[str, Any], current_week: Optional[int], has_future_weeks: bool
) -> Optional[Dict[str, Any]]:
    """Rising VDOT and/or easy-run HR drifting below the prescribed zones.

    Fires when the runner is fitter and it is safe to push: no overreach flag,
    solid completion, the engine already recommends an increase, and there are
    future weeks left to bump.
    """
    if not has_future_weeks:
        return None
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

    return {
        "kind": "fitness_jump",
        "intent": _INTENT_STRONG,
        "signature": _signature(
            "fitness_jump",
            current_week,
            vdot_trend,
            _bucket(hr_dev),
            round(multiplier, 2),
        ),
        "headline": "Your fitness is climbing",
        "detail": _fitness_jump_detail(fitter_by_vdot, fitter_by_hr),
        "cta": "Review the bump",
        "tone": "positive",
        "evidence": {
            "vdot_trend": vdot_trend,
            "avg_zone_deviation": hr_dev,
            "completion_rate": round(completion, 2),
            "multiplier": multiplier,
        },
    }


def _fitness_jump_detail(fitter_by_vdot: bool, fitter_by_hr: bool) -> str:
    """Compose fitness-jump copy from whichever evidence fired."""
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_week_remaining(
    plan_id: str,
    current_week: Optional[int],
    current_dow: Optional[int],
    db: Session,
) -> List[DailyWorkout]:
    """Non-rest workouts still ahead in the current week (today onwards).

    Mirrors what the ``feeling_tired`` intent eases — ``range(current_dow, 8)``
    — so a guard only fires when the action it maps to would actually change
    something.
    """
    if current_week is None or current_dow is None:
        return []
    repo = SQLAlchemyPlanRepository(db)
    weekly_plan = repo.get_weekly_plan(plan_id, current_week)
    if weekly_plan is None:
        return []
    return [
        w
        for w in repo.list_daily_workouts(weekly_plan.id)
        if (w.day_of_week or 0) >= current_dow
        and (w.workout_type or "") != "rest"
        and (w.distance_km or 0) > 0
    ]


def _bucket(value: Any) -> Any:
    """Round a continuous signal so trivial wobble doesn't churn signatures."""
    return round(value, 1) if isinstance(value, (int, float)) else "na"


def _signature(kind: str, *parts: Any) -> str:
    """Stable id for a nudge "situation".

    Keys on the nudge kind plus its bucketed evidence (including the current
    week), so a previously-dismissed nudge re-surfaces only once the situation
    materially moves.
    """
    raw = kind + "|" + "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _recently_applied(plan: TrainingPlan, intent: str) -> bool:
    """True if ``intent`` was applied within the suppress window.

    Reads the plan's adaptation history so we don't re-offer a correction the
    runner just accepted — the plan has already moved.
    """
    history = plan.adaptation_history or []
    today = today_date()
    for event in reversed(history):
        if event.get("intent") != intent:
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
