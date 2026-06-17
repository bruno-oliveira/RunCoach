"""Long run distance and quality workout distance calculations.

Handles long run ratio progression, distance caps, and phase-based
quality workout distance allocation.
"""

import math
from typing import Dict, Optional

from app.core.training.phase_calculator import (
    PHASE_DISTRIBUTIONS,
    calculate_phases,
    get_distance_category,
)
from app.core.training.trail_profile import TrailProfile
from app.core.training.training_constants import (
    calculate_week_in_phase,
    get_hard_ceiling,
)
from app.core.training.tuning import (
    FALLBACK_LONG_RUN_CAP_RATIO,
    LONG_RUN_GROWTH_ABS_KM,
    LONG_RUN_GROWTH_PCT,
    LONG_RUN_VOLUME_RATIO,
    LOW_FREQ_LONG_RUN_RATIO_FLOOR,
    ROAD_LONG_RUN_CAPS,
    TRAIL_LR_CAP_EXPERIENCE,
    TRAIL_LR_CAP_LOG_A,
    TRAIL_LR_CAP_LOG_B,
    TRAIL_LR_CAP_MAX_KM,
    TRAIL_LR_CAP_MIN_KM,
)
from app.core.training.tuning import ROAD_LONG_RUN_RATIOS as _ROAD_LONG_RUN_RATIOS
from app.core.training.tuning import TRAIL_LONG_RUN_RATIOS as _TRAIL_LONG_RUN_RATIOS
from app.core.training.tuning import (
    TRAIL_PEAK_RACE_FRACTION as _TRAIL_PEAK_RACE_FRACTION,
)
from app.core.training.tuning import (
    TRAIL_PEAK_RACE_FRACTION_FLAT as _TRAIL_PEAK_RACE_FRACTION_FLAT,
)

# Road long-run time ceiling: beyond ~3 hours the injury / recovery cost of a
# single run outweighs the aerobic benefit, so a slow runner shouldn't be
# handed a 3.5 h+ long run just because the % cap permits the distance. Trail /
# ultra is intentionally excluded — time-on-feet is the training goal there.
MAX_LONG_RUN_HOURS = 3.0


def get_trail_peak_race_fraction(
    trail_profile: TrailProfile,
    training_terrain: str | None = None,
) -> float:
    """Return the trail peak race-distance floor fraction for long runs."""
    if training_terrain == "flat":
        boosted = _TRAIL_PEAK_RACE_FRACTION_FLAT.get(trail_profile.bracket)
        if boosted is not None:
            return boosted
    return _TRAIL_PEAK_RACE_FRACTION[trail_profile.bracket]


# A plan whose realized peak long run is below this fraction of the
# race-appropriate target has too little runway (base × weeks) to build race
# specificity safely — surface a non-blocking warning rather than papering over
# it with a dangerous single-week jump.
LONG_RUN_ADEQUACY_THRESHOLD = 0.85


def recommended_peak_long_run(
    target_distance: float,
    experience_level: str = "intermediate",
    trail_profile: Optional[TrailProfile] = None,
    training_terrain: str | None = None,
) -> float:
    """The race-appropriate peak long run a well-resourced plan would reach.

    This is the *target* the long-run progression aims for given ample runway —
    a race-distance fraction (bounded by the bracket cap) for trail, and the
    experience-tiered cap for road. Comparing the plan's realized peak long run
    against this surfaces when the base + timeline left it short of race
    specificity (see ``assess_long_run_adequacy``).
    """
    if trail_profile is not None:
        frac = get_trail_peak_race_fraction(trail_profile, training_terrain)
        cap = _trail_long_run_cap(trail_profile, experience_level)
        return round(min(target_distance * frac, cap), 1)
    tier = ROAD_LONG_RUN_CAPS.get(target_distance)
    if tier:
        return float(tier.get(experience_level, tier["intermediate"]))
    return round(target_distance * FALLBACK_LONG_RUN_CAP_RATIO, 1)


