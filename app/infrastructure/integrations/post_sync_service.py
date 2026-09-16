"""Post-sync orchestration: auto-map runs to plans and trigger adjustments.

After an activity sync (manual or ambient), this module maps logged runs onto
planned days, then — new since the auto-adapt wiring — applies signal-based
volume adjustment and VDOT recalibration in one pass.  When there are too few
linked runs for signal computation (<3), it falls back to VDOT-only
recalibration so pace zones still track fitness shifts early in a plan.

Every applied change is recorded as a ``last_change_plan`` on the plan so the
UI can surface an unseen-change banner the next time the runner visits.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.adaptation import AdaptationService
from app.models import TrainingPlan
from app.models.user import User
from app.utils import to_date as _to_date

logger = logging.getLogger(__name__)

# The signal computer already snaps near-neutral multipliers to 1.0 within its
# HOLD_DEADBAND (0.05).  This secondary gate exists for the overreach path,
# where the deadband is bypassed — a 2% overreach tweak applied silently would
# churn the plan without any noticeable coaching signal.
_AUTO_ADJUST_MIN_DELTA = 0.03

# A manual intent ("feeling tired", "feeling strong", …) sets the direction
# the runner chose; the ambient engine should not override it immediately.
_MANUAL_COOLDOWN = timedelta(hours=24)


def auto_map_and_adjust(
    user: User,
    db: Session,
    adaptation_service: AdaptationService,
) -> list[dict]:
    """Find active plans and auto-map runs + auto-adjust each one.

    Returns a list of per-plan result dicts suitable for the sync response.
    """
    today = datetime.now(timezone.utc).date()

    active_plans = (
        db.query(TrainingPlan)
        .filter(
            TrainingPlan.user_id == user.id,
            TrainingPlan.start_date.isnot(None),
        )
        .all()
    )

    results: list[dict] = []
    for plan in active_plans:
        start = _to_date(plan.start_date)
        if start is None:
            continue
        end_date = start + timedelta(weeks=plan.weeks_duration)
        if today > end_date:
            continue

        try:
            map_result = adaptation_service.map_runs_to_plan(plan.id, user.id, db)

            adapt = _auto_adapt(plan, user.id, db)

            results.append(
                {
                    "plan_id": plan.id,
                    "runs_mapped": map_result.get("mapped", 0),
                    "vdot_recalibration": adapt.get("vdot_recalibration"),
                    "auto_adjusted": adapt.get("auto_adjusted", False),
                }
            )
        except Exception as e:
            logger.warning(f"Auto-adjust failed for plan {plan.id}: {e}")

    return results


# ---------------------------------------------------------------------------
# Auto-adaptation orchestration
# ---------------------------------------------------------------------------


def _auto_adapt(
    plan: TrainingPlan,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Full signal-based adaptation with VDOT-only fallback.

    Attempts volume adjustment + VDOT recalibration when signals warrant it;
    falls back to VDOT-only recalibration when the signal data is thin or the
    multiplier is within the auto-adjust deadband.
    """
    from app.contexts.plan.adaptation.adjustment_results import (
        build_signal_snapshot as _build_signal_snapshot,
        build_signals_summary as _build_signals_summary,
        record_adaptation_event as _record,
    )
    from app.contexts.plan.adaptation.change_plan_builder import build_change_plan
    from app.contexts.plan.adaptation.plan_adjuster import gather_signals
    from app.contexts.plan.adaptation.week_adjuster import apply_adjustment_stage

    result: Dict[str, Any] = {"vdot_recalibration": None, "auto_adjusted": False}

    if _recently_adjusted(plan):
        result["vdot_recalibration"] = _try_recalibrate_and_record(
            plan, user_id, db
        )
        return result

    gathered = gather_signals(plan.id, user_id, db, run_map=False)

    if gathered is None:
        result["vdot_recalibration"] = _try_recalibrate_and_record(
            plan, user_id, db
        )
        return result

    signals = gathered["signals"]
    multiplier = signals.get("multiplier", 1.0)
    adjustable_weeks = gathered["adjustable_weeks"]

    if abs(multiplier - 1.0) < _AUTO_ADJUST_MIN_DELTA or not adjustable_weeks:
        result["vdot_recalibration"] = _try_recalibrate_and_record(
            plan, user_id, db
        )
        return result

    # --- full adaptation: volume + VDOT ---
    week_numbers = [w.week_number for w in adjustable_weeks]
    try:
        ar = apply_adjustment_stage(
            plan,
            adjustable_weeks,
            multiplier=multiplier,
            per_type_ratios=signals.get("per_type_ratios"),
            current_week=gathered["current_week"],
            current_day_of_week=gathered["current_day_of_week"],
            user_id=user_id,
            db=db,
            week_numbers=week_numbers,
        )
    except Exception as e:
        logger.warning("Auto-adjust apply stage failed for plan %s: %s", plan.id, e)
        result["vdot_recalibration"] = _try_recalibrate_and_record(
            plan, user_id, db
        )
        return result

    vdot_change = _extract_vdot_change(ar.vdot_result)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if ar.any_distance_changed:
        change_plan = build_change_plan(
            action="auto_adjust",
            mode="applied",
            training_plan=plan,
            before=ar.before,
            after=ar.after,
            recorder=ar.recorder,
            signals=_build_signals_summary(
                signals, runs_count=len(gathered["all_plan_runs"])
            ),
            multiplier=multiplier,
            vdot_change=vdot_change,
            headline_reason=_auto_adjust_headline(multiplier, vdot_change),
            current_week=gathered["current_week"],
            current_day_of_week=gathered["current_day_of_week"],
        )
        plan.adjustment_multiplier = multiplier
        plan.last_adjusted_at = now
        plan.last_change_plan = change_plan
        if ar.vdot_result:
            plan.last_recalibrated_at = now
        _record(
            plan,
            {
                "type": "auto_adjust",
                "multiplier": round(multiplier, 3),
                "weeks_changed": ar.weeks_changed,
                "vdot_recalibration": ar.vdot_result,
                "reason": change_plan["reason"],
                "signal_snapshot": _build_signal_snapshot(signals),
            },
        )
        db.flush()
        result["auto_adjusted"] = True
        result["vdot_recalibration"] = ar.vdot_result

    elif ar.vdot_result:
        change_plan = build_change_plan(
            action="recalibrate",
            mode="applied",
            training_plan=plan,
            before={},
            after={},
            vdot_change=vdot_change,
            headline_reason=_recalibrate_headline(vdot_change),
        )
        plan.last_change_plan = change_plan
        plan.last_recalibrated_at = now
        _record(
            plan,
            {
                "type": "recalibrate",
                "old_vdot": ar.vdot_result["old_vdot"],
                "new_vdot": ar.vdot_result["new_vdot"],
                "direction": ar.vdot_result["direction"],
                "source": ar.vdot_result.get("source"),
                "reason": change_plan["reason"],
            },
        )
        db.flush()
        result["vdot_recalibration"] = ar.vdot_result

    return result


