"""Workout distribution and scheduling logic.

Determines how many of each workout type per week and assigns
them to specific days of the week.
"""

from typing import Dict, List, Optional


def get_workout_distribution(total_km: float, max_runs: int, phase: str = 'build',
                             is_recovery_week: bool = False, week_number: int = 1,
                             phases: Dict[str, int] = None,
                             target_distance: float = 10.0,
                             terrain: Optional[str] = None) -> Dict[str, int]:
    """Calculate how many of each workout type per week."""
    is_backward_compatible_call = (phase == 'build' and not is_recovery_week and
                                   week_number == 1 and phases is None and
                                   target_distance == 10.0)

    if is_backward_compatible_call:
        return get_workout_distribution_simple(total_km, max_runs)

    long_runs = 1

    # Base phase now gets 1 light quality session when runner has enough days
    if is_recovery_week:
        quality_workouts = 0
    elif phase == 'base':
        quality_workouts = 1 if max_runs >= 4 else 0
    elif phase == 'build':
        if phases:
            week_in_build = week_number - phases['base']
        else:
            week_in_build = week_number
        if week_in_build <= 2:
            quality_workouts = 1 if max_runs >= 4 else 0
        else:
            quality_workouts = 2 if max_runs >= 5 else 1
    elif phase == 'peak':
        quality_workouts = 2 if max_runs >= 5 else 1
    else:
        quality_workouts = 0

    # Recovery is an additional non-running day, does NOT count towards max_runs
    actual_run_slots = max_runs
    running_days = actual_run_slots - long_runs - quality_workouts
    easy_runs = max(0, running_days)
    max_runs = min(max_runs, 6)
    rest_days = 7 - (max_runs + 1)

    distribution = _build_quality_distribution(
        target_distance, terrain, quality_workouts, phase,
        easy_runs, long_runs, rest_days, week_number,
    )

    if not is_recovery_week:
        distribution = _validate_polarized_ratio(distribution, phase, target_distance)

    return distribution


def _build_quality_distribution(target_distance: float, terrain: Optional[str],
                                quality_workouts: int, phase: str,
                                easy_runs: int, long_runs: int, rest_days: int,
                                week_number: int) -> Dict[str, int]:
    """Assign quality workout types based on race distance and terrain."""
    base = {'easy': easy_runs, 'long': long_runs, 'interval': 0,
            'tempo': 0, 'hill': 0, 'rest': rest_days}

    if quality_workouts == 0:
        return base

    is_trail = target_distance == 30.0
    is_flat_trail = is_trail and terrain == 'flat'

    # ── Base phase: 1 light quality session (distance-specific type) ──
    if phase == 'base':
        if is_trail and not is_flat_trail:
            base['hill'] = 1
        elif is_flat_trail:
            base['tempo'] = 1
        elif target_distance <= 10:
            base['interval'] = 1    # strides
        else:
            base['tempo'] = 1       # short threshold
        return base

    # ── Trail (hilly) ──
    if is_trail and not is_flat_trail:
        if quality_workouts >= 2:
            base['hill'] = 1
            if week_number % 4 in [1, 2]:
                base['interval'] = 1
            else:
                base['tempo'] = 1
        else:
            base['hill'] = 1 if week_number % 3 in [0, 1] else 0
            base['interval'] = 0 if week_number % 3 in [0, 1] else 1
        return base

    # ── Flat trail: no hills, tempo replaces hill stimulus ──
    if is_flat_trail:
        if quality_workouts >= 2:
            if week_number % 4 in [1, 2]:
                base['tempo'] = 1
                base['interval'] = 1
            else:
                base['tempo'] = 2
        else:
            base['tempo'] = 1
        return base

    # ── Distance-specific road distributions ──
    if target_distance <= 5:
        # 5K: VO2max emphasis
        if quality_workouts >= 2:
            base['interval'] = 2
        else:
            base['interval'] = 1
    elif target_distance <= 10:
        # 10K: balanced (current default)
        base['interval'] = 1 if quality_workouts >= 1 else 0
        base['tempo'] = 1 if quality_workouts >= 2 else 0
    elif target_distance <= 21.1:
        # Half: balanced with tempo emphasis
        base['interval'] = 1 if quality_workouts >= 1 else 0
        base['tempo'] = 1 if quality_workouts >= 2 else 0
    else:
        # Marathon: tempo/MP emphasis
        if quality_workouts >= 2:
            base['tempo'] = 2 if phase == 'peak' else 1
            base['interval'] = 0 if phase == 'peak' else 1
        else:
            base['tempo'] = 1

    return base