def assess_long_run_adequacy(
    achieved_peak_long_run_km: float,
    target_distance: float,
    experience_level: str = "intermediate",
    trail_profile: Optional[TrailProfile] = None,
    training_terrain: str | None = None,
    weeks: Optional[int] = None,
) -> Optional[dict]:
    """Flag when a plan's peak long run falls short of race specificity.

    Returns ``None`` when the long run reaches a race-appropriate distance, or a
    structured warning when the base + timeline didn't allow a safe ramp to it.
    The long run is bounded by the week-over-week growth cap, so from a low base
    on a short timeline it *correctly* falls short rather than spiking — this
    surfaces that trade-off to the runner so they can add weeks or build a
    bigger base instead of being silently under-prepared.
    """
    if achieved_peak_long_run_km <= 0 or target_distance <= 0:
        return None
    recommended = recommended_peak_long_run(
        target_distance,
        experience_level,
        trail_profile=trail_profile,
        training_terrain=training_terrain,
    )
    if recommended <= 0:
        return None
    if achieved_peak_long_run_km >= recommended * LONG_RUN_ADEQUACY_THRESHOLD:
        return None

    achieved = round(achieved_peak_long_run_km, 1)
    recommended = round(recommended, 1)
    pct = round(achieved / recommended * 100)
    race_label = (
        f"{target_distance:g} km trail race"
        if trail_profile is not None
        else f"{target_distance:g} km race"
    )
    message = (
        f"Your longest run peaks at {achieved:g} km — about {pct}% of the "
        f"~{recommended:g} km we'd aim for before a {race_label}. With this "
        "starting base and number of weeks there isn't enough runway to build "
        "the long run that far without ramping it dangerously fast, so the plan "
        "holds it to a safe progression instead."
    )
    suggestion = (
        "Add 2-4 weeks to the plan, or build a higher weekly base before "
        "starting, to reach a more race-specific long run safely."
    )
    return {
        "achieved_km": achieved,
        "recommended_km": recommended,
        "pct_of_recommended": pct,
        "race_distance_km": target_distance,
        "weeks": weeks,
        "message": message,
        "suggestion": suggestion,
    }


def get_weekly_long_run_ratio_cap(
    phase: str,
    trail_profile: Optional[TrailProfile] = None,
    training_terrain: str | None = None,
    max_runs: Optional[int] = None,
) -> float:
    """Return max long-run share of weekly volume for this context.

    Road plans get a frequency-aware ceiling: a low-frequency schedule has few
    runs to spread volume across, so the long run is *legitimately* a bigger
    slice of the week (a 2-run week is essentially one long + one quality/easy),
    but it must never become the whole week. Without a cap at low frequency the
    long run absorbs all the volume the shortfall-fill couldn't place elsewhere,
    cratering quality work to a token sliver and pushing the long run to 85-90 %
    of the week — a classic overuse pattern. The 4+ run ceiling (0.55) is left
    unchanged so the production-quality higher-frequency plans are untouched.
    """
    if trail_profile is not None and training_terrain == "flat" and phase == "peak":
        return 0.65
    if trail_profile is None and max_runs is not None:
        if max_runs <= 2:
            return 0.62
        if max_runs == 3:
            return 0.55
    return 0.55


