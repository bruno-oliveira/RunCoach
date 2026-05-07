"""Long run distance and quality workout distance calculations.

Handles long run ratio progression, distance caps, and phase-based
quality workout distance allocation.
"""

from typing import Dict, Optional

from app.core.training.training_constants import (
    get_hard_ceiling,
    calculate_week_in_phase,
)
from app.core.training.phase_calculator import (
    PHASE_DISTRIBUTIONS,
    calculate_phases,
    get_distance_category,
)
from app.core.training.trail_profile import TrailProfile


_ROAD_LONG_RUN_RATIOS = {
    '5K': {
        'base': (0.25, 0.30),
        'build': (0.28, 0.32),
        'peak': (0.30, 0.35),
        'taper': (0.25, 0.30),
    },
    '10K': {
        'base': (0.28, 0.33),
        'build': (0.31, 0.36),
        'peak': (0.35, 0.40),
        'taper': (0.28, 0.33),
    },
    'Half': {
        'base': (0.30, 0.35),
        'build': (0.33, 0.38),
        'peak': (0.40, 0.48),
        'taper': (0.30, 0.35),
    },
    'Marathon': {
        'base': (0.32, 0.38),
        'build': (0.35, 0.42),
        'peak': (0.42, 0.50),
        'taper': (0.32, 0.38),
    },
}

# Trail long-run ratios scale with bracket. Ultras and long-ultras pull more
# of the weekly volume into a single weekend session (or back-to-back) — but
# the absolute long-run cap (see ``_get_long_run_cap``) keeps them sane.
_TRAIL_LONG_RUN_RATIOS = {
    'short': {
        'base':  (0.30, 0.35),
        'build': (0.35, 0.40),
        'peak':  (0.40, 0.45),
        'taper': (0.30, 0.35),
    },
    'standard': {
        'base':  (0.30, 0.35),
        'build': (0.40, 0.45),
        'peak':  (0.45, 0.50),
        'taper': (0.35, 0.40),
    },
    'ultra': {
        'base':  (0.32, 0.38),
        'build': (0.42, 0.50),
        'peak':  (0.45, 0.55),
        'taper': (0.35, 0.40),
    },
    'long_ultra': {
        'base':  (0.35, 0.40),
        'build': (0.45, 0.52),
        'peak':  (0.45, 0.55),
        'taper': (0.35, 0.40),
    },
}


def get_long_run_ratio_range(
    phase: str,
    target_distance: float,
    weeks: int,
    trail_profile: Optional[TrailProfile] = None,
) -> tuple[float, float]:
    """
    Get the long run ratio range (min, max) for a phase.

    Args:
        phase: Training phase (base, build, peak, taper).
        target_distance: Race distance in km.
        weeks: Total weeks in plan (for adjusting ratios in short plans).
        trail_profile: Optional trail profile — its bracket selects the
            trail ratio table (ultras pull a higher long-run share).
    """
    if trail_profile is not None:
        min_ratio, max_ratio = _TRAIL_LONG_RUN_RATIOS[trail_profile.bracket][phase]
    else:
        category = get_distance_category(target_distance)
        if category in _ROAD_LONG_RUN_RATIOS:
            min_ratio, max_ratio = _ROAD_LONG_RUN_RATIOS[category][phase]
        else:
            # Legacy 30 km without an explicit trail_profile → standard bracket.
            min_ratio, max_ratio = _TRAIL_LONG_RUN_RATIOS['standard'][phase]

    if weeks <= 10:
        adjustment = 0.03
        min_ratio = max(0.25, min_ratio - adjustment)
        max_ratio = max(min_ratio + 0.02, max_ratio - adjustment)

    return (min_ratio, max_ratio)


