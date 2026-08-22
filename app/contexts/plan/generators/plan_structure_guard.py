"""Plan-level structural guard — a safety net over a whole generated plan.

The per-week :func:`validate_week_plan` checks one week in isolation, but nothing
looks at the finished plan as a whole or *acts* on a degenerate result. The
week-level scaling, ratio caps, and smoothing passes are individually correct,
yet a pathological input (very low base, sparse frequency) could in principle
compose them into a week with no runnable session or a collapsed total.

This module runs once, after all smoothing, and classifies problems into two
tiers:

- **fatal** — a week that prescribes nothing runnable, or a non-recovery week
  whose total has collapsed below a viable floor. A plan like this is unusable
  and should fail loudly (``PlanGenerationException``) rather than be served.
- **warning** — softer inconsistencies (e.g. an easy run rivaling the long run
  that slipped past the per-week cap). These are logged for telemetry but do not
  block the plan.

The floors are deliberately generous: they exist to catch genuine breakage, not
to second-guess the honestly-proportionate small plans a low-mileage runner asks
for.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# A non-recovery week below this total has effectively collapsed — even the
# smallest legitimate plan (5 km/week base, 5K, race-week taper) stays well
# above it, so tripping this means something composed wrong upstream.
MIN_VIABLE_NON_RECOVERY_KM = 2.0

# An easy run should never exceed the long run by more than this factor. The
# per-week validator enforces 1.25×; this is the same invariant re-checked
# after the plan-level scaling passes, which can move distances again.
MAX_EASY_VS_LONG = 1.25

# A card's distance and its step list must agree: the steps are what the watch
# executes and what the runner is actually asked to run, so a divergence means
# one of the two is lying. Walk-recovery ground is allowed to be excluded from
# the displayed distance (a hike-run's walk breaks are real ground but not the
# session's running dose), so the check accepts anything in that band.
STEPS_DISTANCE_TOLERANCE_KM = 0.5

_NON_RUNNING_TYPES = ("rest", "recovery")


def _running_workouts(week: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        w
        for w in week.get("daily_workouts", [])
        if w.get("type") not in _NON_RUNNING_TYPES and (w.get("distance") or 0) > 0
    ]


def check_plan_structure(training_plan: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Classify structural problems in a finished plan.

    Returns ``{"fatal": [...], "warnings": [...]}`` — both lists empty when the
    plan is coherent. Never mutates the plan.
    """
    fatal: List[str] = []
    warnings: List[str] = []

    if not training_plan:
        fatal.append("plan has no weeks")
        return {"fatal": fatal, "warnings": warnings}

    for week in training_plan:
        num = week.get("week", "?")
        phase = week.get("phase", "?")
        is_recovery = week.get("is_recovery", False)
        total = week.get("total_km", 0) or 0
        running = _running_workouts(week)

        if not running:
            fatal.append(f"week {num} ({phase}): no runnable workout")
            continue

        if not is_recovery and total < MIN_VIABLE_NON_RECOVERY_KM:
            fatal.append(
                f"week {num} ({phase}): total {total} km below viable floor "
                f"{MIN_VIABLE_NON_RECOVERY_KM} km"
            )

        long_km = max(
            (w.get("distance", 0) or 0 for w in running if w.get("type") == "long"),
            default=0,
        )
        if long_km > 0:
            for w in running:
                if (
                    w.get("type") == "easy"
                    and (w.get("distance", 0) or 0) > long_km * MAX_EASY_VS_LONG
                ):
                    warnings.append(
                        f"week {num} ({phase}): easy run {w.get('distance')} km "
                        f"exceeds {MAX_EASY_VS_LONG:g}× long run {long_km} km"
                    )

        warnings.extend(_step_distance_warnings(week, num, phase))

    return {"fatal": fatal, "warnings": warnings}


def _step_distance_warnings(week: Dict[str, Any], num: Any, phase: str) -> List[str]:
    """Flag workouts whose card distance disagrees with their step list.

    This is the check that would have caught a capped race-rehearsal long run
    whose prose was re-rendered to 28.8 km while its steps still executed
    30.7 km: the runner read one session and their watch got another. Priced
    as a warning rather than a fatal because an unpriceable duration-based
    step makes the step total a lower bound, not a contradiction.
    """
    from app.core.training.workout_steps import compute_distance_from_steps_checked
    from app.core.training.workout_steps.metrics import _priced_step_km

    out: List[str] = []
    for w in week.get("daily_workouts", []):
        distance = w.get("distance") or 0
        steps = w.get("steps") or []
        if distance <= 0 or not steps:
            continue
        step_km, fully_priced = compute_distance_from_steps_checked(steps)
        if not fully_priced or step_km <= 0:
            continue
        walk_km = sum(_priced_step_km(s) for s in steps if s.get("kind") == "walk")
        low = step_km - walk_km - STEPS_DISTANCE_TOLERANCE_KM
        high = step_km + STEPS_DISTANCE_TOLERANCE_KM
        if not low <= distance <= high:
            out.append(
                f"week {num} ({phase}) day {w.get('day')}: {w.get('type')} "
                f"shows {distance} km but its steps total {step_km:.1f} km"
                + (f" ({walk_km:.1f} km of it walking)" if walk_km else "")
            )
    return out