def get_long_run_ratio_range(
    phase: str,
    target_distance: float,
    weeks: int,
    trail_profile: Optional[TrailProfile] = None,
    max_runs: Optional[int] = None,
) -> tuple[float, float]:
    """
    Get the long run ratio range (min, max) for a phase.

    Args:
        phase: Training phase (base, build, peak, taper).
        target_distance: Race distance in km.
        weeks: Total weeks in plan (for adjusting ratios in short plans).
        trail_profile: Optional trail profile — its bracket selects the
            trail ratio table (ultras pull a higher long-run share).
        max_runs: Runs/week. Low-frequency road plans raise the long-run
            floor so the few runs can carry the prescribed weekly volume.
    """
    if trail_profile is not None:
        min_ratio, max_ratio = _TRAIL_LONG_RUN_RATIOS[trail_profile.bracket][phase]
    else:
        category = get_distance_category(target_distance)
        if category in _ROAD_LONG_RUN_RATIOS:
            min_ratio, max_ratio = _ROAD_LONG_RUN_RATIOS[category][phase]
        else:
            # Legacy 30 km without an explicit trail_profile → standard bracket.
            min_ratio, max_ratio = _TRAIL_LONG_RUN_RATIOS["standard"][phase]

    if weeks <= 10:
        adjustment = 0.03
        min_ratio = max(0.25, min_ratio - adjustment)
        max_ratio = max(min_ratio + 0.02, max_ratio - adjustment)

    # Low-frequency road plans: lift the long-run floor so 2-3 runs can hold
    # the week's volume (the other runs are bounded relative to the long run).
    if trail_profile is None and max_runs is not None:
        floor = LOW_FREQ_LONG_RUN_RATIO_FLOOR.get(max_runs, {}).get(phase)
        if floor is not None:
            min_ratio = max(min_ratio, floor)
            max_ratio = max(max_ratio, floor + 0.04)

    return (min_ratio, max_ratio)


