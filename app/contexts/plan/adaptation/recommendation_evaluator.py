"""Auto-triggered adaptation recommendations.

Computes adjustment signals after a training week completes and stores
the result as a pending recommendation on the plan. The user can then
accept (apply) or dismiss it from the plan page.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.core.training.plan_calendar import compute_current_week
from app.models import TrainingPlan
from app.utils import to_date as _to_date

from . import change_reasons as _reasons
from ._helpers import is_current_week_in_progress, today_date
from .adjustment_results import record_adaptation_event
from .change_plan_builder import (
    build_change_plan,
    empty_change_plan,
    snapshot_workouts,
)
from .plan_adjuster import gather_signals
from .tuning import HYSTERESIS_BAND as _HYSTERESIS_BAND
from .vdot_recalibrator import check_vdot_recalibration
from .week_adjuster import apply_adjustment_to_future_weeks

logger = logging.getLogger(__name__)

MIN_RUNS_FOR_RECOMMENDATION = 3


def evaluate_weekly_recommendation(
    plan_id: str,
    user_id: str,
    db: Session,
    *,
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """Compute signals for the most recently completed week and store as pending recommendation.

    Returns the recommendation dict if created, None if skipped.
    """
    training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)

    if not training_plan or not training_plan.start_date:
        return None

    if training_plan.pending_recommendation and not force:
        return None

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    if (today - start_date).days < 0:
        return None

    total_weeks = training_plan.weeks_duration or 0
    current_week = compute_current_week(
        start_date, today, clamp_min=1, total_weeks=total_weeks
    )

    last_completed_week = current_week - 1 if current_week > 1 else None
    if last_completed_week is None:
        return None

    if (
        not force
        and training_plan.last_recommendation_week is not None
        and training_plan.last_recommendation_week >= last_completed_week
    ):
        return None

    gathered = gather_signals(plan_id, user_id, db, run_map=False)
    if gathered is None:
        return None

    signals = gathered["signals"]
    multiplier = signals["multiplier"]

    if abs(multiplier - 1.0) < 0.02:
        training_plan.last_recommendation_week = last_completed_week
        db.commit()
        return None

    direction = "increase" if multiplier > 1.0 else "reduce"
    pct = abs(round((multiplier - 1.0) * 100))

    # Hysteresis: if we'd reverse direction with a small move (< 5%),
    # hold steady. Prevents week-over-week wobble like "+3% / -3% / +3%"
    # that erodes user trust.
    if _is_small_reversal(training_plan.adaptation_history, direction, multiplier):
        training_plan.last_recommendation_week = last_completed_week
        db.commit()
        return None

    reason = (
        f"Based on your week {last_completed_week} performance, "
        f"we recommend {'increasing' if direction == 'increase' else 'reducing'} "
        f"your training by {pct}%."
    )

    volume_ratio = signals.get("volume_ratio", 1.0)
    completion_rate = signals.get("completion_rate", 0)
    avg_effort = signals.get("avg_effort")

    details = []
    if volume_ratio > 1.1:
        details.append("You've been exceeding volume targets.")
    elif volume_ratio < 0.85:
        details.append("Volume has been below target.")
    if completion_rate < 0.7:
        details.append(f"Completion rate is {round(completion_rate * 100)}%.")
    if avg_effort is not None and avg_effort > 7.5:
        details.append(f"Effort is trending high ({avg_effort:.1f}/10).")
    if signals.get("overreach_detected"):
        details.append("Overreach signals detected — recovery prioritized.")
    if details:
        reason += " " + " ".join(details)

    recommendation = {
        "week_evaluated": last_completed_week,
        "multiplier": multiplier,
        "direction": direction,
        "reason": reason,
        "signals": {
            k: signals[k]
            for k in (
                "multiplier",
                "volume_ratio",
                "effort_factor",
                "avg_effort",
                "effort_trend",
                "completion_rate",
                "completion_factor",
                "overreach_detected",
                "current_phase",
                "per_type_ratios",
            )
            if k in signals
        },
        "created_at": today.isoformat(),
    }

    training_plan.pending_recommendation = recommendation
    training_plan.last_recommendation_week = last_completed_week
    db.commit()

    logger.info(
        "Auto-recommendation for plan %s week %d: %s by %d%% (x%.2f)",
        plan_id,
        last_completed_week,
        direction,
        pct,
        multiplier,
    )

    # If the user opted into auto-apply, immediately accept the
    # just-parked recommendation. Weekly cadence + hysteresis still
    # gate this — we apply at most once per ISO week.
    # Local import keeps the plan-adaptation module free of a static edge to
    # the auth context's concrete repository.
    from app.contexts.auth.repositories import SQLAlchemyUserRepository

    user = SQLAlchemyUserRepository(db).get_by_id(user_id)
    if user and user.auto_adjust_enabled:
        applied = _run_accept(plan_id, user_id, db, mode="applied")
        return {
            "action": "auto_adjusted",
            "adjusted": bool(applied.get("adjusted")),
            "reason": applied.get("reason"),
            "multiplier": applied.get("multiplier"),
            "weeks_changed": applied.get("weeks_changed"),
            "workouts_changed": applied.get("workouts_changed"),
            "change_plan": applied.get("change_plan"),
        }

    return {"action": "parked", "recommendation": recommendation}


def accept_recommendation(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Accept the pending recommendation and apply the stored multiplier."""
    return _run_accept(plan_id, user_id, db, mode="applied")


