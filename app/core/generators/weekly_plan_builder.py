"""Weekly plan builder.

Handles distance budgeting, scaling, fill-up, and ceiling enforcement
for a single week of training.
"""

from typing import Any, Dict, List, Optional

from app.core.coaching.coaching_notes_generator import generate_coaching_note
from app.core.training.key_workout_library import KeyWorkoutLibrary
from app.core.training.quality_caps import (
    MAX_QUALITY_VS_LONG_RUN,
    MAX_EASY_VS_LONG_RUN,
    get_quality_caps as _get_quality_caps,
)
from app.core.training.training_constants import get_hard_ceiling, calculate_week_in_phase
from app.core.training import workout_steps as _steps_mod
from app.core.training import phase_calculator
from app.core.training import workout_distribution as workout_dist_mod
from app.core.training import workout_builders
from app.core.training import long_run_calculator
from app.core.generators.plan_validator import validate_week_plan


def _inject_pace_into_steps(steps: List[Dict[str, Any]],
                            pace_zones: Optional[Dict]) -> List[Dict[str, Any]]:
    """Clone steps and fill in pace_str from pace_zones when missing."""
    if not pace_zones:
        return [dict(s) for s in steps]
    out = []
    for s in steps:
        new = dict(s)
        zone = new.get('pace_zone')
        if zone and not new.get('pace_str') and zone in pace_zones:
            new['pace_str'] = pace_zones[zone].get('pace_str')
        out.append(new)
    return out


def apply_quality_caps(quality_distances: Dict[str, float],
                       long_run_distance: float,
                       target_distance: float,
                       phase: str) -> Dict[str, float]:
    """Cap each quality workout by the smaller of:
    MAX_QUALITY_VS_LONG_RUN * long_run or the distance-scaled
    physiological cap for that workout type.
    """
    ceiling = long_run_distance * MAX_QUALITY_VS_LONG_RUN
    phys_caps = _get_quality_caps(target_distance, phase)
    capped = dict(quality_distances)
    for key in capped:
        cap = min(ceiling, phys_caps.get(key, ceiling))
        if capped[key] > cap:
            capped[key] = round(cap, 1)
    return capped


def allocate_easy_distances(remaining_km: float,
                            quality_total: float,
                            long_run_distance: float,
                            easy_runs: int) -> List[float]:
    """Distribute the easy-run budget evenly across easy days."""
    if easy_runs <= 0:
        return []
    easy_budget = remaining_km - quality_total
    max_easy = long_run_distance * MAX_EASY_VS_LONG_RUN
    per_run = easy_budget / easy_runs
    return [round(min(per_run, max_easy), 1) for _ in range(easy_runs)]


def build_workout_for_type(workout_type: str, day_number: int,
                           distance: float, total_km: float,
                           phase: str,
                           pace_zones: Optional[Dict]) -> Dict[str, Any]:
    """Dispatch workout creation to the appropriate builder."""
    if workout_type == 'rest':
        return workout_builders.generate_rest_day(day_number)
    if workout_type == 'recovery':
        return workout_builders.generate_recovery_day(day_number, phase)
    if workout_type == 'long':
        return workout_builders.generate_long_run(day_number, distance, total_km, pace_zones=pace_zones)
    if workout_type == 'easy':
        return workout_builders.generate_easy_run(day_number, distance, total_km, pace_zones=pace_zones)
    if workout_type == 'tempo':
        return workout_builders.generate_tempo_run(day_number, distance, total_km, pace_zones=pace_zones)
    if workout_type == 'interval':
        return workout_builders.generate_interval_run(day_number, distance, total_km, pace_zones=pace_zones)
    if workout_type == 'hill':
        return workout_builders.generate_hill_workout(day_number, distance)
    raise ValueError(f"Unknown workout_type: {workout_type}")


