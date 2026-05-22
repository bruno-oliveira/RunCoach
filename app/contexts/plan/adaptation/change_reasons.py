"""Human-readable reasons for adaptation outcomes.

Centralizes the strings shown in the change-plan modal so every
adaptation path (manual adjust, recommendation accept, recalibrate,
reset, per-week override, auto-adjust) surfaces consistent copy.
"""

# Reasons attached to per-workout entries that were left unchanged
# despite being inside the adjustment window.
PROTECTED_TEMPO = (
    "Tempo workouts are not auto-scaled — pace targets matter more than distance."
)
PROTECTED_INTERVAL = (
    "Interval sessions keep their prescribed distance; load is controlled via pace."
)
PROTECTED_HILL = "Hill repeats are kept at the prescribed distance."
PROTECTED_KEY_WORKOUT = "Key race-specific workout — preserved to anchor the phase."

# Reasons attached to workouts that were changed but with a guardrail.
LONG_RUN_FLOOR = (
    "Long run kept at baseline — scaling down further would erode endurance."
)
QUALITY_HALF_SCALED = (
    "Quality session scaled at half strength to balance load and recovery."
)
GROWTH_CAP = "Weekly growth capped to keep the 10% rule intact."

# Reasons explaining a plan-wide "no change" outcome.
NO_CHANGE_MULTIPLIER_NEUTRAL = (
    "Adjustment multiplier landed within ±2% of 1.00 — no scaling applied."
)
NO_CHANGE_NO_REMAINING_WORKOUTS = (
    "No remaining workouts to adjust — all upcoming sessions are past the cut-off."
)
NO_CHANGE_ALL_PROTECTED = "Every remaining eligible workout is protected (tempo, intervals, hills, or a key workout)."
NO_CHANGE_INSUFFICIENT_DATA = (
    "Not enough recent run data to recommend a change (need at least 3 logged runs)."
)
NO_CHANGE_PLAN_NOT_STARTED = (
    "Plan has not started yet — adjustment runs after the first training week."
)
NO_CHANGE_NO_ACTIVE_ADJUSTMENT = (
    "Plan is already on its original baseline distances — nothing to reset."
)
NO_CHANGE_DISTANCES_IDENTICAL = (
    "Computed distances matched the existing plan — nothing to change."
)


def protected_reason_for_workout(
    workout_type: str | None, has_key_workout_id: bool
) -> str:
    """Return the protection reason for a skipped workout."""
    if has_key_workout_id:
        return PROTECTED_KEY_WORKOUT
    if workout_type == "tempo":
        return PROTECTED_TEMPO
    if workout_type == "interval":
        return PROTECTED_INTERVAL
    if workout_type == "hill":
        return PROTECTED_HILL
    return PROTECTED_KEY_WORKOUT
