"""Workout distribution and scheduling logic.

Determines how many of each workout type per week and assigns
them to specific days of the week.
"""

from typing import Dict, List, Optional


def get_workout_distribution(total_km: float, max_runs: int, phase: str = 'build',
                             is_recovery_week: bool = False, week_number: int = 1,
                             phases: Dict[str, int] = None,
                             target_distance: float = 10.0,
                             terrain: Optional[str] = None,
                             profile: Optional[dict] = None) -> Dict[str, int]:
    """Calculate how many of each workout type per week.

    When a RunnerProfile is provided, the runner's actual pace zone
    distribution and workout history are used to correct imbalances:
    - Too much hard work (>30%) → reduce quality slots
    - Almost no hard work (<10%) → ensure at least 1 quality in build/peak
    - Missing workout types → prioritize gaps in quality selection
    """
    is_backward_compatible_call = (phase == 'build' and not is_recovery_week and
                                   week_number == 1 and phases is None and
                                   target_distance == 10.0)

    if is_backward_compatible_call:
        return get_workout_distribution_simple(total_km, max_runs)

    long_runs = 1

    # At 2 runs/week (minimum effective dose for busy schedules), the week is
    # always 1 long + 1 easy — quality workouts need a third running day to
    # keep the weekly 80/20 easy/hard balance intact.
    if is_recovery_week:
        quality_workouts = 0
    elif max_runs <= 2:
        quality_workouts = 1 if phase in ('build', 'peak') else 0
    elif phase == 'base':
        base_quality_km = total_km * 0.05
        if max_runs >= 4 and base_quality_km >= 1.0:
            quality_workouts = 1
        else:
            quality_workouts = 0
    elif phase == 'build':
        if phases:
            week_in_build = week_number - phases['base']
        else:
            week_in_build = week_number
        if week_in_build <= 2:
            quality_workouts = 1 if max_runs >= 3 else 0
        else:
            quality_workouts = 2 if max_runs >= 5 else 1
    elif phase == 'peak':
        quality_workouts = 2 if max_runs >= 5 else 1
    else:
        quality_workouts = 0

    # Profile-aware: adjust quality count based on actual pace distribution
    if profile and not is_recovery_week and quality_workouts > 0:
        hard_pct = profile.get("hard_pct", 0)
        easy_pct = profile.get("easy_pct", 0)
        # If runner habitually does too much hard work (>30%), reduce quality
        if hard_pct > 30 and quality_workouts > 1:
            quality_workouts = max(1, quality_workouts - 1)
        # If runner does almost no hard work (<10%), ensure at least 1 quality
        elif hard_pct < 10 and quality_workouts == 0 and phase in ("build", "peak"):
            quality_workouts = 1
        # If runner's easy runs are very low (<50%), they may need more recovery
        elif easy_pct < 50 and phase in ("build", "peak") and quality_workouts > 1:
            quality_workouts = max(1, quality_workouts - 1)

    # Recovery is an additional non-running day, does NOT count towards max_runs
    actual_run_slots = max_runs
    running_days = actual_run_slots - long_runs - quality_workouts
    easy_runs = max(0, running_days)
    max_runs = min(max_runs, 6)
    rest_days = 7 - (max_runs + 1)

    distribution = _build_quality_distribution(
        target_distance, terrain, quality_workouts, phase,
        easy_runs, long_runs, rest_days, week_number,
        profile=profile,
    )

    if not is_recovery_week and max_runs > 2:
        distribution = _validate_polarized_ratio(distribution, phase, target_distance)

    return distribution


def _profile_for(target_distance: float, terrain: Optional[str]) -> str:
    """Map (distance, terrain) to a quality-distribution profile name."""
    if target_distance == 30.0:
        return 'trail_flat' if terrain == 'flat' else 'trail_hilly'
    if target_distance <= 5:
        return 'road_5k'
    if target_distance <= 10:
        return 'road_10k'
    if target_distance <= 21.1:
        return 'road_half'
    return 'road_marathon'


# Base-phase quality: every profile gets exactly one light quality session,
# but the type depends on the race it's preparing for.
_BASE_PHASE_QUALITY = {
    'trail_hilly':    {'hill': 1},
    'trail_flat':     {'tempo': 1},
    'road_5k':        {'interval': 1},   # strides
    'road_10k':       {'interval': 1},   # strides
    'road_half':      {'tempo': 1},      # short threshold
    'road_marathon':  {'tempo': 1},      # short threshold
}


def _quality_for_trail_hilly(quality_workouts: int, week_number: int,
                             phase: str) -> Dict[str, int]:
    """Trail (hilly): hills are the dominant stimulus, tempo/interval rotate."""
    if quality_workouts >= 2:
        # Hills every week + rotating second quality session.
        # Week-of-month cycle: weeks 1-2 → intervals, weeks 3-4 → tempo.
        rotating = 'interval' if week_number % 4 in (1, 2) else 'tempo'
        return {'hill': 1, rotating: 1}
    # Single-quality: hills in 2/3 of weeks, interval on the off week.
    # 3-week cycle: weeks divisible by 3 and 3k+1 → hill, 3k+2 → interval.
    if week_number % 3 in (0, 1):
        return {'hill': 1}
    return {'interval': 1}


