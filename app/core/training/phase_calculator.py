"""Phase calculation logic for training plans.

Handles phase distribution (base/build/peak/taper), distance categorization,
and recovery week determination.
"""

from typing import Dict, Optional

from app.exceptions import InsufficientTimeException


MIN_WEEKS_FOR_PHASES = 6


# Phase-specific distance distribution percentages by race category.
# Each dict maps workout types to their share of weekly distance.
PHASE_DISTRIBUTIONS = {
    'base': {
        # Base now includes 1 light quality session (5% allocation):
        # 5K/10K: strides/interval; Half/Marathon: short threshold; Trail: easy hills
        '5K':       {'long': 0.35, 'tempo': 0.0,  'interval': 0.05, 'hill': 0.0,  'easy': 0.60},
        '10K':      {'long': 0.40, 'tempo': 0.0,  'interval': 0.05, 'hill': 0.0,  'easy': 0.55},
        'Half':     {'long': 0.45, 'tempo': 0.05, 'interval': 0.0,  'hill': 0.0,  'easy': 0.50},
        'Trail':    {'long': 0.45, 'tempo': 0.0,  'interval': 0.0,  'hill': 0.05, 'easy': 0.50},
        'FlatTrail': {'long': 0.45, 'tempo': 0.05, 'interval': 0.0,  'hill': 0.0,  'easy': 0.50},
        'Marathon': {'long': 0.45, 'tempo': 0.05, 'interval': 0.0,  'hill': 0.0,  'easy': 0.50},
    },
    'build': {
        '5K':       {'long': 0.35, 'tempo': 0.12, 'interval': 0.10, 'hill': 0.05, 'easy': 0.38},
        '10K':      {'long': 0.40, 'tempo': 0.12, 'interval': 0.10, 'hill': 0.05, 'easy': 0.33},
        'Half':     {'long': 0.45, 'tempo': 0.10, 'interval': 0.08, 'hill': 0.04, 'easy': 0.33},
        'Trail':    {'long': 0.45, 'tempo': 0.06, 'interval': 0.06, 'hill': 0.08, 'easy': 0.35},
        'FlatTrail': {'long': 0.45, 'tempo': 0.14, 'interval': 0.06, 'hill': 0.0,  'easy': 0.35},
        'Marathon': {'long': 0.45, 'tempo': 0.10, 'interval': 0.08, 'hill': 0.04, 'easy': 0.33},
    },
    'peak': {
        '5K':       {'long': 0.33, 'tempo': 0.12, 'interval': 0.10, 'hill': 0.05, 'easy': 0.40},
        '10K':      {'long': 0.38, 'tempo': 0.12, 'interval': 0.10, 'hill': 0.05, 'easy': 0.35},
        'Half':     {'long': 0.43, 'tempo': 0.10, 'interval': 0.08, 'hill': 0.04, 'easy': 0.35},
        'Trail':    {'long': 0.43, 'tempo': 0.06, 'interval': 0.06, 'hill': 0.08, 'easy': 0.37},
        'FlatTrail': {'long': 0.43, 'tempo': 0.14, 'interval': 0.06, 'hill': 0.0,  'easy': 0.37},
        'Marathon': {'long': 0.43, 'tempo': 0.10, 'interval': 0.08, 'hill': 0.04, 'easy': 0.35},
    },
    'taper': {
        '5K':       {'long': 0.30, 'tempo': 0.12, 'interval': 0.0, 'hill': 0.0,  'easy': 0.58},
        '10K':      {'long': 0.35, 'tempo': 0.12, 'interval': 0.0, 'hill': 0.0,  'easy': 0.53},
        'Half':     {'long': 0.40, 'tempo': 0.10, 'interval': 0.0, 'hill': 0.0,  'easy': 0.50},
        'Trail':    {'long': 0.40, 'tempo': 0.06, 'interval': 0.0, 'hill': 0.04, 'easy': 0.50},
        'FlatTrail': {'long': 0.40, 'tempo': 0.10, 'interval': 0.0, 'hill': 0.0,  'easy': 0.50},
        'Marathon': {'long': 0.40, 'tempo': 0.10, 'interval': 0.0, 'hill': 0.0,  'easy': 0.50},
    },
}


def get_distance_category(target_distance: float, terrain: Optional[str] = None) -> str:
    """Map target distance to a category key.

    Args:
        target_distance: Race distance in km
        terrain: Optional terrain access ('flat' for no-hills trail plans)
    """
    if target_distance <= 5:
        return '5K'
    elif target_distance <= 10:
        return '10K'
    elif target_distance <= 21.1:
        return 'Half'
    elif target_distance <= 30.0:
        if terrain == 'flat':
            return 'FlatTrail'
        return 'Trail'
    else:
        return 'Marathon'