def calculate_long_run_ratio(
    phase: str,
    week_number: int,
    phases: Dict[str, int],
    target_distance: float,
    is_recovery_week: bool,
    total_weeks: int,
    trail_profile: Optional[TrailProfile] = None,
    max_runs: Optional[int] = None,
) -> float:
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
        max_runs: Runs/week — lifts the long-run floor on low-frequency plans.

    Returns:
        Long run ratio as a decimal (e.g., 0.35 for 35%)
    """
    min_ratio, max_ratio = get_long_run_ratio_range(
        phase,
        target_distance,
        total_weeks,
        trail_profile=trail_profile,
        max_runs=max_runs,
    )

    week_in_phase = calculate_week_in_phase(week_number, phase, phases)
    total_in_phase = phases.get(phase, phases.get("taper", 1))

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
    """Long-run cap for a trail profile, scaled continuously with distance.

    Uses a log curve (``A·ln(d) + B``) so the single long run grows smoothly
    with race distance — ~25 km for a 30 km race, ~32 km for a 55 km ultra,
    ~46 km for 100-mile prep — rather than stepping between coarse brackets.
    An experience multiplier nudges the curve up/down, and the result is
    clamped to a sane absolute range. Additional long-day volume beyond the cap
    comes from back-to-back doubles in build/peak weeks (added in the
    workout-builder pass), not a single 50 km+ grind.
    """
    distance_km = max(profile.distance_km, 1.0)
    base_cap = TRAIL_LR_CAP_LOG_A * math.log(distance_km) + TRAIL_LR_CAP_LOG_B
    multiplier = TRAIL_LR_CAP_EXPERIENCE.get(
        experience_level, TRAIL_LR_CAP_EXPERIENCE["intermediate"]
    )
    cap = base_cap * multiplier
    cap = max(TRAIL_LR_CAP_MIN_KM, min(TRAIL_LR_CAP_MAX_KM, cap))
    return round(cap, 1)


def _get_long_run_cap(
    target_distance: float,
    experience_level: str = "intermediate",
    weekly_km: float = 0,
    trail_profile: Optional[TrailProfile] = None,
) -> float:
    """Experience-tiered long run distance caps, with volume-aware scaling.

    When weekly volume is high enough that the static cap would prevent
    filling target volume, the cap scales up to a hard ceiling. Trail /
    ultra plans use a bracket-aware cap that scales with race distance,
    topping out around 46 km for 100-mile prep.
    """
    if trail_profile is not None:
        # Bracket cap is authoritative for trail. Weekly volume can't push
        # above it — additional long-day load belongs in back-to-back doubles
        # rather than ever-bigger single runs.
        return _trail_long_run_cap(trail_profile, experience_level)

    tier = ROAD_LONG_RUN_CAPS.get(target_distance)
    if tier:
        base_cap = tier.get(experience_level, tier["intermediate"])
    else:
        base_cap = target_distance * FALLBACK_LONG_RUN_CAP_RATIO

    if weekly_km <= 0:
        return base_cap

    ceiling = get_hard_ceiling(target_distance)
    volume_ratio = weekly_km * LONG_RUN_VOLUME_RATIO
    if volume_ratio > base_cap:
        return min(round(volume_ratio, 1), ceiling)
    return base_cap


def calculate_long_run_distance(
    total_km: float,
    target_distance: float,
    weeks: int = 12,
    week_number: int = 1,
    phase: str = "build",
    is_recovery_week: bool = False,
    experience_level: str = "intermediate",
    profile: Optional[dict] = None,
    trail_profile: Optional[TrailProfile] = None,
    training_terrain: str | None = None,
    long_run_pace_min_km: Optional[float] = None,
    max_runs: Optional[int] = None,
    prev_long_run_km: Optional[float] = None,
) -> float:
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
        phase,
        week_number,
        phases,
        target_distance,
        is_recovery_week,
        weeks,
        trail_profile=trail_profile,
        max_runs=max_runs,
    )

    long_run_base = total_km * long_run_ratio

    long_run_cap = _get_long_run_cap(
        target_distance,
        experience_level,
        weekly_km=total_km,
        trail_profile=trail_profile,
    )

    # Trail peak: pull the long run up to a race-distance share when the
    # weekly-volume ratio would otherwise leave it too short for the race.
    # Bracket cap and the weekly-safety cap below still bound the result.
    if trail_profile is not None and phase == "peak" and not is_recovery_week:
        race_fraction = get_trail_peak_race_fraction(
            trail_profile,
            training_terrain=training_terrain,
        )
        race_floor = target_distance * race_fraction
        long_run_base = max(long_run_base, race_floor)

    long_run_base = min(long_run_base, long_run_cap)

    # Trail-only weekly safety cap: even with a generous race-fraction floor,
    # a single run shouldn't exceed 55 % of the week's volume — that load
    # belongs spread across back-to-back doubles or higher overall mileage.
    if trail_profile is not None and total_km > 0 and not is_recovery_week:
        weekly_cap_ratio = get_weekly_long_run_ratio_cap(
            phase,
            trail_profile=trail_profile,
            training_terrain=training_terrain,
        )
        long_run_base = min(long_run_base, total_km * weekly_cap_ratio)

    # Low-frequency road weekly-share cap, applied upfront so the remaining
    # volume flows to the quality/easy budget instead of the long run absorbing
    # it all. Mirrors the trail safety cap above. 4+ run road plans are left to
    # the post-pass (enforce_long_run_ratio_cap), which can redistribute excess
    # to their easy runs; low-frequency weeks often have no easy run to receive
    # it, so bounding the long run before sizing quality is what keeps both
    # sessions substantial.
    if (
        trail_profile is None
        and max_runs is not None
        and max_runs <= 3
        and total_km > 0
        and not is_recovery_week
    ):
        weekly_cap_ratio = get_weekly_long_run_ratio_cap(phase, max_runs=max_runs)
        long_run_base = min(long_run_base, total_km * weekly_cap_ratio)

    # Road-only long-run time cap, layered on the % cap (audit E7 time cap).
    # Applied only when a real pace is known (from VDOT zones) so a fit runner
    # without logged pace data is never falsely shortened. Trail/ultra opt out.
    if trail_profile is None and long_run_pace_min_km and long_run_pace_min_km > 0:
        time_cap_km = (MAX_LONG_RUN_HOURS * 60.0) / long_run_pace_min_km
        long_run_base = min(long_run_base, time_cap_km)

    # Week-over-week growth ceiling for the long run itself, relative to the
    # previous *loading* week's long run (deloads are passed through unchanged
    # and skipped here — they dip by design). The weekly 10% rule bounds total
    # volume but says nothing about how fast the single longest, highest-risk
    # run may grow. On trail plans the peak phase introduces a race-distance
    # floor (a fraction of *race distance*, not weekly volume) only once the
    # peak phase starts, so without this the long run could jump ~30% in a
    # single step at the build→peak boundary while the weekly total still ramped
    # smoothly. The long run may grow by the larger of a percentage or a fixed
    # absolute step, so short-race long runs add a sensible few km while ultra
    # long runs (large absolute values) still step up proportionally. The
    # race-distance floor is still reached — just ramped into across the peak
    # weeks. The km trimmed here flow to the week's easy runs downstream, so
    # weekly volume is preserved.
    if prev_long_run_km and prev_long_run_km > 0 and not is_recovery_week:
        growth_ceiling = max(
            prev_long_run_km * LONG_RUN_GROWTH_PCT,
            prev_long_run_km + LONG_RUN_GROWTH_ABS_KM,
        )
        long_run_base = min(long_run_base, growth_ceiling)

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


def get_phase_distribution(
    phase: str,
    target_distance: float = 10.0,
    terrain: str | None = None,
    trail_profile: Optional[TrailProfile] = None,
) -> Dict[str, float]:
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
        target_distance,
        terrain=terrain,
        trail_profile=trail_profile,
    )
    return PHASE_DISTRIBUTIONS.get(phase, PHASE_DISTRIBUTIONS["taper"])[dist_key]


def calculate_quality_distances(
    total_km: float,
    phase: str,
    distribution: Dict[str, int],
    is_recovery_week: bool,
    long_run_distance: float = 0,
    target_distance: float = 10.0,
    terrain: str | None = None,
    trail_profile: Optional[TrailProfile] = None,
) -> Dict[str, float]:
    """Calculate distances for quality workouts based on phase distribution."""
    quality_distances = {}

    if is_recovery_week:
        return {"tempo": 0, "interval": 0, "hill": 0}

    phase_dist = get_phase_distribution(
        phase,
        target_distance,
        terrain=terrain,
        trail_profile=trail_profile,
    )

    remaining_km = total_km - long_run_distance

    non_long_pct = max(0.01, 1 - phase_dist["long"])

    # Mountain race + flat training: if hill sessions were substituted away,
    # keep the race-specific quality load by redistributing hill budget to
    # flat-executable quality types.
    effective_pct = {
        "tempo": phase_dist.get("tempo", 0.0),
        "interval": phase_dist.get("interval", 0.0),
        "hill": phase_dist.get("hill", 0.0),
    }
    if (
        terrain == "flat"
        and trail_profile is not None
        and trail_profile.elevation_class != "flat"
        and distribution.get("hill", 0) == 0
        and phase_dist.get("hill", 0) > 0
    ):
        hill_budget = phase_dist["hill"]
        effective_pct["hill"] = 0.0
        has_interval = distribution.get("interval", 0) > 0
        has_tempo = distribution.get("tempo", 0) > 0
        if has_interval and has_tempo:
            interval_share = (
                0.60 if trail_profile.elevation_class == "mountainous" else 0.50
            )
            effective_pct["interval"] += hill_budget * interval_share
            effective_pct["tempo"] += hill_budget * (1.0 - interval_share)
        elif has_interval:
            effective_pct["interval"] += hill_budget
        elif has_tempo:
            effective_pct["tempo"] += hill_budget

    for qtype in ("tempo", "interval", "hill"):
        if distribution.get(qtype, 0) > 0:
            pct = effective_pct.get(qtype, 0)
            dist = remaining_km * (pct / non_long_pct) if pct > 0 else 0
            quality_distances[qtype] = round(max(dist, 1.0), 1)

    return quality_distances