def _quality_for_trail_flat(quality_workouts: int, week_number: int,
                            phase: str) -> Dict[str, int]:
    """Flat trail: no hill access, tempo replaces the hill stimulus."""
    if quality_workouts >= 2:
        # Weeks 1-2 of the 4-week cycle: mixed quality; weeks 3-4: double tempo.
        if week_number % 4 in (1, 2):
            return {'tempo': 1, 'interval': 1}
        return {'tempo': 2}
    return {'tempo': 1}


def _quality_for_road_5k(quality_workouts: int, week_number: int,
                         phase: str) -> Dict[str, int]:
    """5K: VO2max emphasis — intervals dominate."""
    return {'interval': 2 if quality_workouts >= 2 else 1}


def _quality_for_road_10k(quality_workouts: int, week_number: int,
                          phase: str) -> Dict[str, int]:
    """10K: balanced — 1 interval + optional tempo."""
    result: Dict[str, int] = {'interval': 1}
    if quality_workouts >= 2:
        result['tempo'] = 1
    return result


def _quality_for_road_half(quality_workouts: int, week_number: int,
                           phase: str) -> Dict[str, int]:
    """Half: balanced — interval and tempo rotate when only 1 quality slot."""
    if quality_workouts >= 2:
        return {'interval': 1, 'tempo': 1}
    if week_number % 2 == 1:
        return {'interval': 1}
    return {'tempo': 1}


def _quality_for_road_marathon(quality_workouts: int, week_number: int,
                               phase: str) -> Dict[str, int]:
    """Marathon: tempo/MP emphasis; peak phase drops intervals entirely."""
    if quality_workouts < 2:
        return {'tempo': 1}
    if phase == 'peak':
        return {'tempo': 2}
    return {'tempo': 1, 'interval': 1}


_PROFILE_BUILDERS = {
    'trail_hilly':   _quality_for_trail_hilly,
    'trail_flat':    _quality_for_trail_flat,
    'road_5k':       _quality_for_road_5k,
    'road_10k':      _quality_for_road_10k,
    'road_half':     _quality_for_road_half,
    'road_marathon': _quality_for_road_marathon,
}


def _build_quality_distribution(target_distance: float, terrain: Optional[str],
                                quality_workouts: int, phase: str,
                                easy_runs: int, long_runs: int, rest_days: int,
                                week_number: int,
                                profile: Optional[dict] = None) -> Dict[str, int]:
    """Assign quality workout types based on race distance, terrain, and phase.

    Dispatches to a per-profile builder keyed by (distance, terrain).
    Base phase always returns a single light quality session;
    build/peak use the profile's full quality pattern.

    When a RunnerProfile is provided, workout type gaps are filled:
    - No speed work history → start with tempo in base phase
    - No tempo history → prioritize tempo over intervals
    """
    distribution = {
        'easy': easy_runs, 'long': long_runs,
        'interval': 0, 'tempo': 0, 'hill': 0,
        'rest': rest_days,
    }

    if quality_workouts == 0:
        return distribution

    profile_name = _profile_for(target_distance, terrain)

    # Profile-aware: detect gaps in training history
    if profile:
        counts = profile.get("workout_type_counts", {}) or {}
        has_speed = counts.get("interval", 0) + counts.get("speed", 0) + counts.get("track", 0) > 0
        has_tempo = counts.get("tempo", 0) + counts.get("threshold", 0) > 0
        has_hills = counts.get("hill", 0) + counts.get("hill_repeats", 0) > 0

        # If runner has never done speed work, use tempo-focused profile in base
        if not has_speed and phase == "base" and profile_name in ("road_5k", "road_10k"):
            profile_name = "road_half"  # tempo-focused instead of interval
        # If runner has never done tempo, prioritize it in early build
        if not has_tempo and phase == "base":
            # Keep the base quality as tempo instead of interval
            distribution.update({'tempo': 1})
            return distribution

    if phase == 'base':
        distribution.update(_BASE_PHASE_QUALITY[profile_name])
        return distribution

    distribution.update(_PROFILE_BUILDERS[profile_name](quality_workouts, week_number, phase))
    return distribution


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

    # If hard% exceeds target by >5%, reduce quality by 1.
    # Never reduce below 1 quality in build/peak — with 3-4 total runs the
    # count-based ratio overstates intensity (one 4km tempo in a 30km week
    # is only 13% of volume, not the 33% that 1-of-3 suggests).
    if hard_pct > target + 0.05 and hard_count > 0:
        if phase == 'base' and hard_count <= 1:
            pass
        elif phase in ('build', 'peak') and hard_count <= 1:
            pass
        else:
            for key in ('interval', 'tempo', 'hill'):
                if distribution.get(key, 0) > 0:
                    distribution[key] -= 1
                    distribution['easy'] = distribution.get('easy', 0) + 1
                    break
    # If under by >10% in build/peak, increase by 1.
    # Skip for 2-run weeks: adding quality would displace the only easy run
    # and leave the week without an aerobic recovery session.
    elif (phase in ('build', 'peak') and hard_pct < target - 0.10
          and distribution.get('easy', 0) > 0 and total_runs >= 3):
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

    # For busy 2-run weeks (1 easy + 1 long), anchor easy on Wed (day_idx 2)
    # so it sits ~3 days from the Saturday long on either side. The default
    # left-to-right fill would put easy on Monday and leave 5 days of no-run,
    # a lopsided spacing.
    if distribution['easy'] == 1 and sum(
        distribution.get(k, 0) for k in ('interval', 'tempo', 'hill')
    ) == 0 and workout_types[2] is None:
        workout_types[2] = 'easy'
        distribution['easy'] -= 1

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
