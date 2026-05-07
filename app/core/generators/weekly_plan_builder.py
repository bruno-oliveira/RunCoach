"""Weekly plan builder.

Handles distance budgeting, scaling, fill-up, and ceiling enforcement
for a single week of training.
"""

from typing import Any, Dict, List, Optional

from app.core.coaching.coaching_notes_generator import generate_coaching_note
from app.core.training.key_workout_library import (
    KeyWorkoutLibrary,
    overlay_key_workout,
)
from app.core.training.quality_caps import (
    MAX_QUALITY_VS_LONG_RUN,
    MAX_EASY_VS_LONG_RUN,
    get_quality_caps as _get_quality_caps,
)
from app.core.training.training_constants import get_hard_ceiling, calculate_week_in_phase
from app.core.training import phase_calculator
from app.core.training import workout_distribution as workout_dist_mod
from app.core.training import workout_builders
from app.core.training import long_run_calculator
from app.core.generators.plan_validator import validate_week_plan
from app.core.training.workout_steps import _parse_pace_str_to_min_per_km


# Quality slots with capped distance below this floor are demoted to easy
# rather than scheduled as a thin-stimulus workout. Set just below the
# smallest budget that still leaves room for a meaningful main set after
# warm-up and cool-down.
_QUALITY_DEMOTE_THRESHOLD_KM = 1.5

# Workouts shorter than this get an "≈ X min" UX hint alongside the km value.
_DURATION_HINT_THRESHOLD_KM = 3.0

_PACE_ZONE_FOR_TYPE = {
    'easy': 'E', 'long': 'E', 'tempo': 'T', 'interval': 'I', 'hill': 'I',
}
_DEFAULT_PACE_MIN_PER_KM = {
    'easy': 7.0, 'long': 7.0, 'tempo': 5.5, 'interval': 4.8, 'hill': 5.0,
}


def demote_low_budget_quality(distribution: Dict[str, int],
                              quality_distances: Dict[str, float]) -> None:
    """Demote quality slots whose budget is below the stimulus floor to easy.

    A 1.5 km tempo is a poor experience: the segment math fits but the
    physiological dose is too thin to be worth a quality slot. Convert it
    to an easy run instead — the slot's allocated km flows back into the
    easy budget automatically when ``quality_distances`` shrinks.

    Mutates both inputs in place.
    """
    for qtype in ('tempo', 'interval', 'hill'):
        budget = quality_distances.get(qtype, 0)
        if 0 < budget < _QUALITY_DEMOTE_THRESHOLD_KM and distribution.get(qtype, 0) > 0:
            distribution[qtype] -= 1
            distribution['easy'] = distribution.get('easy', 0) + 1
            quality_distances.pop(qtype, None)


def attach_duration_hints(workouts: List[Dict[str, Any]],
                          pace_zones: Optional[Dict] = None) -> None:
    """Attach a duration_min UX hint to short workouts.

    Pure display annotation: does not modify ``distance`` or ``steps``.
    Only fires for workouts shorter than the hint threshold so cards
    aren't cluttered with redundant minute estimates.
    """
    for w in workouts:
        wtype = w.get('type')
        if wtype not in _PACE_ZONE_FOR_TYPE:
            continue
        dist = w.get('distance', 0) or 0
        if dist <= 0 or dist >= _DURATION_HINT_THRESHOLD_KM:
            continue
        pace_min_km = _pace_for_type(wtype, pace_zones)
        w['duration_min'] = max(1, int(round(dist * pace_min_km)))


