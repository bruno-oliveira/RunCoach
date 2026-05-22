"""Week plan validation.

Checks that generated weekly workout plans follow training principles.
"""

from typing import Any, Dict, List


def validate_week_plan(
    workouts: List[Dict[str, Any]], total_km: float, target_total_km: float, phase: str
) -> tuple[bool, str]:
    """Validate week plan follows training principles.

    Checks:
    - All workouts have 'description' field
    - Recovery day has label 'recovery' (not 'recovery_rest')
    - No easy run > 125% of long run distance
    - Total distance matches target (+/-5% tolerance)
    - Recovery days have zero distance
    """
    for workout in workouts:
        if "description" not in workout:
            return (
                False,
                f"Missing description for {workout['type']} on day {workout['day']}",
            )

    for workout in workouts:
        if workout["type"] == "recovery_rest":
            return (
                False,
                f"Old label 'recovery_rest' on day {workout['day']}, should be 'recovery'",
            )

    long_run_dist = max(
        [w.get("distance", 0) for w in workouts if w["type"] == "long"], default=0
    )
    if long_run_dist > 0:
        for workout in workouts:
            if workout["type"] == "easy":
                if workout.get("distance", 0) > long_run_dist * 1.25:
                    return (
                        False,
                        f"Easy run ({workout.get('distance')}km) > 125% of long run ({long_run_dist}km) on day {workout['day']}",
                    )

    tolerance = target_total_km * 0.05
    if abs(total_km - target_total_km) > tolerance:
        return (
            False,
            f"Total distance mismatch: expected {target_total_km}km, got {total_km}km",
        )

    for workout in workouts:
        if workout["type"] == "recovery" and workout.get("distance", 0) != 0:
            return False, f"Recovery day on day {workout['day']} has non-zero distance"

    return True, "Valid"
