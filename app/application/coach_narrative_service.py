"""Coach's Note — a recognition-anchored, signal-aware lead for the Today tab.

Assembles a deterministic fact pack from existing read-only assemblers, distils
the runner's own signals into a single "focus" for today (or none), then asks the
injected ``CoachNarrator`` to voice it in three beats: a light recognition
anchor, today's purpose + how to run it, and the focus adjustment when one fires.

Hard numbers are returned as recognition chips computed in Python, never from the
model's prose. Falls back to a deterministic note when the AI voice is
unavailable. Read-only: never commits.
"""

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.application.coach_summary_service import (
    build_coach_patterns,
    build_coach_summary,
    build_readiness_trend,
    build_today,
    build_training_age,
)
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.contexts.runner.profile.profile_builder import build_profile
from app.core.coaching.coaching_notes_generator import generate_coaching_note
from app.core.coaching.recognition import (
    build_fallback_note,
    build_recognition,
    select_today_focus,
)
from app.domain.coaching import CoachNarrator
from app.models import TrainingPlan

logger = logging.getLogger(__name__)

# Mirrors the rolling window the runner profile uses, so the "journey start"
# VDOT comes from the same horizon as the current VDOT.
_JOURNEY_WEEKS = 12

# build_coach_patterns surfaces a pattern per these logged workout types.
_PATTERN_TYPES = ("easy", "recovery", "long", "tempo", "interval")


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
        "focus": facts.get("focus"),
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
    patterns = build_coach_patterns(plan, user_id, db)
    readiness = build_readiness_trend(user_id, db)

    # Journey: earliest vs current VDOT over the same window the profile uses.
    history = RacePredictorService.get_vdot_history(
        user_id, weeks=_JOURNEY_WEEKS, db=db
    )
    vdot_start: Optional[float] = None
    for entry in history:
        if entry.get("vdot") is not None:
            vdot_start = entry["vdot"]
            break

    today_facts = _today_facts(today)
    if today_facts.get("available"):
        # Verbose rationale for the AI voice to compress; the rules note derives
        # its own concise purpose line.
        today_facts["purpose"] = generate_coaching_note(
            today_facts.get("workout_type") or "easy",
            today.get("phase") or "base",
            today.get("current_week") or 1,
            0.0,
        )

    week_pulse_msg = (patterns.get("week_pulse") or {}).get("message")
    latest_readiness = None
    if readiness.get("available") and readiness.get("logs"):
        latest_readiness = readiness["logs"][-1]  # logs are oldest-first

    signals = {
        "overreach": summary.get("overreach_detected", False),
        "direction": summary.get("direction"),
        "tsb_form": (summary.get("form") or {}).get("tsb_form"),
        "effort_trend": summary.get("effort_trend"),
        "vdot_trend": summary.get("vdot_trend"),
        "readiness_status": latest_readiness.get("status")
        if latest_readiness
        else None,
        "readiness_score": latest_readiness.get("score") if latest_readiness else None,
        "today_is_rest": today_facts.get("is_rest", False),
        "today_workout_type": today_facts.get("workout_type"),
        "today_pattern": _today_pattern(patterns, today_facts.get("workout_type")),
    }
    focus = select_today_focus(signals)

    return {
        "today": today_facts,
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
        },
        "week_pulse": week_pulse_msg,
        "focus": focus,
    }


def _today_facts(today: dict[str, Any]) -> dict[str, Any]:
    if not today.get("available"):
        return {"available": False}

    block = today.get("today") or {}
    wtype = block.get("workout_type")
    return {
        "available": True,
        "phase": today.get("phase"),
        "current_week": today.get("current_week"),
        "total_weeks": today.get("total_weeks"),
        "workout_type": wtype,
        "distance_km": block.get("distance_km"),
        "duration_min": block.get("duration_min"),
        "hr_zone_target": block.get("hr_zone_target"),
        "hr_zone_label": block.get("hr_zone_label"),
        "description": block.get("description"),
        # No scheduled session today (block empty) is treated as a rest day.
        "is_rest": wtype in (None, "rest", "recovery") and not block.get("distance_km"),
    }


def _today_pattern(
    patterns: dict[str, Any], workout_type: Optional[str]
) -> Optional[str]:
    """The recency-weighted pace pattern for today's workout type, if any."""
    if not workout_type or workout_type not in _PATTERN_TYPES:
        return None
    for p in patterns.get("patterns") or []:
        if p.get("workout_type") == workout_type:
            return p.get("message")
    return None