def calculate_long_run_ratio(phase: str, week_number: int, phases: Dict[str, int],
                             target_distance: float, is_recovery_week: bool,
                             total_weeks: int,
                             trail_profile: Optional[TrailProfile] = None) -> float:
    """
    Calculate long run ratio with progression within phase.

    Args:
        phase: Current training phase
        week_number: Week number in plan (1-indexed)
        phases: Dictionary with phase durations
        target_distance: Race distance in km
        is_recovery_week: Whether this is a recovery week
        total_weeks: Total weeks in plan
        trail_profile: Optional trail profile — bracket-aware ratios.

    Returns:
        Long run ratio as a decimal (e.g., 0.35 for 35%)
    """
    min_ratio, max_ratio = get_long_run_ratio_range(
        phase, target_distance, total_weeks, trail_profile=trail_profile,
    )

    week_in_phase = calculate_week_in_phase(week_number, phase, phases)
    total_in_phase = phases.get(phase, phases.get('taper', 1))

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


def _trail_long_run_cap(profile: TrailProfile, experience_level: str) -> float:
    """Long-run cap for a trail profile.

    For ultras the single long run plateaus around 35 km — additional
    long-day volume comes from back-to-back doubles in build/peak weeks
    (added in the workout-builder pass), not a single 50 km grind.
    """
    bracket_caps = {
        'short':      {'beginner': 14.0, 'intermediate': 16.0, 'advanced': 18.0},
        'standard':   {'beginner': 24.0, 'intermediate': 25.5, 'advanced': 27.0},
        'ultra':      {'beginner': 28.0, 'intermediate': 30.0, 'advanced': 32.0},
        'long_ultra': {'beginner': 30.0, 'intermediate': 32.0, 'advanced': 35.0},
    }
    tier = bracket_caps[profile.bracket]
    return tier.get(experience_level, tier['intermediate'])


def _get_long_run_cap(target_distance: float, experience_level: str = 'intermediate',
                      weekly_km: float = 0,
                      trail_profile: Optional[TrailProfile] = None) -> float:
    """Experience-tiered long run distance caps, with volume-aware scaling.

    When weekly volume is high enough that the static cap would prevent
    filling target volume, the cap scales up to a hard ceiling. Trail /
    ultra plans use a bracket-aware cap that does not blow past 35 km even
    for 100-mile prep.
    """
    if trail_profile is not None:
        base_cap = _trail_long_run_cap(trail_profile, experience_level)
        if weekly_km <= 0:
            return base_cap
        # Allow a 30% slice of weekly volume but never above the bracket cap.
        volume_ratio = weekly_km * 0.30
        return min(round(volume_ratio, 1), base_cap) if volume_ratio > base_cap else base_cap

    base_caps = {
        5.0:  {'beginner': 7.0,  'intermediate': 8.0,  'advanced': 10.0},
        10.0: {'beginner': 12.0, 'intermediate': 15.0, 'advanced': 16.0},
        21.1: {'beginner': 17.0, 'intermediate': 18.0, 'advanced': 19.0},
        30.0: {'beginner': 24.0, 'intermediate': 25.5, 'advanced': 27.0},
        42.2: {'beginner': 32.0, 'intermediate': 34.0, 'advanced': 36.0},
    }
    tier = base_caps.get(target_distance)
    if tier:
        base_cap = tier.get(experience_level, tier['intermediate'])
    else:
        base_cap = target_distance * 0.77

    if weekly_km <= 0:
        return base_cap

    ceiling = get_hard_ceiling(target_distance)
    volume_ratio = weekly_km * 0.30
    if volume_ratio > base_cap:
        return min(round(volume_ratio, 1), ceiling)
    return base_cap


