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

# VDOT zone pace used for each workout type (zone key must match VDOTCalculator output)
WORKOUT_PACE_ZONE: dict[str, str] = {
    "easy": "E",
    "recovery": "E",
    "long": "E",
    "tempo": "T",
    "interval": "I",
    "hill": "T",
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
    mid = _midpoint(lo, hi)

    # ── Effort component (50 pts) ─────────────────────────────────────
    if actual_effort is None:
        effort_score = 25.0  # neutral when no effort data
    elif lo <= actual_effort <= hi:
        effort_score = 50.0
    else:
        deviation = min(abs(actual_effort - lo), abs(actual_effort - hi))
        effort_score = max(0.0, 50.0 - deviation * 12.5)

    # ── Pace component (50 pts) ───────────────────────────────────────
    if planned_pace_min_km and actual_pace_min_km:
        # Allowed tolerance: ±8% of planned pace
        deviation_pct = abs(actual_pace_min_km - planned_pace_min_km) / planned_pace_min_km
        if deviation_pct <= 0.08:
            pace_score = 50.0
        else:
            # Penalise beyond tolerance: lose 5 pts per extra 1%
            excess = deviation_pct - 0.08
            pace_score = max(0.0, 50.0 - excess * 500)
    else:
        pace_score = 25.0  # neutral when no VDOT/pace data

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
