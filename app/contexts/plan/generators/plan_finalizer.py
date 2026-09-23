"""Shared final reconciliation for generated training plans.

Generators intentionally mutate weeks in several passes (caps, taper smoothing,
race-day installation, and workout overlays).  This module is the single last
word after those passes: cards and executable steps are reconciled, derived
totals are refreshed, week validation is recomputed, and the plan-level
structure guard sees the exact representation that will be persisted.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from app.contexts.plan.generators.plan_structure_guard import check_plan_structure
from app.contexts.plan.generators.plan_validator import (
    CLAMPED_TARGET_TOLERANCE,
    validate_week_plan,
)
from app.core.training.periodization.training_constants import workouts_training_km
from app.core.training.workouts.workout_steps import (
    compute_distance_from_steps_checked,
    fit_steps_to_distance,
)
from app.core.training.workouts.workout_steps.metrics import _priced_step_km

_RECONCILE_TOLERANCE_KM = 0.1


def reconcile_card_distances(training_plan: List[Dict[str, Any]]) -> int:
    """Reconcile fully-priced executable steps with each card's budget.

    Walking recoveries are deliberately excluded from the displayed running
    dose, matching the structure guard's existing contract. Card distance is
    preserved when easy running can fund a shortfall; irreducible executable
    work wins otherwise. Duration-based steps are left alone because their
    distance is not fully knowable.
    """
    changed = 0
    for week in training_plan:
        for workout in week.get("daily_workouts", []):
            if workout.get("type") in ("rest", "recovery"):
                continue
            steps = workout.get("steps") or []
            if not steps:
                continue
            step_km, fully_priced = compute_distance_from_steps_checked(steps)
            if not fully_priced or step_km <= 0:
                continue
            walk_km = sum(
                _priced_step_km(step) for step in steps if step.get("kind") == "walk"
            )
            executable_running_km = round(max(0.0, step_km - walk_km), 1)
            displayed = workout.get("distance") or 0.0
            if abs(executable_running_km - displayed) > _RECONCILE_TOLERANCE_KM:
                if displayed > executable_running_km:
                    # Preserve the authored work set and fund the card's extra
                    # distance with easy running.  This is preferable to
                    # stretching 800 m reps into odd distances, and it keeps
                    # the weekly budget/long-run share intact.
                    completion = {
                        "kind": "run",
                        "label": "Easy running to complete session",
                        "distance_m": int(
                            round((displayed - executable_running_km) * 1000)
                        ),
                        "pace_zone": "E",
                        "effort": "easy",
                    }
                    insert_at = next(
                        (
                            i
                            for i, step in enumerate(steps)
                            if step.get("kind") == "cooldown"
                        ),
                        len(steps),
                    )
                    workout["steps"] = (
                        steps[:insert_at] + [completion] + steps[insert_at:]
                    )
                else:
                    # The watch prescription is longer than the card.  Trim
                    # repeatable/easy structure to the card budget first; only
                    # if the authored structure cannot be fitted does the card
                    # adopt the irreducible executable dose.
                    fitted = fit_steps_to_distance(steps, displayed + walk_km)
                    workout["steps"] = fitted
                    fitted_km, fitted_priced = compute_distance_from_steps_checked(
                        fitted
                    )
                    if fitted_priced and fitted_km > 0:
                        fitted_walk_km = sum(
                            _priced_step_km(step)
                            for step in fitted
                            if step.get("kind") == "walk"
                        )
                        fitted_running = round(
                            max(0.0, fitted_km - fitted_walk_km), 1
                        )
                        if abs(fitted_running - displayed) > _RECONCILE_TOLERANCE_KM:
                            workout["distance"] = fitted_running

                final_displayed = workout.get("distance") or 0.0
                description = workout.get("description")
                if isinstance(description, str):
                    workout["description"] = re.sub(
                        r"^\d+(?:\.\d+)?\s*km",
                        f"{final_displayed:.1f}km",
                        description,
                        count=1,
                        flags=re.IGNORECASE,
                    )
                changed += 1
    return changed


def refresh_plan_fields(training_plan: List[Dict[str, Any]]) -> None:
    """Refresh totals derived from the final day cards."""
    for week in training_plan:
        workouts = week.get("daily_workouts", [])
        for workout in workouts:
            description = workout.get("description")
            distance = workout.get("distance") or 0.0
            if isinstance(description, str) and distance > 0:
                workout["description"] = re.sub(
                    r"^\d+(?:\.\d+)?\s*km",
                    f"{distance:.1f}km",
                    description,
                    count=1,
                    flags=re.IGNORECASE,
                )
        week["total_km"] = round(
            sum(workout.get("distance", 0) or 0 for workout in workouts), 1
        )
        week["training_km"] = workouts_training_km(workouts)
        if "quality_workouts" in week:
            week["quality_workouts"] = sum(
                1
                for workout in workouts
                if workout.get("quality")
                or workout.get("type") in ("tempo", "interval", "hill")
            )


def finalize_plan(
    training_plan: List[Dict[str, Any]],
    weekly_targets: Iterable[float],
) -> Dict[str, List[str]]:
    """Reconcile and validate the exact plan representation being returned.

    ``weekly_targets`` must already use race-aware accounting where applicable.
    A volume miss is a degraded plan, not a structural error; all other failed
    week checks are classified as errors.  The legacy ``valid`` boolean remains
    for consumers, but now reflects the final rather than an intermediate week.
    """
    reconcile_card_distances(training_plan)
    refresh_plan_fields(training_plan)

    targets = list(weekly_targets)
    for index, week in enumerate(training_plan):
        target = targets[index] if index < len(targets) else week.get("total_km", 0)
        week["weekly_target_km"] = round(target, 1)
        valid, message = validate_week_plan(
            week.get("daily_workouts", []),
            week.get("total_km", 0),
            target,
            week.get("phase", ""),
            tolerance=CLAMPED_TARGET_TOLERANCE,
        )
        if valid:
            status = "valid"
            reason_code = None
        elif message.startswith("Total distance mismatch"):
            status = "degraded"
            reason_code = "volume_deviation"
        else:
            status = "error"
            reason_code = "week_structure"
        week["validation"] = {
            "valid": valid,
            "status": status,
            "reason_code": reason_code,
            "message": message,
        }

    return check_plan_structure(training_plan)
