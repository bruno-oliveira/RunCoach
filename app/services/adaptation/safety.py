"""Shared structural safety guards for adaptation flows.

Keeps recalibration/adjustment outputs aligned with the same practical
constraints as generated plans:
- quality/easy caps relative to long run
- long run dominance cap on 4+ run weeks
- week-over-week 10% growth cap on non-recovery weeks
"""

from __future__ import annotations

from typing import Dict, Iterable, List

from app.core.training.quality_caps import enforce_week_caps


def _running_workouts(workouts: Iterable) -> list:
    return [
        w
        for w in workouts
        if (w.workout_type or "") not in ("rest", "recovery")
        and (w.distance_km or 0) > 0
    ]


def _apply_long_run_ratio_cap(workouts: List, max_ratio: float = 0.55) -> bool:
    """Ensure long run does not dominate weekly volume for 4+ run weeks."""
    running = _running_workouts(workouts)
    if len(running) < 4:
        return False

    long_runs = [w for w in running if (w.workout_type or "") == "long"]
    if not long_runs:
        return False
    long_w = long_runs[0]

    total = sum(w.distance_km or 0 for w in running)
    if total <= 0:
        return False

    max_long = total * max_ratio
    if (long_w.distance_km or 0) <= max_long + 0.05:
        return False

    excess = (long_w.distance_km or 0) - max_long
    long_w.distance_km = round(max_long, 1)

    recipients = [w for w in running if w is not long_w and (w.workout_type or "") == "easy"]
    if not recipients:
        recipients = [w for w in running if w is not long_w]

    if recipients:
        per = excess / len(recipients)
        for w in recipients:
            w.distance_km = round((w.distance_km or 0) + per, 1)

    return True


def enforce_week_structure(workouts: List, target_distance: float, phase: str) -> bool:
    """Apply structural safety constraints to one week's ORM workouts."""
    changed = False
    if enforce_week_caps(workouts, target_distance, phase):
        changed = True
    if _apply_long_run_ratio_cap(workouts):
        changed = True
        # Re-apply easy/quality caps after redistribution.
        enforce_week_caps(workouts, target_distance, phase)
    return changed


def enforce_future_growth_cap(
    ordered_week_numbers: List[int],
    weekly_plans_by_number: Dict[int, object],
    workouts_by_week_id: Dict[str, List],
    pd_week: Dict[int, Dict],
    *,
    high_water_seed: float,
) -> int:
    """Apply 10% week-over-week cap across future non-recovery weeks.

    Returns number of weeks whose workouts were modified.
    """
    high_water = max(0.0, high_water_seed)
    changed_weeks = 0

    for wk_num in ordered_week_numbers:
        week_obj = weekly_plans_by_number[wk_num]
        workouts = workouts_by_week_id.get(week_obj.id, [])
        is_recovery = bool(pd_week.get(wk_num, {}).get("is_recovery", False))

        total = round(sum((w.distance_km or 0) for w in workouts), 1)
        if is_recovery:
            week_obj.total_km = total
            if wk_num in pd_week:
                pd_week[wk_num]["total_km"] = total
            continue

        if high_water <= 0:
            high_water = total
            week_obj.total_km = total
            if wk_num in pd_week:
                pd_week[wk_num]["total_km"] = total
            continue

        ceiling = high_water * 1.10
        if total > ceiling + 0.05:
            flexible = [
                w
                for w in workouts
                if (w.workout_type or "") in ("easy", "long")
                and not getattr(w, "key_workout_id", None)
                and (w.distance_km or 0) > 0
            ]
            if flexible:
                fixed = sum(
                    (w.distance_km or 0)
                    for w in workouts
                    if w not in flexible and (w.distance_km or 0) > 0
                )
                flex_sum = sum((w.distance_km or 0) for w in flexible)
                target_flex = max(0.0, ceiling - fixed)
                if flex_sum > 0 and target_flex < flex_sum:
                    scale = target_flex / flex_sum
                    for w in flexible:
                        w.distance_km = round((w.distance_km or 0) * scale, 1)
                    changed_weeks += 1

        total = round(sum((w.distance_km or 0) for w in workouts), 1)
        week_obj.total_km = total
        if wk_num in pd_week:
            pd_week[wk_num]["total_km"] = total
        if total > high_water:
            high_water = total

    return changed_weeks
