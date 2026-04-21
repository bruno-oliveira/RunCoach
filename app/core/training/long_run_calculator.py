"""Long run distance and quality workout distance calculations.

Handles long run ratio progression, distance caps, and phase-based
quality workout distance allocation.
"""

from typing import Dict

from app.core.training.phase_calculator import (
    PHASE_DISTRIBUTIONS,
    calculate_phases,
    get_distance_category,
)


def get_long_run_ratio_range(phase: str, target_distance: float, weeks: int) -> tuple[float, float]:
    """
    Get the long run ratio range (min, max) for a phase.

    Args:
        phase: Training phase (base, build, peak, taper)
        target_distance: Race distance in km
        weeks: Total weeks in plan (for adjusting ratios in short plans)

    Returns:
        Tuple of (min_ratio, max_ratio)
    """
    category = get_distance_category(target_distance)

    ratio_ranges = {
        '5K': {
            'base': (0.25, 0.30),
            'build': (0.28, 0.32),
            'peak': (0.30, 0.35),
            'taper': (0.25, 0.30)
        },
        '10K': {
            'base': (0.28, 0.33),
            'build': (0.31, 0.36),
            'peak': (0.35, 0.40),
            'taper': (0.28, 0.33)
        },
        'Half': {
            'base': (0.30, 0.35),
            'build': (0.33, 0.38),
            'peak': (0.38, 0.43),
            'taper': (0.30, 0.35)
        },
        'Trail': {
            'base': (0.30, 0.35),
            'build': (0.40, 0.45),
            'peak': (0.45, 0.50),
            'taper': (0.35, 0.40)
        },
        'Marathon': {
            'base': (0.32, 0.38),
            'build': (0.35, 0.42),
            'peak': (0.40, 0.45),
            'taper': (0.32, 0.38)
        }
    }

    min_ratio, max_ratio = ratio_ranges[category][phase]

    if weeks <= 10:
        adjustment = 0.03
        min_ratio = max(0.25, min_ratio - adjustment)
        max_ratio = max(min_ratio + 0.02, max_ratio - adjustment)

    return (min_ratio, max_ratio)


def calculate_long_run_ratio(phase: str, week_number: int, phases: Dict[str, int],
                             target_distance: float, is_recovery_week: bool,
                             total_weeks: int) -> float:
    """
    Calculate long run ratio with progression within phase.

    Args:
        phase: Current training phase
        week_number: Week number in plan (1-indexed)
        phases: Dictionary with phase durations
        target_distance: Race distance in km
        is_recovery_week: Whether this is a recovery week
        total_weeks: Total weeks in plan

    Returns:
        Long run ratio as a decimal (e.g., 0.35 for 35%)
    """
    min_ratio, max_ratio = get_long_run_ratio_range(phase, target_distance, total_weeks)

    if phase == 'base':
        week_in_phase = week_number - 1
        total_in_phase = phases['base']
    elif phase == 'build':
        week_in_phase = week_number - phases['base'] - 1
        total_in_phase = phases['build']
    elif phase == 'peak':
        week_in_phase = week_number - phases['base'] - phases['build'] - 1
        total_in_phase = phases['peak']
    else:
        week_in_phase = week_number - phases['base'] - phases['build'] - phases['peak'] - 1
        total_in_phase = phases['taper']

    if total_in_phase > 1:
        progression = week_in_phase / (total_in_phase - 1)
    else:
        progression = 0.0

    ratio = min_ratio + (max_ratio - min_ratio) * progression

    if is_recovery_week:
        ratio = ratio * 0.85  # Fixed 15% reduction for deterministic recovery
        recovery_min = max(0.20, min_ratio - 0.05)
        ratio = max(recovery_min, ratio)
    else:
        ratio = max(0.25, ratio)

    return round(ratio, 3)