def overlay_key_workout(workout: Dict[str, Any], workout_type: str,
                        phase: str, target_distance: float,
                        week_in_phase: int,
                        terrain: Optional[str],
                        pace_zones: Optional[Dict]) -> None:
    """Attach a KeyWorkoutLibrary description for quality sessions in build/peak."""
    if workout_type not in ('interval', 'tempo', 'hill', 'long'):
        return
    if phase not in ('build', 'peak'):
        return
    key_wk = KeyWorkoutLibrary.get_for_phase(
        target_distance, phase, week_in_phase, workout_type, terrain=terrain,
    )
    if not key_wk:
        return
    if pace_zones:
        key_wk = KeyWorkoutLibrary.inject_vdot_paces(key_wk, pace_zones)

    actual_distance = workout.get('distance', 0)
    description = key_wk['description']
    if actual_distance > 0:
        from app.core.training.key_workout_library import _rewrite_key_workout_description
        description = _rewrite_key_workout_description(
            description, key_wk['id'], actual_distance,
        )
    workout['description'] = description
    workout['key_workout_id'] = key_wk['id']
    workout['key_workout_name'] = key_wk['name']
    workout['structure'] = key_wk['structure']
    workout['key_workout_rationale'] = key_wk['rationale']
    if key_wk.get('steps'):
        workout['steps'] = _inject_pace_into_steps(key_wk['steps'], pace_zones)
    elif key_wk.get('steps_builder'):
        from app.core.training.key_workout_library import _resolve_long_steps_builder
        workout['steps'] = _resolve_long_steps_builder(
            key_wk['steps_builder'], workout.get('distance', 0), pace_zones,
        )
    else:
        workout['steps'] = _steps_mod.parse_key_workout_steps(
            key_wk['structure'], pace_zones, workout_type
        )