def calculate_phases(weeks: int, target_distance: float = 10.0) -> Dict[str, int]:
    """
    Calculate distance-aware phase distribution.

    Marathon/half marathon plans get longer builds and tapers.
    5K plans get more sharpening (peak) and shorter tapers.

    Args:
        weeks: Total training plan duration
        target_distance: Race distance in km (affects phase proportions)

    Returns:
        Dict with phase durations: {'base': int, 'build': int, 'peak': int, 'taper': int}
    """
    if weeks < MIN_WEEKS_FOR_PHASES:
        raise InsufficientTimeException(
            f"Minimum {MIN_WEEKS_FOR_PHASES} weeks required for structured periodization.",
            suggestion=f"Extend your plan to at least {MIN_WEEKS_FOR_PHASES} weeks for a safe base/build/peak/taper structure.",
        )

    category = get_distance_category(target_distance)

    # Distance-specific ideal proportions: (base%, build%, peak%, taper_weeks)
    # Taper is prescribed as a fixed week count (not a %), then remaining weeks
    # are split among base/build/peak proportionally.
    phase_profiles = {
        '5K':       {'base_pct': 0.35, 'build_pct': 0.30, 'peak_pct': 0.20, 'taper': 2},
        '10K':      {'base_pct': 0.35, 'build_pct': 0.30, 'peak_pct': 0.15, 'taper': 2},
        'Half':     {'base_pct': 0.35, 'build_pct': 0.35, 'peak_pct': 0.15, 'taper': 2},
        'Trail':    {'base_pct': 0.35, 'build_pct': 0.35, 'peak_pct': 0.15, 'taper': 2},
        'Marathon': {'base_pct': 0.30, 'build_pct': 0.35, 'peak_pct': 0.15, 'taper': 3},
    }

    profile = phase_profiles[category]

    # Taper is prescribed by distance (marathon = 3 weeks, 5K = 1 week)
    taper = min(profile['taper'], max(1, weeks // 4))

    # Distribute remaining weeks among base/build/peak
    remaining = weeks - taper
    total_pct = profile['base_pct'] + profile['build_pct'] + profile['peak_pct']
    base = max(2, round(remaining * profile['base_pct'] / total_pct))
    build = max(2, round(remaining * profile['build_pct'] / total_pct))
    peak = max(1, remaining - base - build)

    # Safety: if rounding pushed us over, trim from the largest non-taper phase
    # but never let any phase drop below its floor
    while base + build + peak + taper > weeks:
        if base >= build and base >= peak and base > 2:
            base -= 1
        elif build >= peak and build > 2:
            build -= 1
        elif peak > 1:
            peak -= 1
        else:
            # All at minimums — trim from the largest anyway
            if base >= build and base >= peak:
                base -= 1
            elif build >= peak:
                build -= 1
            else:
                peak -= 1

    # Safety: if rounding left us short, add to build
    while base + build + peak + taper < weeks:
        build += 1

    return {'base': base, 'build': build, 'peak': peak, 'taper': taper}


def get_phase(week_number: int, phases: Dict[str, int]) -> str:
    """
    Determine which phase a given week belongs to.

    Returns: 'base', 'build', 'peak', or 'taper'
    """
    if week_number <= phases['base']:
        return 'base'
    elif week_number <= phases['base'] + phases['build']:
        return 'build'
    elif week_number <= phases['base'] + phases['build'] + phases['peak']:
        return 'peak'
    else:
        return 'taper'


def is_recovery_week(week_number: int, phase: str, phases: Optional[Dict[str, int]] = None) -> bool:
    """
    Determine if a week is a recovery week.

    Every 4th week in base and build phases is a recovery week,
    but only if the phase is long enough (>=4 weeks) to justify it.
    Peak phases of 4+ weeks get a recovery week in the 3rd week to
    consolidate adaptations before taper. No recovery weeks in taper.
    """
    if phase == 'taper':
        return False
    if phase == 'peak':
        if not phases or phases.get('peak', 0) < 4:
            return False
        # 3rd week of a 4+ week peak is recovery
        peak_start = phases['base'] + phases['build']
        week_in_peak = week_number - peak_start
        return week_in_peak == 3
    if phases:
        phase_length = phases.get(phase, 0)
        if phase_length < 4:
            return False
        phase_start_week = 1 if phase == 'base' else phases['base'] + 1
        week_in_phase = week_number - phase_start_week
        return week_in_phase > 0 and week_in_phase % 4 == 0
    return week_number % 4 == 0