def calculate_long_run_distance(total_km: float, target_distance: float,
                                weeks: int = 12, week_number: int = 1,
                                phase: str = 'build',
                                is_recovery_week: bool = False,
                                experience_level: str = 'intermediate',
                                profile: Optional[dict] = None,
                                trail_profile: Optional[TrailProfile] = None) -> float:
    """
    Calculate long run distance with proper progression and phase-specific percentage.
    Long run percentage increases with race distance for appropriate endurance building.

    When a RunnerProfile is provided, the runner's historical longest_run_km is used
    only as a gentle nudge in week 1 — if the calculated long run would be more than
    50% above their historical max, it's pulled back slightly to avoid a jarring first
    session. After week 1, normal progression takes over and the runner builds fitness
    freely through the plan's 10%-rule ramp.
    """
    phases = calculate_phases(weeks, target_distance, trail_profile=trail_profile)
    long_run_ratio = calculate_long_run_ratio(
        phase, week_number, phases, target_distance, is_recovery_week, weeks,
        trail_profile=trail_profile,
    )

    long_run_base = total_km * long_run_ratio

    long_run_cap = _get_long_run_cap(
        target_distance, experience_level, weekly_km=total_km,
        trail_profile=trail_profile,
    )

    long_run_base = min(long_run_base, long_run_cap)

    # Profile-aware: gentle week-1 nudge only (not a hard cap)
    if profile and week_number == 1:
        longest_run = profile.get("longest_run_km", 0)
        if longest_run > 0:
            # If the planned long run is >50% above historical max, pull it back
            # to longest_run * 1.30 as a gentle starting point
            gentle_start = longest_run * 1.30
            if long_run_base > gentle_start * 1.50:
                long_run_base = gentle_start

    # Floor: at least 25% of target race distance, but never more than total
    # weekly volume (a single run cannot exceed the week's total mileage)
    # and never more than 50% of total (prevents long-run dominance in low-
    # volume taper weeks where the distance floor would otherwise dominate).
    #
    # Trail/ultra plans cap the floor at the bracket-specific long-run cap —
    # otherwise 25% of a 100-mile target (≈ 41 km) would force a single
    # long run beyond what the bracket prescribes (back-to-back doubles and
    # time-on-feet sessions take the place of one ever-bigger run).
    min_long_run = min(target_distance * 0.25, total_km, total_km * 0.50)
    if trail_profile is not None:
        min_long_run = min(min_long_run, long_run_cap)

    if is_recovery_week:
        min_long_run = min(target_distance * 0.20, total_km)
        min_long_run = min(min_long_run, total_km * 0.30)
        if trail_profile is not None:
            min_long_run = min(min_long_run, long_run_cap)

    return round(max(min_long_run, long_run_base), 1)


def get_phase_distribution(phase: str, target_distance: float = 10.0,
                           terrain: str | None = None,
                           trail_profile: Optional[TrailProfile] = None) -> Dict[str, float]:
    """
    Get distance distribution percentages for each phase.

    Returns percentages that sum to 100% across all workout types.
    Long run percentages increase with race distance for proper endurance building.

    Args:
        phase: Current training phase (base, build, peak, taper)
        target_distance: Race distance in km (adjusts long run percentage)
        terrain: Legacy terrain string ('flat' selects flat-trail bucket).
        trail_profile: Preferred input for trail/ultra plans.

    Returns:
        Dict with percentage breakdown of workout types
    """
    dist_key = get_distance_category(
        target_distance, terrain=terrain, trail_profile=trail_profile,
    )
    return PHASE_DISTRIBUTIONS.get(phase, PHASE_DISTRIBUTIONS['taper'])[dist_key]


def calculate_quality_distances(total_km: float, phase: str,
                                distribution: Dict[str, int], is_recovery_week: bool,
                                long_run_distance: float = 0,
                                target_distance: float = 10.0,
                                terrain: str | None = None,
                                trail_profile: Optional[TrailProfile] = None) -> Dict[str, float]:
    """Calculate distances for quality workouts based on phase distribution."""
    quality_distances = {}

    if is_recovery_week:
        return {'tempo': 0, 'interval': 0, 'hill': 0}

    phase_dist = get_phase_distribution(
        phase, target_distance, terrain=terrain, trail_profile=trail_profile,
    )

    remaining_km = total_km - long_run_distance

    non_long_pct = max(0.01, 1 - phase_dist['long'])

    for qtype in ('tempo', 'interval', 'hill'):
        if distribution.get(qtype, 0) > 0:
            pct = phase_dist.get(qtype, 0)
            dist = remaining_km * (pct / non_long_pct) if pct > 0 else 0
            quality_distances[qtype] = round(max(dist, 1.0), 1)

    return quality_distances