def preview_accept_recommendation(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Compute what accepting the pending recommendation would do."""
    try:
        result = _run_accept(plan_id, user_id, db, mode="preview")
    finally:
        db.rollback()
        db.expire_all()
    return result["change_plan"] if "change_plan" in result else result


def _accept_rejected(mode: str, *, reason: str, headline: str) -> Dict[str, Any]:
    """Build a no-op accept result with an empty change plan."""
    return {
        "accepted": False,
        "reason": reason,
        "change_plan": empty_change_plan(
            action="accept_recommendation", mode=mode, headline_reason=headline
        ),
    }


def _run_accept(
    plan_id: str,
    user_id: str,
    db: Session,
    *,
    mode: str,
) -> Dict[str, Any]:
    training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)

    if not training_plan:
        return _accept_rejected(
            mode,
            reason="We couldn't find that training plan.",
            headline="We couldn't find that training plan.",
        )

    rec = training_plan.pending_recommendation
    if not rec:
        return _accept_rejected(
            mode,
            reason="There's no pending recommendation to apply — it may have already been accepted or dismissed.",
            headline="There's no pending recommendation to apply.",
        )

    multiplier = rec.get("multiplier", 1.0)
    per_type_ratios = rec.get("signals", {}).get("per_type_ratios")

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    current_week = compute_current_week(start_date, today, clamp_min=1, pre_start=1)
    current_day_of_week = today.isoweekday()

    in_progress = is_current_week_in_progress(
        plan_id,
        start_date,
        current_week,
        current_day_of_week,
        db,
    )
    min_first = current_week + 1 if in_progress else current_week
    # Anchor on the recommendation's evaluated week so data from week N
    # always targets week N+1, regardless of when the user accepts. Clamp
    # to min_first so we never reach back into a started week.
    target_first = rec.get("week_evaluated", current_week - 1) + 1
    first_adjustable_week = max(min_first, target_first)

    from app.models import WeeklyPlan

    adjustable_weeks = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number >= first_adjustable_week,
        )
        .all()
    )

    if not adjustable_weeks:
        cp = empty_change_plan(
            action="accept_recommendation",
            mode=mode,
            headline_reason=_reasons.NO_CHANGE_NO_REMAINING_WORKOUTS,
        )
        cp["summary"]["multiplier"] = multiplier
        if mode == "applied":
            training_plan.pending_recommendation = None
            training_plan.last_change_plan = cp
            db.commit()
        return {
            "accepted": False,
            "reason": "All remaining workouts in your plan are already completed or locked — there's nothing left for this recommendation to adjust.",
            "change_plan": cp,
        }

    week_numbers = [w.week_number for w in adjustable_weeks]
    before = snapshot_workouts(training_plan, db, week_numbers=week_numbers)

    recorder: list = []
    weeks_changed, any_distance_changed, counts = apply_adjustment_to_future_weeks(
        training_plan,
        adjustable_weeks,
        multiplier,
        db,
        current_week=current_week,
        current_day_of_week=current_day_of_week,
        per_type_ratios=per_type_ratios,
        recorder=recorder,
    )

    vdot_result = None
    try:
        vdot_result = check_vdot_recalibration(training_plan, user_id, db)
    except Exception as e:
        logger.warning("VDOT recalibration failed (non-fatal): %s", e)

    after = snapshot_workouts(training_plan, db, week_numbers=week_numbers)

    direction = rec.get("direction", "kept")

    vdot_change_payload = None
    if vdot_result:
        vdot_change_payload = {
            "before": vdot_result.get("old_vdot"),
            "after": vdot_result.get("new_vdot"),
            "direction": vdot_result.get("direction"),
        }

    # Build change_plan first so the headline reason uses the same
    # display-rounded counts and net delta the user sees in the modal.
    change_plan = build_change_plan(
        action="accept_recommendation",
        mode=mode,
        training_plan=training_plan,
        before=before,
        after=after,
        recorder=recorder,
        signals={
            "effort_trend": rec.get("signals", {}).get("effort_trend"),
            "completion_rate": rec.get("signals", {}).get("completion_rate"),
            "volume_ratio": rec.get("signals", {}).get("volume_ratio"),
            "phase": rec.get("signals", {}).get("current_phase"),
        },
        multiplier=multiplier,
        vdot_change=vdot_change_payload,
        headline_reason=None,
        current_week=current_week,
        current_day_of_week=current_day_of_week,
    )

    cp_summary = change_plan.get("summary", {})
    canonical_workouts_changed = cp_summary.get(
        "workouts_changed_count", counts["workouts_changed"]
    )
    canonical_total_km_delta = cp_summary.get("total_km_delta", 0.0)

    summary = _build_accept_summary(
        weeks_changed=weeks_changed,
        workouts_changed=canonical_workouts_changed,
        workouts_skipped_protected=counts["workouts_skipped_protected"],
        total_km_delta=canonical_total_km_delta,
    )
    if in_progress and adjustable_weeks:
        summary = (
            f"Current week {current_week} left in place — adjustments apply "
            f"from week {current_week + 1}. " + summary
        )
    change_plan["reason"] = summary

    if mode == "applied":
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        training_plan.adjustment_multiplier = multiplier
        training_plan.last_adjusted_at = now
        training_plan.pending_recommendation = None
        training_plan.last_change_plan = change_plan
        _record_event(
            training_plan,
            {
                "type": "auto_accept",
                "multiplier": multiplier,
                "direction": direction,
                "week_evaluated": rec.get("week_evaluated"),
                "reason": summary,
            },
        )
        db.commit()

    result = {
        "accepted": True,
        "adjusted": any_distance_changed or bool(vdot_result),
        "multiplier": multiplier,
        "weeks_changed": weeks_changed,
        "workouts_changed": canonical_workouts_changed,
        "workouts_skipped_protected": counts["workouts_skipped_protected"],
        "reason": summary,
        "change_plan": change_plan,
    }
    if vdot_result:
        result["vdot_recalibration"] = vdot_result
    return result


def dismiss_recommendation(
    plan_id: str,
    user_id: str,
    db: Session,
) -> Dict[str, Any]:
    """Dismiss the pending recommendation without applying it."""
    training_plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, user_id)

    if not training_plan:
        return {"dismissed": False, "reason": "Plan not found"}

    rec = training_plan.pending_recommendation
    if not rec:
        return {"dismissed": False, "reason": "No pending recommendation"}

    _record_event(
        training_plan,
        {
            "type": "auto_dismiss",
            "multiplier": rec.get("multiplier", 1.0),
            "direction": rec.get("direction", "kept"),
            "week_evaluated": rec.get("week_evaluated"),
            "reason": "User dismissed recommendation.",
        },
    )

    training_plan.pending_recommendation = None
    db.commit()

    return {"dismissed": True}


def _verb_from_delta(total_km_delta: float) -> str:
    """Pick the user-facing verb from the actual net km change.

    The internal `multiplier` is baseline-relative, so a sub-1.0 multiplier
    can still produce a net increase when a prior, more aggressive
    adjustment had pulled distances below baseline. The headline verb has
    to reflect what the user sees on the row (old → new), not the sign of
    the multiplier.
    """
    if total_km_delta > 0.05:
        return "Increased"
    if total_km_delta < -0.05:
        return "Reduced"
    return "Adjusted"


def _build_accept_summary(
    *,
    weeks_changed: int,
    workouts_changed: int,
    workouts_skipped_protected: int,
    total_km_delta: float,
) -> str:
    """Human-readable summary of what an accepted recommendation actually did."""
    if workouts_changed == 0:
        if workouts_skipped_protected > 0:
            return (
                "No distances changed — every affected workout is a key workout, "
                "tempo, interval, or hill session and is preserved as prescribed."
            )
        return "No distances needed adjustment."

    verb = _verb_from_delta(total_km_delta)
    sign = "+" if total_km_delta > 0 else ""
    sentence = (
        f"{verb} {workouts_changed} workout{'s' if workouts_changed != 1 else ''} "
        f"across {weeks_changed} week{'s' if weeks_changed != 1 else ''} "
        f"({sign}{total_km_delta} km total)."
    )
    if workouts_skipped_protected > 0:
        sentence += (
            f" {workouts_skipped_protected} key/tempo/interval workout"
            f"{'s were' if workouts_skipped_protected != 1 else ' was'} preserved."
        )
    return sentence


def _build_auto_adjust_reason(
    *,
    workouts_changed: int,
    week_numbers: list,
    total_km_delta: float,
) -> str:
    """Human-readable summary of what auto-adjust actually changed."""
    if workouts_changed == 0:
        return "No distances needed adjustment."

    verb = _verb_from_delta(total_km_delta)
    sign = "+" if total_km_delta > 0 else ""

    if week_numbers:
        first, last = week_numbers[0], week_numbers[-1]
        weeks_label = f"week {first}" if first == last else f"weeks {first}–{last}"
    else:
        weeks_label = "remaining weeks"

    workout_label = "workout" if workouts_changed == 1 else "workouts"
    return (
        f"{verb} {workouts_changed} {workout_label} across {weeks_label} "
        f"({sign}{total_km_delta} km total)."
    )


def _is_small_reversal(
    history: list | None,
    proposed_direction: str,
    proposed_multiplier: float,
) -> bool:
    """True when the proposal would reverse the last applied direction by < 5%.

    Looks back through ``adaptation_history`` for the most recent applied
    event (``adjust``, ``auto_adjust``, or ``auto_accept``) and compares
    its direction against the current proposal.
    """
    if not history:
        return False
    if abs(proposed_multiplier - 1.0) >= _HYSTERESIS_BAND:
        return False
    last_dir: str | None = None
    for event in reversed(history):
        if event.get("type") not in ("adjust", "auto_adjust", "auto_accept"):
            continue
        d = event.get("direction")
        if d in ("increased", "increase"):
            last_dir = "increase"
            break
        if d in ("reduced", "reduce"):
            last_dir = "reduce"
            break
    if last_dir is None:
        return False
    return last_dir != proposed_direction


def _record_event(training_plan: TrainingPlan, event: Dict[str, Any]) -> None:
    event.setdefault(
        "applied_at",
        datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    )
    # record_adaptation_event stamps ``date`` and handles the append + 20-entry cap.
    record_adaptation_event(training_plan, event)
