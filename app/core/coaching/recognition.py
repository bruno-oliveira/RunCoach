"""Recognition facts + deterministic fallback note for the Coach's Note.

Pure functions over the fact pack assembled by
``app.application.coach_narrative_service``. Two responsibilities:

- ``build_recognition`` — the guaranteed-accurate chips ("7-week streak",
  "VDOT 44->48"). These render straight from computed numbers, never from the
  model's prose, so displayed facts are always correct.
- ``build_fallback_note`` — a warm, rules-based note used when the AI voice is
  unavailable (no API key, call failed). This is the deterministic floor.

No I/O, no ORM — fact pack in, strings out.
"""

from typing import Any


def _round(value: Any) -> Any:
    return round(value) if isinstance(value, (int, float)) else value


def build_recognition(facts: dict[str, Any]) -> dict[str, Any]:
    """Build accurate recognition chips and the raw facts behind them."""
    age = facts.get("training_age") or {}
    today = facts.get("today") or {}
    journey = facts.get("journey") or {}

    streak = age.get("current_streak_weeks") or 0
    longest = age.get("longest_streak_weeks") or 0
    weeks = age.get("weeks_since_first_run") or 0
    total_runs = age.get("total_runs") or 0
    done = today.get("done_this_week") or 0
    due = today.get("due_this_week") or 0
    vdot_now = journey.get("vdot_now")
    vdot_start = journey.get("vdot_start")

    chips: list[str] = []

    if streak >= 2:
        label = f"{streak}-week streak"
        if longest and streak == longest and longest >= 3:
            label += " (your best)"
        chips.append(label)

    if due > 0:
        chips.append(f"{done}/{due} sessions this week")

    if weeks >= 3:
        chips.append(f"{weeks} weeks training")
    elif total_runs >= 5:
        chips.append(f"{total_runs} runs logged")

    if (
        isinstance(vdot_now, (int, float))
        and isinstance(vdot_start, (int, float))
        and vdot_now - vdot_start >= 0.5
    ):
        chips.append(f"VDOT {_round(vdot_start)}→{_round(vdot_now)}")

    return {
        "chips": chips,
        "streak_weeks": streak,
        "longest_streak_weeks": longest,
        "weeks_training": weeks,
        "total_runs": total_runs,
        "done_this_week": done,
        "due_this_week": due,
        "vdot_now": vdot_now,
        "vdot_start": vdot_start,
    }


def build_fallback_note(facts: dict[str, Any]) -> str:
    """A deterministic, recognition-first coach's note (the rules floor)."""
    age = facts.get("training_age") or {}
    today = facts.get("today") or {}
    journey = facts.get("journey") or {}
    week_pulse = facts.get("week_pulse")

    streak = age.get("current_streak_weeks") or 0
    total_runs = age.get("total_runs") or 0
    done = today.get("done_this_week") or 0
    due = today.get("due_this_week") or 0

    sentences: list[str] = []

    # 1. Recognition — lead by acknowledging the athlete.
    if streak >= 3:
        sentences.append(
            f"You've put together {streak} straight weeks of training — that "
            "consistency is the foundation everything else is built on."
        )
    elif done and due and done >= due:
        sentences.append(
            f"You've hit every session due this week ({done} of {due}) — "
            "exactly the kind of week that compounds."
        )
    elif total_runs:
        sentences.append(
            f"You're {total_runs} runs into this — showing up is the hard part, "
            "and you're doing it."
        )

    # 2. Continuity — connect to the journey.
    vdot_now = journey.get("vdot_now")
    vdot_start = journey.get("vdot_start")
    if (
        isinstance(vdot_now, (int, float))
        and isinstance(vdot_start, (int, float))
        and vdot_now - vdot_start >= 0.5
    ):
        sentences.append(
            f"Your fitness has climbed from a VDOT of about {_round(vdot_start)} "
            f"to {_round(vdot_now)} along the way."
        )
    elif journey.get("vdot_trend") == "improving":
        sentences.append("Your fitness is trending up — the work is paying off.")

    # 3. Today — frame the session.
    if today.get("available"):
        phase = today.get("phase")
        if today.get("is_rest"):
            sentences.append(
                "Today is a rest day, and that's not time off — it's when the "
                "adaptation actually happens."
            )
        elif today.get("workout_type"):
            wtype = str(today["workout_type"]).replace("_", " ")
            dist = today.get("distance_km")
            dist_str = (
                f" ({dist:g} km)" if isinstance(dist, (int, float)) and dist else ""
            )
            phase_str = f" in your {phase} phase" if phase else ""
            sentences.append(
                f"Today's a {wtype} session{dist_str}{phase_str} — settle in and "
                "trust the plan."
            )

    if not sentences and week_pulse:
        sentences.append(week_pulse)

    if not sentences:
        sentences.append("Keep showing up — consistency is what builds fitness.")

    return " ".join(sentences[:4])