def generate_daily_workouts(week_number: int, total_km: float,
                            distribution: Dict[str, int],
                            target_distance: float, weeks: int, phase: str,
                            is_recovery_week: bool,
                            vdot: Optional[float] = None,
                            pace_zones: Optional[Dict] = None,
                            experience_level: str = "beginner",
                            week_in_phase: int = 0,
                            terrain: Optional[str] = None,
                            profile: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Generate daily workouts for one week."""
    long_run_distance = long_run_calculator.calculate_long_run_distance(
        total_km, target_distance, weeks, week_number, phase, is_recovery_week,
        experience_level, profile=profile,
    )
    quality_distances = long_run_calculator.calculate_quality_distances(
        total_km, phase, distribution, is_recovery_week, long_run_distance, target_distance,
        terrain=terrain,
    )
    quality_distances = apply_quality_caps(
        quality_distances, long_run_distance, target_distance, phase,
    )

    workout_types = workout_dist_mod.schedule_workout_types(
        distribution.copy(), phase, week_number, is_recovery_week,
    )

    remaining_km = total_km - long_run_distance
    quality_total = sum(quality_distances.values())
    easy_runs = sum(1 for wt in workout_types if wt == 'easy')
    easy_distances = allocate_easy_distances(
        remaining_km, quality_total, long_run_distance, easy_runs,
    )

    easy_run_idx = 0
    strength_session_idx = 0
    workouts: List[Dict[str, Any]] = []

    for day in range(7):
        workout_type = workout_types[day]
        if workout_type is None:
            continue
        day_number = day + 1

        if workout_type == 'easy':
            distance = easy_distances[easy_run_idx] if easy_run_idx < len(easy_distances) else easy_distances[0]
            easy_run_idx += 1
        elif workout_type == 'long':
            distance = long_run_distance
        elif workout_type in ('tempo', 'interval', 'hill'):
            distance = quality_distances.get(workout_type, 0)
        else:
            distance = 0

        workout = build_workout_for_type(
            workout_type, day_number, distance, total_km, phase, pace_zones,
        )

        overlay_key_workout(
            workout, workout_type, phase, target_distance,
            week_in_phase, terrain, pace_zones,
        )

        if workout_type == 'easy':
            strength_session = workout_builders.generate_strength_session(
                day_number, week_number, phase, workout_type,
                session_index=strength_session_idx,
                experience_level=experience_level,
                target_distance=target_distance,
            )
            if strength_session:
                workout['strength_session'] = strength_session
                strength_session_idx += 1

        workout['coaching_rationale'] = generate_coaching_note(
            workout_type, phase, week_number, target_distance, is_recovery_week,
        )
        workouts.append(workout)

    return workouts


def _scale_down(workouts: List[Dict[str, Any]], total_km: float) -> float:
    """Scale workouts down if actual exceeds target (preserves 10% progression cap)."""
    actual_total_km = round(sum(w.get('distance', 0) for w in workouts), 1)
    if actual_total_km > total_km * 1.03 and actual_total_km > 0:
        scale = total_km / actual_total_km
        for w in workouts:
            if w.get('distance', 0) > 0:
                w['distance'] = round(w['distance'] * scale, 1)
        actual_total_km = round(sum(w.get('distance', 0) for w in workouts), 1)
    return actual_total_km


def _fill_shortfall(workouts: List[Dict[str, Any]], total_km: float,
                    actual_total_km: float, target_distance: float) -> float:
    """Fill shortfall by expanding easy and long runs proportionally."""
    if actual_total_km >= total_km * 0.97 or actual_total_km <= 0:
        return actual_total_km

    deficit = total_km - actual_total_km
    has_easy = any(w.get('type') == 'easy' and w.get('distance', 0) > 0 for w in workouts)
    expandable_types = ('easy', 'long') if has_easy else ('easy', 'long', 'tempo', 'interval', 'hill')
    expandable = [w for w in workouts if w.get('type') in expandable_types and w.get('distance', 0) > 0]
    if expandable:
        total_expandable = sum(w['distance'] for w in expandable)
        if total_expandable > 0:
            for w in expandable:
                share = deficit * (w['distance'] / total_expandable)
                w['distance'] = round(w['distance'] + share, 1)

    hard_ceiling = get_hard_ceiling(target_distance)
    long_ws = [w for w in workouts if w.get('type') == 'long' and w.get('distance', 0) > 0]
    if long_ws and long_ws[0]['distance'] > hard_ceiling:
        excess = round(long_ws[0]['distance'] - hard_ceiling, 1)
        long_ws[0]['distance'] = round(hard_ceiling, 1)
        easy_ws = [w for w in workouts
                   if w.get('type') == 'easy' and w.get('distance', 0) > 0]
        if easy_ws:
            per_easy = excess / len(easy_ws)
            for w in easy_ws:
                w['distance'] = round(w['distance'] + per_easy, 1)

    long_ws = [w for w in workouts if w.get('type') == 'long' and w.get('distance', 0) > 0]
    if long_ws:
        long_d = long_ws[0]['distance']
        for w in workouts:
            if w.get('type') == 'easy' and w.get('distance', 0) > long_d:
                transferable = w['distance'] - long_d
                headroom = hard_ceiling - long_d
                transfer = min(transferable, max(0, headroom))
                if transfer > 0:
                    w['distance'] = round(w['distance'] - transfer, 1)
                    long_ws[0]['distance'] = round(long_ws[0]['distance'] + transfer, 1)
                    long_d = long_ws[0]['distance']
                if w['distance'] > long_d + 0.05:
                    w['distance'] = round(long_d, 1)

    return round(sum(w.get('distance', 0) for w in workouts), 1)


def build_weekly_plan(week_number: int, total_km: float, target_distance: float,
                      max_runs_per_week: int, weeks: int,
                      vdot: Optional[float] = None,
                      pace_zones: Optional[Dict] = None,
                      experience_level: str = "beginner",
                      terrain: Optional[str] = None,
                      profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Generate a single week's training plan."""
    phases = phase_calculator.calculate_phases(weeks, target_distance)
    phase = phase_calculator.get_phase(week_number, phases)
    is_recovery = phase_calculator.is_recovery_week(week_number, phase, phases)

    week_in_phase = calculate_week_in_phase(week_number, phase, phases)

    distribution = workout_dist_mod.get_workout_distribution(
        total_km, max_runs_per_week, phase,
        is_recovery, week_number, phases, target_distance,
        terrain=terrain, profile=profile,
    )

    workouts = generate_daily_workouts(
        week_number, total_km, distribution, target_distance, weeks, phase, is_recovery,
        vdot=vdot, pace_zones=pace_zones,
        experience_level=experience_level,
        week_in_phase=week_in_phase,
        terrain=terrain,
        profile=profile,
    )

    actual_total_km = _scale_down(workouts, total_km)
    actual_total_km = _fill_shortfall(workouts, total_km, actual_total_km, target_distance)

    is_valid, validation_message = validate_week_plan(workouts, actual_total_km, total_km, phase)

    training_tips = workout_builders.generate_training_tips(week_number, target_distance)

    return {
        'week': week_number,
        'phase': phase,
        'is_recovery': is_recovery,
        'total_km': actual_total_km,
        'daily_workouts': workouts,
        'training_tips': training_tips,
        'validation': {'valid': is_valid, 'message': validation_message},
        'strength_training': [w['strength_session'] for w in workouts if w.get('strength_session')]
    }
