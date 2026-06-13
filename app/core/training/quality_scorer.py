"""Effort quality scorer.

Compares a logged run against the planned workout and assigns a
quality score (0–100) and a human-readable label.
"""

from typing import Optional, Tuple

# Expected perceived-effort (PE) range for each workout type [min, max]
EXPECTED_EFFORT: dict[str, Tuple[int, int]] = {
    "easy": (3, 5),
    "recovery": (1, 3),
    "long": (5, 7),
    "tempo": (6, 7),
    "interval": (7, 9),
    "hill": (7, 8),
    "strength": (4, 6),
    "rest": (1, 2),
}

# VDOT zone pace used for each workout type (zone key must match VDOTCalculator output).
# Hill reps are short (~30 s) uphill efforts built at R-pace effort; average pace
# on a hill is not a meaningful target, so the scorer treats hills as effort-only
# (see calculate_quality_score) and this entry is for display/labelling alignment.
WORKOUT_PACE_ZONE: dict[str, str] = {
    "easy": "E",
    "recovery": "E",
    "long": "E",
    "tempo": "T",
    "interval": "I",
    "hill": "R",
}


def _midpoint(lo: int, hi: int) -> float:
    return (lo + hi) / 2.0


def calculate_quality_score(
    actual_effort: Optional[int],
    actual_pace_min_km: Optional[float],
    workout_type: str,
    planned_pace_min_km: Optional[float] = None,
) -> Tuple[float, str]:
    """Calculate an effort quality score for a logged run.

    Args:
        actual_effort:       Perceived effort (1–10) reported by the user, or None
        actual_pace_min_km:  Actual average pace in min/km, or None
        workout_type:        Planned workout type (easy, tempo, interval, …)
        planned_pace_min_km: Expected pace from VDOT zones, or None

    Returns:
        (score, label) where score is 0–100 and label is one of:
        "Nailed it", "On track", "Too easy", "Too hard"
    """
    wtype = workout_type.lower() if workout_type else "easy"
    effort_range = EXPECTED_EFFORT.get(wtype, (4, 7))
    lo, hi = effort_range

    # Hills are short uphill reps where average pace is physically meaningless
    # (the gradient dominates, GPS pace is noise), so they are scored on effort
    # alone — 100% effort, no pace component — regardless of any planned pace
    # that may be attached. Other quality types use 40% effort / 60% pace.
    is_hill = wtype == "hill"
    if is_hill:
        effort_max = 100.0
        pace_max = 0.0
    else:
        effort_max = 40.0
        pace_max = 60.0
    neutral_effort = effort_max / 2.0
    neutral_pace = pace_max / 2.0

    # ── Effort component ──────────────────────────────────────────────
    if actual_effort is None:
        effort_score = neutral_effort
    elif lo <= actual_effort <= hi:
        effort_score = effort_max
    else:
        deviation = min(abs(actual_effort - lo), abs(actual_effort - hi))
        effort_score = max(0.0, effort_max - deviation * (effort_max / 4.0))

    # ── Pace component ────────────────────────────────────────────────
    if planned_pace_min_km and actual_pace_min_km:
        # Allowed tolerance: ±8% of planned pace
        deviation_pct = (
            abs(actual_pace_min_km - planned_pace_min_km) / planned_pace_min_km
        )
        if deviation_pct <= 0.08:
            pace_score = pace_max
        else:
            # Penalise beyond tolerance: lose points per extra 1%
            excess = deviation_pct - 0.08
            pace_score = max(0.0, pace_max - excess * (pace_max / 0.10))
    else:
        pace_score = neutral_pace

    total = effort_score + pace_score

    # ── Label ─────────────────────────────────────────────────────────
    if total >= 85:
        label = "Nailed it"
    elif total >= 65:
        label = "On track"
    elif actual_effort is not None and actual_effort < lo:
        label = "Too easy"
    elif actual_effort is not None and actual_effort > hi:
        label = "Too hard"
    else:
        label = "On track"  # pace-only miss without effort extreme

    return round(total, 1), label