def _try_recalibrate_and_record(
    plan: TrainingPlan,
    user_id: str,
    db: Session,
) -> Optional[Dict[str, Any]]:
    """VDOT-only recalibration with change_plan + adaptation event recording."""
    from app.contexts.plan.adaptation.adjustment_results import (
        record_adaptation_event as _record,
    )
    from app.contexts.plan.adaptation.change_plan_builder import build_change_plan
    from app.contexts.plan.adaptation.vdot_recalibrator import recalibrate_zones_only

    try:
        vdot_result = recalibrate_zones_only(plan, user_id, db)
    except Exception as e:
        logger.warning(
            "VDOT recalibration after sync failed for plan %s: %s", plan.id, e
        )
        return None

    if not vdot_result:
        return None

    vdot_change = _extract_vdot_change(vdot_result)
    change_plan = build_change_plan(
        action="recalibrate",
        mode="applied",
        training_plan=plan,
        before={},
        after={},
        vdot_change=vdot_change,
        headline_reason=_recalibrate_headline(vdot_change),
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    plan.last_change_plan = change_plan
    plan.last_recalibrated_at = now
    _record(
        plan,
        {
            "type": "recalibrate",
            "old_vdot": vdot_result["old_vdot"],
            "new_vdot": vdot_result["new_vdot"],
            "delta": vdot_result["delta"],
            "direction": vdot_result["direction"],
            "source": vdot_result["source"],
            "reason": change_plan["reason"],
        },
    )
    db.flush()

    return vdot_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _recently_adjusted(plan: TrainingPlan) -> bool:
    """True if the plan was manually adjusted within the cooldown window."""
    if not plan.last_adjusted_at:
        return False
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - _MANUAL_COOLDOWN
    return plan.last_adjusted_at > cutoff


def _extract_vdot_change(
    vdot_result: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not vdot_result:
        return None
    return {
        "old_vdot": vdot_result["old_vdot"],
        "new_vdot": vdot_result["new_vdot"],
        "direction": vdot_result["direction"],
    }


def _auto_adjust_headline(
    multiplier: float, vdot_change: Optional[Dict[str, Any]]
) -> str:
    direction = "down" if multiplier < 1.0 else "up"
    pct = abs(round((multiplier - 1.0) * 100))

    if vdot_change:
        old_v, new_v = vdot_change["old_vdot"], vdot_change["new_vdot"]
        if direction == "up":
            return (
                f"You're running stronger — bumped upcoming volume ~{pct}% "
                f"and updated your paces (VDOT {old_v} → {new_v})."
            )
        return (
            f"Eased upcoming volume ~{pct}% and updated your paces "
            f"(VDOT {old_v} → {new_v}) — your recent runs suggest dialing back."
        )

    if direction == "up":
        return f"You're handling the load well — bumped upcoming volume ~{pct}%."
    return f"Eased upcoming volume ~{pct}% — your recent runs suggest dialing back."


def _recalibrate_headline(vdot_change: Optional[Dict[str, Any]]) -> str:
    if not vdot_change:
        return "Updated your pace targets based on recent performance."
    old_v, new_v = vdot_change["old_vdot"], vdot_change["new_vdot"]
    if vdot_change["direction"] == "improved":
        return (
            f"Your fitness improved — updated your pace targets "
            f"(VDOT {old_v} → {new_v})."
        )
    return (
        f"Adjusted your pace targets to match current fitness "
        f"(VDOT {old_v} → {new_v})."
    )