def _get_long_run_cap(target_distance: float, experience_level: str = 'intermediate',
                      weekly_km: float = 0) -> float:
    """Experience-tiered long run distance caps, with volume-aware scaling.

    When weekly volume is high enough that the static cap would prevent
    filling target volume, the cap scales up to a hard ceiling.
    """
    base_caps = {
        5.0:  {'beginner': 7.0,  'intermediate': 8.0,  'advanced': 10.0},
        10.0: {'beginner': 12.0, 'intermediate': 15.0, 'advanced': 16.0},
        21.1: {'beginner': 18.0, 'intermediate': 20.0, 'advanced': 22.0},
        30.0: {'beginner': 20.0, 'intermediate': 24.0, 'advanced': 28.0},
        42.2: {'beginner': 28.0, 'intermediate': 32.0, 'advanced': 35.0},
    }
    hard_ceilings = {5.0: 14.0, 10.0: 22.0, 21.1: 28.0, 30.0: 32.0, 42.2: 38.0}

    tier = base_caps.get(target_distance)
    if tier:
        base_cap = tier.get(experience_level, tier['intermediate'])
    else:
        base_cap = target_distance * 0.77

    if weekly_km <= 0:
        return base_cap

    ceiling = hard_ceilings.get(target_distance, target_distance * 0.9)
    volume_ratio = weekly_km * 0.30
    if volume_ratio > base_cap:
        return min(round(volume_ratio, 1), ceiling)
    return base_cap


def calculate_long_run_distance(total_km: float, target_distance: float,
                                weeks: int = 12, week_number: int = 1,
                                phase: str = 'build',
                                is_recovery_week: bool = False,
                                experience_level: str = 'intermediate') -> float:
    """
    Calculate long run distance with proper progression and phase-specific percentage.
    Long run percentage increases with race distance for appropriate endurance building.
    """
    phases = calculate_phases(weeks, target_distance)
    long_run_ratio = calculate_long_run_ratio(
        phase, week_number, phases, target_distance, is_recovery_week, weeks
    )

    long_run_base = total_km * long_run_ratio

    long_run_cap = _get_long_run_cap(target_distance, experience_level, weekly_km=total_km)

    long_run_base = min(long_run_base, long_run_cap)

    # Floor: at least 25% of target race distance, but never more than total
    # weekly volume (a single run cannot exceed the week's total mileage).
    min_long_run = min(target_distance * 0.25, total_km)

    if is_recovery_week:
        min_long_run = min(target_distance * 0.20, total_km)

    return round(max(min_long_run, long_run_base), 1)


def get_phase_distribution(phase: str, target_distance: float = 10.0) -> Dict[str, float]:
    """
    Get distance distribution percentages for each phase.

    Returns percentages that sum to 100% across all workout types.
    Long run percentages increase with race distance for proper endurance building.

    Args:
        phase: Current training phase (base, build, peak, taper)
        target_distance: Race distance in km (adjusts long run percentage)

    Returns:
        Dict with percentage breakdown of workout types
    """
    dist_key = get_distance_category(target_distance)
    return PHASE_DISTRIBUTIONS.get(phase, PHASE_DISTRIBUTIONS['taper'])[dist_key]


def calculate_quality_distances(total_km: float, phase: str,
                                distribution: Dict[str, int], is_recovery_week: bool,
                                long_run_distance: float = 0,
                                target_distance: float = 10.0) -> Dict[str, float]:
    """Calculate distances for quality workouts based on phase distribution."""
    quality_distances = {}

    if is_recovery_week:
        return {'tempo': 0, 'interval': 0, 'hill': 0}

    phase_dist = get_phase_distribution(phase, target_distance)

    remaining_km = total_km - long_run_distance

    non_long_pct = max(0.01, 1 - phase_dist['long'])

    if distribution['tempo'] > 0:
        quality_distances['tempo'] = round(remaining_km * (phase_dist['tempo'] / non_long_pct), 1)
    if distribution['interval'] > 0:
        quality_distances['interval'] = round(remaining_km * (phase_dist['interval'] / non_long_pct), 1)
    if distribution['hill'] > 0:
        quality_distances['hill'] = round(remaining_km * (phase_dist['hill'] / non_long_pct), 1)

    return quality_distances