def _pace_for_type(wtype: str, pace_zones: Optional[Dict]) -> float:
    """Pace (min/km) for a workout type, preferring VDOT zones when present."""
    if pace_zones:
        zone = _PACE_ZONE_FOR_TYPE.get(wtype)
        if zone and zone in pace_zones:
            parsed = _parse_pace_str_to_min_per_km(
                pace_zones[zone].get('pace_str'), zone,
            )
            if parsed:
                return parsed
    return _DEFAULT_PACE_MIN_PER_KM.get(wtype, 7.0)


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
    """Dispatch workout creation to the registered builder."""
    from app.core.training.workout_registry import build_workout

    return build_workout(
        workout_type,
        day=day_number,
        distance=distance,
        total_km=total_km,
        phase=phase,
        pace_zones=pace_zones,
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
                            profile: Optional[Dict[str, Any]] = None,
                            trail_profile=None) -> List[Dict[str, Any]]:
    """Generate daily workouts for one week."""
    long_run_distance = long_run_calculator.calculate_long_run_distance(
        total_km, target_distance, weeks, week_number, phase, is_recovery_week,
        experience_level, profile=profile, trail_profile=trail_profile,
    )
    quality_distances = long_run_calculator.calculate_quality_distances(
        total_km, phase, distribution, is_recovery_week, long_run_distance, target_distance,
        terrain=terrain, trail_profile=trail_profile,
    )
    quality_distances = apply_quality_caps(
        quality_distances, long_run_distance, target_distance, phase,
    )

    demote_low_budget_quality(distribution, quality_distances)

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
            trail_profile=trail_profile,
        )

        if workout_type == 'easy':
            strength_session = workout_builders.generate_strength_session(
                day_number, week_number, phase, workout_type,
                session_index=strength_session_idx,
                experience_level=experience_level,
                target_distance=target_distance,
                trail_profile=trail_profile,
            )
            if strength_session:
                workout['strength_session'] = strength_session
                strength_session_idx += 1

        workout['coaching_rationale'] = generate_coaching_note(
            workout_type, phase, week_number, target_distance, is_recovery_week,
        )
        workouts.append(workout)

    return workouts


def _rescale_steps(workout: Dict[str, Any], multiplier: float) -> None:
    """Scale every step's distance_m / duration_s by ``multiplier`` so the
    step list stays in sync with the workout's distance.

    Skipped for key-workout-overlaid sessions because their structure is
    authored prescriptively and shouldn't be rubber-banded to fit budget.
    """
    if multiplier == 1.0 or not workout.get('steps'):
        return
    if workout.get('key_workout_id'):
        return
    new_steps = []
    for s in workout['steps']:
        ns = dict(s)
        if ns.get('distance_m'):
            ns['distance_m'] = max(1, int(round(ns['distance_m'] * multiplier)))
        if ns.get('duration_s'):
            ns['duration_s'] = max(1, int(round(ns['duration_s'] * multiplier)))
        new_steps.append(ns)
    workout['steps'] = new_steps


def _set_distance(workout: Dict[str, Any], new_distance: float) -> None:
    """Update ``distance`` and rescale ``steps`` proportionally."""
    old = workout.get('distance', 0) or 0
    rounded = round(new_distance, 1)
    workout['distance'] = rounded
    if old > 0 and rounded > 0:
        _rescale_steps(workout, rounded / old)


def _scale_down(workouts: List[Dict[str, Any]], total_km: float) -> float:
    """Scale workouts down if actual exceeds target (preserves 10% progression cap)."""
    actual_total_km = round(sum(w.get('distance', 0) for w in workouts), 1)
    if actual_total_km > total_km * 1.03 and actual_total_km > 0:
        scale = total_km / actual_total_km
        for w in workouts:
            if w.get('distance', 0) > 0 and not w.get('duration_min'):
                _set_distance(w, w['distance'] * scale)
        actual_total_km = round(sum(w.get('distance', 0) for w in workouts), 1)
    return actual_total_km


