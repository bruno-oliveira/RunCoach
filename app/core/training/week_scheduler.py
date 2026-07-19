"""Week day scheduling.

Assigns workout types to specific days of the week.
"""

from typing import Dict, List, Optional


def schedule_workout_types(
    distribution: Dict[str, int], phase: str, week_number: int, is_recovery_week: bool
) -> List[Optional[str]]:
    """Assign workout types to specific days.

    Recovery is always on Day 2 and does NOT count towards max_runs.
    """
    workout_types: List[Optional[str]] = [None] * 7

    workout_types[1] = "recovery"

    workout_types[5] = "long"
    if distribution.get("long", 0) > 0:
        distribution["long"] -= 1

    if not is_recovery_week:
        quality_count = sum(
            distribution.get(t, 0) for t in ("hill", "interval", "tempo")
        )
        # Space hard days apart. A single quality session sits mid-week
        # (day 4). Two sessions go on days 1 and 4: the recovery day and an
        # easy day separate them, and an easy day always buffers the long
        # run — filling consecutive slots put interval + tempo on
        # back-to-back days. Three (defensive; the distribution caps at
        # two) alternate hard/easy across the week.
        if quality_count >= 3:
            quality_slots = [0, 2, 4]
        elif quality_count == 2:
            quality_slots = [0, 3]
        else:
            quality_slots = [3]
        for day_idx in quality_slots:
            if workout_types[day_idx] is not None:
                continue
            if distribution["hill"] > 0:
                workout_types[day_idx] = "hill"
                distribution["hill"] -= 1
            elif distribution["interval"] > 0:
                workout_types[day_idx] = "interval"
                distribution["interval"] -= 1
            elif distribution["tempo"] > 0:
                workout_types[day_idx] = "tempo"
                distribution["tempo"] -= 1

    # For busy 2-run weeks (1 easy + 1 long), anchor easy on Wed (day_idx 2)
    # so it sits ~3 days from the Saturday long on either side.
    if (
        distribution["easy"] == 1
        and sum(distribution.get(k, 0) for k in ("interval", "tempo", "hill")) == 0
        and workout_types[2] is None
    ):
        workout_types[2] = "easy"
        distribution["easy"] -= 1

    for day_idx in range(7):
        if workout_types[day_idx] is not None:
            continue
        if distribution["easy"] > 0:
            workout_types[day_idx] = "easy"
            distribution["easy"] -= 1

    for day_idx in range(7):
        if workout_types[day_idx] is None:
            workout_types[day_idx] = "rest"
            distribution["rest"] -= 1

    return workout_types
