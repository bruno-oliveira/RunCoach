"""Pure trend/drift math for plan-adjustment signals.

Extracted from ``contexts/plan/adaptation/signal_computer`` so the statistics
are unit-testable without a DB. These functions take plain values or
duck-typed run objects (anything with ``.date``/``.effort_quality_score``/
``.effort_class``) and perform no I/O.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.utils import to_date


def compute_quality_drift(
    all_plan_runs: List[Any], today: date
) -> Tuple[Optional[float], float]:
    """Compare ``effort_quality_score`` across first/second half of last 8 runs.

    Returns ``(drift_delta, modifier)`` where the modifier is in
    ``{-0.02, 0.0, +0.02}``.
    """
    runs_with_score = []
    for run in all_plan_runs:
        score = getattr(run, "effort_quality_score", None)
        if score is None:
            continue
        run_date = to_date(run.date) or today
        runs_with_score.append((run_date, score))

    if len(runs_with_score) < 4:
        return None, 0.0

    runs_with_score.sort(key=lambda t: t[0])
    recent = runs_with_score[-8:]
    if len(recent) < 4:
        return None, 0.0

    mid = len(recent) // 2
    first_half = [s for _, s in recent[:mid]]
    second_half = [s for _, s in recent[mid:]]
    if not first_half or not second_half:
        return None, 0.0

    delta = (sum(second_half) / len(second_half)) - (sum(first_half) / len(first_half))
    if delta < -10:
        return delta, -0.02
    if delta > 10:
        return delta, 0.02
    return delta, 0.0


def count_recent_race_efforts(all_plan_runs: List[Any], today: date) -> int:
    """Count runs classified as ``race_effort`` within the last 14 days."""
    cutoff = today - timedelta(days=14)
    count = 0
    for run in all_plan_runs:
        if getattr(run, "effort_class", None) != "race_effort":
            continue
        run_date = to_date(run.date) or today
        if run_date >= cutoff:
            count += 1
    return count


def compute_effort_trend(efforts: List[float]) -> str:
    """Classify a sequence of perceived-effort values as a trend."""
    if len(efforts) < 4:
        return "insufficient_data"
    mid_point = len(efforts) // 2
    first_half_avg = sum(efforts[:mid_point]) / mid_point
    second_half_avg = sum(efforts[mid_point:]) / (len(efforts) - mid_point)
    diff = second_half_avg - first_half_avg
    if diff > 1.0:
        return "increasing"
    elif diff < -1.0:
        return "decreasing"
    return "stable"


def count_consecutive_direction(
    adaptation_history: Optional[List[Dict[str, Any]]],
) -> int:
    """Count how many recent adjustments share the same direction in a row."""
    if not adaptation_history:
        return 0
    count = 0
    last_direction = None
    for event in reversed(adaptation_history):
        direction = event.get("direction")
        if direction in ("increased", "reduced"):
            if last_direction is None:
                last_direction = direction
                count = 1
            elif direction == last_direction:
                count += 1
            else:
                break
        elif direction == "kept":
            break
    return count


__all__ = [
    "compute_quality_drift",
    "count_recent_race_efforts",
    "compute_effort_trend",
    "count_consecutive_direction",
]