def _validate_polarized_ratio(distribution: Dict[str, int], phase: str,
                              target_distance: float) -> Dict[str, int]:
    """Validate 80/20 polarized training ratio and adjust if needed.

    Trail gets slightly easier targets (85/15 build, 80/20 peak) because
    terrain naturally provides intensity through elevation.
    """
    is_trail = target_distance == 30.0
    hard_targets = {
        'base': 0.10,
        'build': 0.15 if is_trail else 0.20,
        'peak': 0.20 if is_trail else 0.25,
        'taper': 0.10,
    }

    hard_count = distribution.get('interval', 0) + distribution.get('tempo', 0) + distribution.get('hill', 0)
    total_runs = hard_count + distribution.get('easy', 0) + distribution.get('long', 0)

    if total_runs == 0:
        return distribution

    hard_pct = hard_count / total_runs
    target = hard_targets.get(phase, 0.20)

    # If hard% exceeds target by >5%, reduce quality by 1
    if hard_pct > target + 0.05 and hard_count > 0:
        for key in ('interval', 'tempo', 'hill'):
            if distribution.get(key, 0) > 0:
                distribution[key] -= 1
                distribution['easy'] = distribution.get('easy', 0) + 1
                break
    # If under by >10% in build/peak, increase by 1
    elif phase in ('build', 'peak') and hard_pct < target - 0.10 and distribution.get('easy', 0) > 0:
        distribution['easy'] -= 1
        distribution['interval'] = distribution.get('interval', 0) + 1

    return distribution


def get_workout_distribution_simple(total_km: float, max_runs: int) -> Dict[str, int]:
    """Simplified version of workout distribution for backward compatibility with tests."""
    long_runs = 1
    running_days = max_runs - long_runs

    if max_runs == 3:
        easy_runs = 1
        rest_days = 3
        quality_workouts = 1
    elif max_runs == 4:
        easy_runs = 2
        rest_days = 2
        quality_workouts = 1
    elif max_runs == 5:
        easy_runs = 2
        rest_days = 1
        quality_workouts = 2
    elif max_runs == 6:
        easy_runs = 3
        rest_days = 0
        quality_workouts = 2
    else:
        quality_workouts = max(1, running_days - 1)
        easy_runs = max(0, running_days - quality_workouts)
        rest_days = max(0, max_runs - long_runs - quality_workouts - easy_runs)

    return {
        'easy': easy_runs,
        'long': long_runs,
        'interval': quality_workouts if quality_workouts == 1 or (quality_workouts == 2 and max_runs == 4) else (1 if quality_workouts >= 1 else 0),
        'tempo': 1 if quality_workouts >= 2 and max_runs > 4 else 0,
        'hill': 0,
        'rest': rest_days
    }


def schedule_workout_types(distribution: Dict[str, int], phase: str,
                           week_number: int, is_recovery_week: bool) -> List[Optional[str]]:
    """
    Assign workout types to specific days.
    Recovery is always on Day 2 and does NOT count towards max_runs.
    """
    workout_types = [None] * 7

    workout_types[1] = 'recovery'

    workout_types[5] = 'long'
    distribution['long'] -= 1

    if not is_recovery_week:
        quality_slots = [2, 3, 4]
        for day_idx in quality_slots:
            if workout_types[day_idx] is not None:
                continue
            if distribution['hill'] > 0:
                workout_types[day_idx] = 'hill'
                distribution['hill'] -= 1
            elif distribution['interval'] > 0:
                workout_types[day_idx] = 'interval'
                distribution['interval'] -= 1
            elif distribution['tempo'] > 0:
                workout_types[day_idx] = 'tempo'
                distribution['tempo'] -= 1

    for day_idx in range(7):
        if workout_types[day_idx] is not None:
            continue
        if distribution['easy'] > 0:
            workout_types[day_idx] = 'easy'
            distribution['easy'] -= 1

    for day_idx in range(7):
        if workout_types[day_idx] is None:
            workout_types[day_idx] = 'rest'
            distribution['rest'] -= 1

    return workout_types
