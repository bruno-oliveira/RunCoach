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

    return {"fatal": fatal, "warnings": warnings}
