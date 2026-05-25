"""Recognition, today's purpose, and signal-driven focus for the Coach's Note.

Pure functions over the fact pack assembled by
``app.application.coach_narrative_service``. The Coach's Note has three beats:

1. recognition  — one light anchor (lifetime consistency / journey)
2. purpose      — what today's session builds and how to run it
3. focus        — the single most important adjustment from the runner's own
                  signals, or nothing when none warrants it

- ``build_recognition`` — accurate chips. Lifetime journey (streak, weeks, VDOT)
  and the plan-week framing ("Week 6 of 12") are kept as *distinct* chips so the
  two scopes never collide into a misleading ratio.
- ``today_purpose_line`` — concise purpose + pace/zone cue (the rules floor; the
  AI path is fed the fuller rationale from ``coaching_notes_generator``).
- ``select_today_focus`` — picks the one adjustment that matters today from the
  runner's signals, or ``None`` so the note never nags.
- ``build_fallback_note`` — the deterministic 3-beat note used when the AI voice
  is unavailable.

No I/O, no ORM — fact pack in, strings out.
"""

from typing import Any, Optional


def _round(value: Any) -> Any:
    return round(value) if isinstance(value, (int, float)) else value


def build_recognition(facts: dict[str, Any]) -> dict[str, Any]:
    """Accurate recognition chips: lifetime journey + plan-week framing.

    Lifetime stats (streak, weeks, VDOT — from all logged runs) and the
    plan-scoped week ("Week 6 of 12") are separate chips, never a ratio that
    mixes the two scopes.
    """
    age = facts.get("training_age") or {}
    today = facts.get("today") or {}
    journey = facts.get("journey") or {}

    streak = age.get("current_streak_weeks") or 0
    longest = age.get("longest_streak_weeks") or 0
    weeks = age.get("weeks_since_first_run") or 0
    total_runs = age.get("total_runs") or 0
    vdot_now = journey.get("vdot_now")
    vdot_start = journey.get("vdot_start")
    current_week = today.get("current_week")
    total_weeks = today.get("total_weeks")

    chips: list[str] = []

    if streak >= 2:
        label = f"{streak}-week streak"
        if longest and streak == longest and longest >= 3:
            label += " (your best)"
        chips.append(label)

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

    if current_week and total_weeks:
        chips.append(f"Week {current_week} of {total_weeks}")

    return {
        "chips": chips,
        "streak_weeks": streak,
        "longest_streak_weeks": longest,
        "weeks_training": weeks,
        "total_runs": total_runs,
        "vdot_now": vdot_now,
        "vdot_start": vdot_start,
        "current_week": current_week,
        "total_weeks": total_weeks,
    }


# Concise purpose + execution cue per workout type — one sentence, for the rules
# note. The AI path is fed the fuller rationale from coaching_notes_generator.
_PURPOSE: dict[str, str] = {
    "easy": "Today's easy run is aerobic base-building — keep it genuinely conversational, slower than feels natural.",
    "recovery": "Today is active recovery — keep it light and short; it's there to flush fatigue, not build fitness.",
    "long": "Today's long run is your endurance cornerstone — relaxed and steady, slow enough you could keep going at the end.",
    "tempo": "Today's tempo is lactate-threshold work — settle into comfortably hard and hold it; controlled, not a race.",
    "interval": "Today's intervals are VO₂max work — commit fully to the hard reps and take the full recovery between them.",
    "hill": "Today's hills build strength and power — short, quick strides, drive the arms, recover on the way down.",
    "fartlek": "Today's fartlek plays with pace — push the surges, stay relaxed on the floats.",
    "race_pace": "Today rehearses race pace — lock into goal effort and groove the rhythm you'll want on race day.",
    "strength": "Today is strength work — quality movement over heavy load; it protects everything else you do.",
}

# Map plan-specific workout types onto the concise purposes above.
_PURPOSE_ALIASES: dict[str, str] = {
    "threshold": "tempo",
    "vo2max": "interval",
    "race": "race_pace",
    "run_walk": "easy",
}

_REST_PURPOSE = (
    "Today is a rest day — adaptation happens now, not on the run. "
    "Protect it as seriously as a workout."
)


def today_purpose_line(today: dict[str, Any]) -> Optional[str]:
    """A concise 'what today builds + how to run it' line, with HR-zone cue."""
    if not today.get("available"):
        return None

    wtype = today.get("workout_type")
    if today.get("is_rest") or not wtype or wtype == "rest":
        return _REST_PURPOSE

    wtype = str(wtype)
    canon = _PURPOSE_ALIASES.get(wtype, wtype)
    base = _PURPOSE.get(canon)
    if not base:
        base = (
            f"Today's {str(wtype).replace('_', ' ')} session — settle in and run "
            "it with intent."
        )

    zone = today.get("hr_zone_target")
    if zone:
        base += f" Aim for ~Zone {zone}."
    return base


