"""Compare a finished single run with what was prescribed.

"Done · 8.0 km · 5:01/km" tells a runner they ran. It does not tell them
whether they ran the session — and the commonest miss is invisible in those
numbers: an easy run done faster than easy.

Two kinds of session, two honest comparisons:

* **Steady** (easy, long): one step with a pace range, so the run's average
  pace is compared with that range directly.
* **Structured** (tempo, intervals): the average of a run that mixes a warm-up
  jog with threshold work means nothing against the work pace. It is compared
  instead with the average the *whole prescribed session* works out to.

What this does not do is judge each step. That needs lap data, and the
Intervals.icu import stores one average per run — a per-rep verdict built from
that would be invented.
"""

from dataclasses import dataclass
from typing import Any, Optional

from app.core.training.workouts.workout_steps.intervals_export import (
    _parse_pace_bounds,
    build_intervals_workout,
)

# Pace within this share of a single target counts as hitting it.
_PACE_TOLERANCE = 0.03
# Distance within this share of the prescription counts as the full session.
_DISTANCE_TOLERANCE = 0.1

ON_TARGET = "on_target"
FASTER = "faster"
SLOWER = "slower"

FULL = "full"
SHORT = "short"
OVER = "over"


@dataclass(frozen=True)
class SingleRunReview:
    """Prescribed vs done, in the units the card prints."""

    # Target as (slow, fast) min/km; equal when the target is a single pace.
    target_slow: float
    target_fast: float
    actual_pace: float
    pace_verdict: str
    distance_verdict: str
    # True when the target is the planned whole-session average rather than a
    # pace the runner was asked to hold.
    is_session_average: bool


def _planned_average(workout: dict[str, Any]) -> Optional[float]:
    """Average min/km of the whole prescribed session, from its own steps."""
    try:
        seconds = build_intervals_workout(workout)["moving_time"]
    except ValueError:
        return None
    distance = float(workout.get("distance") or 0.0)
    if not seconds or distance <= 0:
        return None
    return seconds / 60.0 / distance


def review_single_run(
    workout: dict[str, Any],
    run_distance_km: Optional[float],
    run_pace_min_km: Optional[float],
) -> Optional[SingleRunReview]:
    """Judge a logged run against the session it completed.

    Returns:
        None when there is nothing to compare: the run has no pace, or the
        session was prescribed by effort (no fitness on record at the time).
    """
    if not run_pace_min_km or run_pace_min_km <= 0:
        return None
    steps = workout.get("steps") or []
    paced = [step for step in steps if step.get("pace_str")]
    if not paced:
        return None

    if len(steps) == 1:
        bounds = _parse_pace_bounds(paced[0].get("pace_str"))
        if not bounds:
            return None
        slow, fast = max(bounds), min(bounds)
        is_average = False
    else:
        average = _planned_average(workout)
        if average is None:
            return None
        slow = fast = average
        is_average = True

    if slow == fast:
        slow, fast = slow * (1 + _PACE_TOLERANCE), fast * (1 - _PACE_TOLERANCE)
        shown_slow = shown_fast = (slow + fast) / 2.0
    else:
        shown_slow, shown_fast = slow, fast

    if run_pace_min_km < fast:
        pace_verdict = FASTER
    elif run_pace_min_km > slow:
        pace_verdict = SLOWER
    else:
        pace_verdict = ON_TARGET

    prescribed = float(workout.get("distance") or 0.0)
    ran = run_distance_km or 0.0
    if prescribed <= 0 or abs(ran - prescribed) <= prescribed * _DISTANCE_TOLERANCE:
        distance_verdict = FULL
    else:
        distance_verdict = SHORT if ran < prescribed else OVER

    return SingleRunReview(
        target_slow=shown_slow,
        target_fast=shown_fast,
        actual_pace=run_pace_min_km,
        pace_verdict=pace_verdict,
        distance_verdict=distance_verdict,
        is_session_average=is_average,
    )