def _fill_shortfall(workouts: List[Dict[str, Any]], total_km: float,
                    actual_total_km: float, target_distance: float,
                    trail_profile=None) -> float:
    """Fill shortfall by expanding easy and long runs proportionally."""
    if actual_total_km >= total_km * 0.97 or actual_total_km <= 0:
        return actual_total_km

    deficit = total_km - actual_total_km
    has_easy = any(w.get('type') == 'easy' and w.get('distance', 0) > 0 for w in workouts)
    expandable_types = ('easy', 'long') if has_easy else ('easy', 'long', 'tempo', 'interval', 'hill')
    expandable = [w for w in workouts
                  if w.get('type') in expandable_types
                  and w.get('distance', 0) > 0
                  and not w.get('duration_min')]
    if expandable:
        total_expandable = sum(w['distance'] for w in expandable)
        if total_expandable > 0:
            for w in expandable:
                share = deficit * (w['distance'] / total_expandable)
                _set_distance(w, w['distance'] + share)

    hard_ceiling = get_hard_ceiling(target_distance, trail_profile=trail_profile)
    long_ws = [w for w in workouts if w.get('type') == 'long' and w.get('distance', 0) > 0]
    if long_ws and long_ws[0]['distance'] > hard_ceiling:
        excess = round(long_ws[0]['distance'] - hard_ceiling, 1)
        _set_distance(long_ws[0], hard_ceiling)
        easy_ws = [w for w in workouts
                   if w.get('type') == 'easy' and w.get('distance', 0) > 0]
        if easy_ws:
            per_easy = excess / len(easy_ws)
            for w in easy_ws:
                _set_distance(w, w['distance'] + per_easy)

    long_ws = [w for w in workouts if w.get('type') == 'long' and w.get('distance', 0) > 0]
    if long_ws:
        long_d = long_ws[0]['distance']
        for w in workouts:
            if w.get('type') == 'easy' and w.get('distance', 0) > long_d:
                transferable = w['distance'] - long_d
                headroom = hard_ceiling - long_d
                transfer = min(transferable, max(0, headroom))
                if transfer > 0:
                    _set_distance(w, w['distance'] - transfer)
                    _set_distance(long_ws[0], long_ws[0]['distance'] + transfer)
                    long_d = long_ws[0]['distance']
                if w['distance'] > long_d + 0.05:
                    _set_distance(w, long_d)

    return round(sum(w.get('distance', 0) for w in workouts), 1)


def build_weekly_plan(week_number: int, total_km: float, target_distance: float,
                      max_runs_per_week: int, weeks: int,
                      vdot: Optional[float] = None,
                      pace_zones: Optional[Dict] = None,
                      experience_level: str = "beginner",
                      terrain: Optional[str] = None,
                      profile: Optional[Dict[str, Any]] = None,
                      trail_profile=None) -> Dict[str, Any]:
    """Generate a single week's training plan."""
    phases = phase_calculator.calculate_phases(
        weeks, target_distance, trail_profile=trail_profile,
    )
    phase = phase_calculator.get_phase(week_number, phases)
    is_recovery = phase_calculator.is_recovery_week(week_number, phase, phases)

    week_in_phase = calculate_week_in_phase(week_number, phase, phases)

    distribution = workout_dist_mod.get_workout_distribution(
        total_km, max_runs_per_week, phase,
        is_recovery, week_number, phases, target_distance,
        terrain=terrain, profile=profile,
        trail_profile=trail_profile,
    )

    workouts = generate_daily_workouts(
        week_number, total_km, distribution, target_distance, weeks, phase, is_recovery,
        vdot=vdot, pace_zones=pace_zones,
        experience_level=experience_level,
        week_in_phase=week_in_phase,
        terrain=terrain,
        profile=profile,
        trail_profile=trail_profile,
    )

    actual_total_km = _scale_down(workouts, total_km)
    actual_total_km = _fill_shortfall(
        workouts, total_km, actual_total_km, target_distance,
        trail_profile=trail_profile,
    )

    attach_duration_hints(workouts, pace_zones)

    is_valid, validation_message = validate_week_plan(workouts, actual_total_km, total_km, phase)

    training_tips = workout_builders.generate_training_tips(
        week_number, target_distance, trail_profile=trail_profile,
    )

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