def select_today_focus(signals: dict[str, Any]) -> Optional[dict[str, str]]:
    """Pick the single most important coaching adjustment for today, or None.

    Priority is safety-first, then today's execution, then fatigue, then push.
    Returns ``None`` when no signal clears a real threshold — most days — so the
    note stays recognition + purpose and never nags.
    """
    is_rest = signals.get("today_is_rest", False)

    overreach = signals.get("overreach")
    direction = signals.get("direction")
    tsb_form = signals.get("tsb_form")

    # 1. Safety — load/fatigue is high; ease off (applies even on rest days).
    if overreach or tsb_form == "overreached" or direction == "decrease":
        if is_rest:
            return {
                "kind": "ease",
                "message": (
                    "Your signals point to accumulated fatigue, so today's rest is "
                    "perfectly timed — take it seriously and let your body absorb the work."
                ),
            }
        return {
            "kind": "ease",
            "message": (
                "Your signals say ease off right now — recent load and fatigue are "
                "high, so the smart move is to hold back today and let your body "
                "absorb the work."
            ),
        }

    if is_rest:
        return None  # nothing else applies to a rest day

    # 2. Low morning readiness — today-specific.
    status = signals.get("readiness_status")
    score = signals.get("readiness_score")
    if status == "rest" or (isinstance(score, (int, float)) and score < 45):
        return {
            "kind": "readiness_low",
            "message": (
                "Your check-in this morning is low — treat today as truly easy, and "
                "don't hesitate to cut it short or swap for rest if your body's asking."
            ),
        }

    # 3. Execution drift on today's session type (the most actionable cue).
    wtype = signals.get("today_workout_type")
    if signals.get("today_pattern"):
        if wtype in ("easy", "recovery", "long"):
            return {
                "kind": "execution",
                "message": (
                    f"One thing for today: your recent {wtype} runs have drifted "
                    "faster than target. Hold back on purpose — easy has to be easy "
                    "for the hard days to pay off."
                ),
            }
        if wtype in ("tempo", "interval", "threshold", "vo2max"):
            return {
                "kind": "execution",
                "message": (
                    f"Don't shortchange today — your recent {wtype} sessions have come "
                    "in under target pace. Commit to the prescribed effort; that's "
                    "where the fitness is made."
                ),
            }

    # 4. Perceived effort creeping up — watch for fatigue.
    if signals.get("effort_trend") == "increasing":
        return {
            "kind": "effort_watch",
            "message": (
                "Your perceived effort has been creeping up lately — if today feels "
                "harder than the pace should warrant, ease back. Fitness is built in "
                "recovery too."
            ),
        }

    # 5. Primed and ready to step up.
    if direction == "increase" or tsb_form == "primed":
        return {
            "kind": "push",
            "message": (
                "You're fresh and the signals say you've got room — today's a day to "
                "commit fully and get the most out of the session."
            ),
        }

    return None


def build_fallback_note(facts: dict[str, Any]) -> str:
    """Deterministic 3-beat note: recognition → purpose → focus (the rules floor)."""
    age = facts.get("training_age") or {}
    today = facts.get("today") or {}
    focus = facts.get("focus") or {}
    week_pulse = facts.get("week_pulse")

    streak = age.get("current_streak_weeks") or 0
    total_runs = age.get("total_runs") or 0

    sentences: list[str] = []

    # 1. Recognition — one light anchor (the chips carry the detailed numbers).
    if streak >= 3:
        sentences.append(
            f"{streak} straight weeks in the bag — that consistency is the part "
            "most people can't do."
        )
    elif total_runs >= 5:
        sentences.append(
            f"You're {total_runs} runs into this and still showing up — that's the "
            "foundation everything is built on."
        )

    # 2. Purpose — what today builds and how to run it.
    purpose = today_purpose_line(today)
    if purpose:
        sentences.append(purpose)

    # 3. Focus — the single signal-driven adjustment, only if one fired.
    if focus.get("message"):
        sentences.append(focus["message"])

    if not sentences and week_pulse:
        sentences.append(week_pulse)
    if not sentences:
        sentences.append("Keep showing up — consistency is what builds fitness.")

    return " ".join(sentences[:4])
