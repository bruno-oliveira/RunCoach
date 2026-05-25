"""Coach's Note — the recognition-first, AI-voiced lead of the Today tab.

Assembles a deterministic fact pack from existing read-only assemblers (today's
session, training age/streak, adaptation stance, fitness journey), then asks the
injected ``CoachNarrator`` to voice it. Hard numbers are returned separately as
recognition chips so what's displayed is always computed, never hallucinated.
Falls back to a deterministic note when the AI voice is unavailable.

Read-only: never commits.
"""

import logging
from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.application.coach_summary_service import (
    build_coach_summary,
    build_today,
    build_training_age,
)
from app.contexts.plan.plan_date_utils import compute_current_week
from app.contexts.runner.enrichment.week_pulse_generator import get_week_pulse
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.contexts.runner.profile.profile_builder import build_profile
from app.core.coaching.recognition import build_fallback_note, build_recognition
from app.domain.coaching import CoachNarrator
from app.models import TrainingPlan
from app.utils import to_date as _to_date

logger = logging.getLogger(__name__)

# Mirrors the rolling window the runner profile uses, so the "journey start"
# VDOT comes from the same horizon as the current VDOT.
_JOURNEY_WEEKS = 12


def build_coach_note(
    plan: TrainingPlan,
    user_id: str,
    db: Session,
    narrator: CoachNarrator,
) -> dict[str, Any]:
    """The Coach's Note payload: prose + accurate recognition chips."""
    # Gate on the same "3 linked runs" threshold the rest of the Coach hub uses.
    summary = build_coach_summary(plan, user_id, db)
    if not summary.get("available"):
        return {
            "available": False,
            "reason": summary.get(
                "reason",
                "Log a few runs linked to this plan to unlock your coach's note.",
            ),
        }

    facts = _assemble_facts(plan, user_id, db, summary)

    recognition = build_recognition(facts)
    note = narrator.generate_note(facts)
    source = "ai"
    if not note:
        note = build_fallback_note(facts)
        source = "rules"

    return {
        "available": True,
        "source": source,
        "note": note,
        "recognition": recognition,
        "today": facts.get("today"),
    }


def _assemble_facts(
    plan: TrainingPlan,
    user_id: str,
    db: Session,
    summary: dict[str, Any],
) -> dict[str, Any]:
    today = build_today(plan, user_id, db)
    age = build_training_age(user_id, db)
    profile = build_profile(user_id, db)

    # Journey: earliest vs current VDOT over the same window the profile uses.
    history = RacePredictorService.get_vdot_history(
        user_id, weeks=_JOURNEY_WEEKS, db=db
    )
    vdot_start: Optional[float] = None
    for entry in history:
        if entry.get("vdot") is not None:
            vdot_start = entry["vdot"]
            break

    week_pulse_msg = _week_pulse_message(plan, today, db)

    return {
        "today": _today_facts(today),
        "training_age": {
            k: age.get(k)
            for k in (
                "weeks_since_first_run",
                "total_runs",
                "total_km",
                "current_streak_weeks",
                "longest_streak_weeks",
                "avg_runs_per_week",
            )
        }
        if age.get("available")
        else {},
        "journey": {
            "vdot_now": profile.current_vdot,
            "vdot_start": vdot_start,
            "vdot_trend": profile.vdot_trend,
            "easy_pct": profile.easy_pct,
            "efficiency_trend_pct": profile.efficiency_trend_pct,
            "weeks_of_data": profile.weeks_of_data,
        },
        "stance": {
            "direction": summary.get("direction"),
            "multiplier": summary.get("multiplier"),
            "tsb_form": (summary.get("form") or {}).get("tsb_form"),
            "effort_trend": summary.get("effort_trend"),
            "overreach": summary.get("overreach_detected", False),
            "headline_reason": summary.get("headline_reason"),
        },
        "week_pulse": week_pulse_msg,
    }


def _today_facts(today: dict[str, Any]) -> dict[str, Any]:
    if not today.get("available"):
        return {"available": False}

    week = today.get("week") or []
    done = sum(1 for d in week if d.get("status") == "done")
    # "due so far" = sessions whose day has arrived (done / missed / today),
    # excluding rest days — so "3/3" reads as recognition, not "behind".
    due = sum(1 for d in week if d.get("status") in ("done", "missed", "today"))

    block = today.get("today") or {}
    wtype = block.get("workout_type")
    return {
        "available": True,
        "phase": today.get("phase"),
        "current_week": today.get("current_week"),
        "total_weeks": today.get("total_weeks"),
        "workout_type": wtype,
        "distance_km": block.get("distance_km"),
        "description": block.get("description"),
        "is_rest": wtype in (None, "rest", "recovery") and not block.get("distance_km"),
        "week_pct": today.get("week_pct"),
        "week_actual_km": today.get("week_actual_km"),
        "week_planned_km": today.get("week_planned_km"),
        "done_this_week": done,
        "due_this_week": due,
    }


def _week_pulse_message(
    plan: TrainingPlan, today: dict[str, Any], db: Session
) -> Optional[str]:
    if not plan.start_date:
        return None
    current_week = today.get("current_week") or compute_current_week(
        _to_date(plan.start_date), date.today(), clamp_min=1, pre_start=1
    )
    pulse = get_week_pulse(plan, current_week, db)
    return pulse.get("message") if pulse else None
