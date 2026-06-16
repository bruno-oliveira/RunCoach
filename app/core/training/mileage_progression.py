"""Weekly mileage progression logic.

Handles peak mileage calculation and week-over-week progression
with 10% rule enforcement and phase-aware periodization.
"""

from typing import List, Optional

from app.core.training.phase_calculator import (
    calculate_phases,
    get_phase,
    is_recovery_week,
)
from app.core.training.road_profile import classify_road
from app.core.training.trail_profile import (
    TrailProfile,
    is_trail_target,
    trail_max_weekly_mileage,
)
from app.core.training.tuning import (
    ACWR_PEAK_FACTORS,
    BASE_PHASE_END_FRACTION,
    MAX_PEAK_MILEAGE,
    MIN_NON_RECOVERY_BUMP,
    PEAK_OSCILLATION_BASE,
    PEAK_OSCILLATION_STEP,
    RECOVERY_WEEK_RATIO,
    RUNS_PER_WEEK_FACTOR_MAX,
    RUNS_PER_WEEK_FACTOR_MIN,
    RUNS_PER_WEEK_REFERENCE,
    RUNS_PER_WEEK_VOLUME_STEP,
    TRAIL_BRACKET_PEAK_TARGETS,
    VOLUME_TREND_CAPS,
    WEEK_OVER_WEEK_CAP,
)

# Per road band: (floor_km, multiplier on current_km) for the ideal peak.
# Floors and multipliers raised toward modern training-app prescriptions:
# weekly volume is the primary driver of endurance adaptation, so the target
# peak pulls runners with modest bases up to genuinely productive mileage
# rather than parking them just above where they started. The week-over-week
# cap and absolute MAX_PEAK_MILEAGE ceilings still bound the ramp.
_ROAD_PEAK_PARAMS = {
    "5k": (24, 1.7),
    "10k": (32, 1.85),
    "half": (48, 2.1),
    "marathon": (64, 2.25),
}


def _acwr_peak_factor(profile: Optional[dict]) -> float:
    """Return a peak-mileage multiplier based on ACWR injury risk."""
    if not profile:
        return 1.0
    risk = profile.get("acwr_risk", "low")
    return ACWR_PEAK_FACTORS.get(risk, 1.0)


def _volume_trend_cap(profile: Optional[dict]) -> float:
    """Return the effective week-over-week cap based on volume trend."""
    if not profile:
        return WEEK_OVER_WEEK_CAP
    trend = profile.get("volume_trend", "stable")
    return VOLUME_TREND_CAPS.get(trend, WEEK_OVER_WEEK_CAP)


def _runs_per_week_factor(max_runs: int) -> float:
    """Nudge the peak-mileage target around the reference training frequency.

    ``RUNS_PER_WEEK_REFERENCE`` runs/week is the neutral anchor (factor 1.0);
    higher-frequency schedules can absorb a little more weekly volume and
    lower-frequency ones a little less, so plans for the same race and fitness
    no longer land on identical km regardless of how many days the runner
    trains. The swing is clamped to stay modest; the absolute peak ceilings
    applied by the caller still bound the result.
    """
    factor = 1.0 + RUNS_PER_WEEK_VOLUME_STEP * (max_runs - RUNS_PER_WEEK_REFERENCE)
    return max(RUNS_PER_WEEK_FACTOR_MIN, min(RUNS_PER_WEEK_FACTOR_MAX, factor))


def _trail_ideal_peak(profile: TrailProfile, current_km: float) -> float:
    """Bracket-aware target peak weekly mileage for a trail/ultra plan."""
    multiplier, floor = TRAIL_BRACKET_PEAK_TARGETS[profile.bracket]
    return max(floor, current_km * multiplier)


def get_ideal_peak(
    target_distance: float,
    current_km: float,
    weeks: int,
    trail_profile: Optional[TrailProfile] = None,
) -> float:
    """Get ideal peak mileage based on race distance.

    Multipliers are conservative — suitable for recreational runners who
    want to finish strong without needing elite-level weekly volume.

    Trail / ultra plans use a bracket-aware floor and a continuous ceiling
    in distance × elevation (see ``trail_profile.trail_max_weekly_mileage``).
    """
    if trail_profile is not None:
        ideal_peak = _trail_ideal_peak(trail_profile, current_km)
        return min(ideal_peak, trail_max_weekly_mileage(trail_profile))

    if is_trail_target(target_distance, trail_profile):
        ideal_peak = max(45, current_km * 1.8)
    else:
        floor_km, mult = _ROAD_PEAK_PARAMS[classify_road(target_distance)]
        ideal_peak = max(floor_km, current_km * mult)

    # Apply absolute ceiling so high-base runners don't get absurd peaks
    cap = MAX_PEAK_MILEAGE.get(target_distance)
    if cap is not None:
        ideal_peak = min(ideal_peak, cap)

    return ideal_peak


def get_peak_mileage(
    target_distance: float,
    current_km: float,
    weeks: int,
    vdot: Optional[float] = None,
    profile: Optional[dict] = None,
    trail_profile: Optional[TrailProfile] = None,
) -> float:
    """
    Determine peak weekly mileage with length-based multipliers and optional VDOT adjustment.
    Higher VDOT runners can absorb slightly more volume (better aerobic fitness / recovery).

    When a RunnerProfile is provided, ACWR injury risk reduces the peak:
    - high risk → 15% lower peak
    - very_high risk → 25% lower peak

    Trail / ultra plans bypass the per-distance ``MAX_PEAK_MILEAGE`` lookup
    in favour of the continuous ceiling derived from distance + elevation.
    """
    # How far above the current base the peak target may sit. This is the
    # binding constraint for runners starting from a modest base: with the old
    # 1.5/2.6 envelope a 20 km/wk runner on a 12-week plan was throttled to
    # 20 * 2.125 ≈ 42 km regardless of the race's ideal peak, so raising the
    # per-distance ceilings alone never reached them. A more generous envelope
    # lets a low-base runner ramp toward the race-appropriate ideal peak; the
    # 10% week-over-week rule still governs how fast they actually get there.
    peak_multiplier = 1 + (1.9 * (weeks / 16))
    peak_multiplier = min(peak_multiplier, 2.8)

    ideal_peak = get_ideal_peak(
        target_distance, current_km, weeks, trail_profile=trail_profile
    )

    # VDOT adjustment: VDOT 30 = 0.95x, VDOT 50 = 1.0x, VDOT 65+ = 1.08x
    if vdot:
        vdot_factor = 0.95 + min(0.13, (vdot - 30) / 350)
        ideal_peak = ideal_peak * vdot_factor

    # ACWR injury-risk adjustment
    ideal_peak *= _acwr_peak_factor(profile)

    if current_km == 0:
        return ideal_peak

    peak = min(current_km * peak_multiplier, ideal_peak)

    # Ensure peak is at least 1.2x base but never exceeds the distance cap
    peak = max(peak, current_km * 1.2)
    if trail_profile is not None:
        peak = min(peak, trail_max_weekly_mileage(trail_profile))
    else:
        cap = MAX_PEAK_MILEAGE.get(target_distance)
        if cap is not None:
            peak = min(peak, cap)

    # Never force more than 10% detraining below the runner's current base.
    # A high-base runner targeting a shorter race still needs meaningful volume.
    if current_km > peak:
        peak = max(current_km * 0.90, peak)

    return peak


def _get_taper_curve(
    taper_weeks: int,
    target_distance: float,
    trail_profile: Optional[TrailProfile] = None,
) -> list[float]:
    """Return taper percentage curve scaled to distance and taper length.

    Trail / ultra runners get a more aggressive taper (eccentric damage from
    descents takes longer to clear). Ultra brackets land in the 3-week taper
    arm and get an even sharper drop than road marathon.
    """
    if taper_weeks == 1:
        return [0.55]
    elif taper_weeks == 2:
        if is_trail_target(target_distance, trail_profile):  # trail: more aggressive
            return [0.72, 0.50]
        return [0.75, 0.55]  # half marathon
    elif taper_weeks == 3:
        if trail_profile is not None and trail_profile.is_ultra:
            return [0.85, 0.65, 0.45]  # ultra: sharper drop than marathon
        return [0.85, 0.70, 0.50]  # marathon
    else:
        return [0.92, 0.82, 0.68, 0.50]  # 4+ week taper


def _ramp_week_km(
    start_km: float,
    end_km: float,
    step_idx: int,
    total_steps: int,
    high_water: float,
    effective_cap: float = WEEK_OVER_WEEK_CAP,
) -> float:
    """Compute one ramp step toward ``end_km``, capped by the 10% rule.

    Linear interpolation from ``start_km`` to ``end_km`` across ``total_steps``
    non-recovery weeks, then clamped by both the week-over-week cap and the
    minimum bump so the week is at least a measurable progression — but only
    when the target is actually above the current base.
    """
    if total_steps <= 0:
        ideal = start_km
    else:
        ideal = start_km + (end_km - start_km) * ((step_idx + 1) / total_steps)
    capped = min(ideal, high_water * effective_cap)
    # Only enforce minimum bump when actually ramping up
    if end_km > start_km:
        return max(capped, high_water * MIN_NON_RECOVERY_BUMP)
    return capped


def _progress_ramp_phase(
    phase_name: str,
    phase_weeks: int,
    phase_start_week: int,
    phase_start_km: float,
    phase_end_km: float,
    phases: dict,
    high_water: float,
    effective_cap: float = WEEK_OVER_WEEK_CAP,
) -> tuple[list[float], float]:
    """Progress a ramp-style phase (base or build) one week at a time.

    Returns ``(weeks_km, new_high_water)``. Non-recovery weeks ramp linearly
    from ``phase_start_km`` to ``phase_end_km`` under the 10% cap; recovery
    weeks dip to ``RECOVERY_WEEK_RATIO * high_water`` without disturbing the
    high-water mark.
    """
    non_recovery_count = sum(
        1
        for i in range(phase_weeks)
        if not is_recovery_week(phase_start_week + i, phase_name, phases)
    )

    weeks_km: list[float] = []
    step_idx = 0
    for week_offset in range(phase_weeks):
        week_number = phase_start_week + week_offset
        if is_recovery_week(week_number, phase_name, phases):
            weeks_km.append(round(high_water * RECOVERY_WEEK_RATIO, 1))
            continue

        week_km = _ramp_week_km(
            phase_start_km,
            phase_end_km,
            step_idx,
            non_recovery_count,
            high_water,
            effective_cap=effective_cap,
        )
        high_water = week_km
        weeks_km.append(round(week_km, 1))
        step_idx += 1

    return weeks_km, high_water


def _progress_peak_phase(
    phases: dict,
    peak_km: float,
    high_water: float,
    effective_cap: float = WEEK_OVER_WEEK_CAP,
) -> tuple[list[float], float]:
    """Progress the peak phase.

    Peak weeks oscillate slightly around peak_km so the body doesn't sit on
    a flat ceiling. Each non-recovery week is capped by the effective week-over-week
    cap to prevent abrupt jumps, especially important for injury-prone runners.
    4+ week peaks include a mid-phase recovery week.
    """
    peak_weeks = phases["peak"]
    phase_start_week = phases["base"] + phases["build"] + 1
    weeks_km: list[float] = []

    for week_offset in range(peak_weeks):
        week_number = phase_start_week + week_offset
        if is_recovery_week(week_number, "peak", phases):
            weeks_km.append(round(high_water * RECOVERY_WEEK_RATIO, 1))
            continue

        oscillation = PEAK_OSCILLATION_BASE + (week_offset % 3) * PEAK_OSCILLATION_STEP
        week_km = peak_km * oscillation
        # Cap every non-recovery peak week by the effective week-over-week cap
        week_km = min(week_km, high_water * effective_cap)
        week_km = max(week_km, high_water)
        high_water = week_km
        weeks_km.append(round(week_km, 1))

    return weeks_km, high_water


def _progress_taper_phase(
    phases: dict,
    taper_base_km: float,
    target_distance: float,
    trail_profile: Optional[TrailProfile] = None,
) -> list[float]:
    """Progress the taper phase.

    Shorter races taper faster; marathon tapers more gradually. Trail tapers
    more aggressively than half (eccentric damage needs extra recovery).

    The curve scales from ``taper_base_km`` — the *realized* peak (high-water
    mark) reached by the loading phases, not the theoretical peak target. On
    short plans a low-base runner may run out of weeks to ramp all the way to
    the target peak under the 10% rule; scaling the taper from the unrealized
    target would make the first taper week *exceed* the actual peak. Anchoring
    to the realized high-water mark guarantees the taper always descends.
    """
    taper_weeks = phases["taper"]
    curve = _get_taper_curve(taper_weeks, target_distance, trail_profile=trail_profile)
    return [
        round(taper_base_km * curve[min(week, len(curve) - 1)], 1)
        for week in range(taper_weeks)
    ]


def _trail_run_ceilings(profile: TrailProfile) -> tuple[float, float]:
    """Per-run distance ceilings for a trail profile.

    The single-run ceiling caps the longest run on plans with few runs/week.
    It scales with race distance so ultra prep gets a genuinely long peak run,
    topping out around 46 km for 100-mile distances — beyond that the remaining
    long-day volume comes from back-to-back doubles, not a single 50 km grind.

    The quality cap controls per-session intensity work (tempo / interval /
    hill repeats); it scales with distance but stays runner-friendly.
    """
    run_ceiling = min(46.0, max(20.0, 0.45 * profile.distance_km))
    q_cap = min(15.0, max(8.0, 0.15 * profile.distance_km))
    return run_ceiling, q_cap


def calculate_weekly_progression(
    current_km: float,
    target_distance: float,
    weeks: int,
    max_runs: int = 4,
    vdot: Optional[float] = None,
    profile: Optional[dict] = None,
    trail_profile: Optional[TrailProfile] = None,
) -> List[float]:
    """
    Calculate weekly mileage with phase-aware progression and 10% rule enforcement.

    Key safety invariant: no non-recovery week increases more than 10% over the
    previous non-recovery week's mileage. Recovery weeks reduce by 35% but the
    "high-water mark" is tracked separately so the post-recovery ramp resumes
    from the pre-recovery level — never recalculating from the dip.

    Phases:
    - Base: Build to 70% of peak, recovery every 4th week
    - Build: Progress from 70% to 100% of peak, recovery every 4th week
    - Peak: Maintain near peak with slight variation
    - Taper: Distance-appropriate progressive reduction toward race week

    When the runner's base already meets or exceeds the target peak (common for
    high-mileage runners training for shorter distances), the ramp phases are
    skipped and weekly mileage is held flat at the capped peak.

    Profile-aware adjustments:
    - ACWR risk: reduces peak mileage (high=15%, very_high=25%)
    - Volume trend: adjusts week-over-week cap (decreasing=5%, increasing=12%)
    """
    phases = calculate_phases(weeks, target_distance, trail_profile=trail_profile)
    peak_km = get_peak_mileage(
        target_distance,
        current_km,
        weeks,
        vdot=vdot,
        profile=profile,
        trail_profile=trail_profile,
    )

    # Frequency scaling: weekly volume tracks training frequency, so a plan with
    # fewer runs/week targets a lower peak than a higher-frequency plan for the
    # same race and fitness. Without this, a 3-run and a 6-run plan landed on
    # identical weekly km — forcing the low-frequency plan into oversized
    # individual runs while the high-frequency plan stayed under-loaded. A
    # downward nudge never detrains a runner below ~90% of their established
    # base; an upward nudge is re-clamped to the absolute peak ceiling so a
    # high-frequency schedule is never pushed past recreational safety limits.
    runs_factor = _runs_per_week_factor(max_runs)
    if runs_factor != 1.0:
        peak_km *= runs_factor
        if runs_factor < 1.0 and current_km > 0:
            peak_km = max(peak_km, current_km * 0.90)
        elif runs_factor > 1.0:
            if trail_profile is not None:
                peak_km = min(peak_km, trail_max_weekly_mileage(trail_profile))
            else:
                cap = MAX_PEAK_MILEAGE.get(target_distance)
                if cap is not None:
                    peak_km = min(peak_km, cap)

    # Cap peak at what can physically be distributed across max_runs
    # within per-run structural limits (long run ceiling + quality caps).
    # Without this, low-run plans target volumes that force the shortfall
    # fill-up to inflate individual runs past safe distances. Applied across
    # all run counts so per-run distances stay bounded regardless of frequency
    # (at higher run counts the ceiling is generous and rarely binds).
    if trail_profile is not None:
        run_ceiling, q_cap = _trail_run_ceilings(trail_profile)
    else:
        _CEILINGS = {5.0: 14.0, 10.0: 22.0, 21.1: 28.0, 30.0: 32.0, 42.2: 38.0}
        _Q_CAPS = {5.0: 5.0, 10.0: 8.0, 21.1: 10.0, 30.0: 12.0, 42.2: 12.0}
        run_ceiling = _CEILINGS.get(target_distance, target_distance * 0.9)
        q_cap = _Q_CAPS.get(target_distance, 8.0)
    quality_slots = 1 if max_runs >= 2 else 0
    distributable = run_ceiling * (max_runs - quality_slots) + q_cap * quality_slots
    peak_km = min(peak_km, distributable)
    # Floor the base target at the runner's current volume: when current_km
    # already exceeds peak*0.70 the old ramp sloped DOWN to 0.70*peak, shedding
    # ~15% of established aerobic volume for the whole base phase. Hold (don't
    # detrain) an already-adequate base, then build from there (audit G5).
    base_end_target = max(peak_km * BASE_PHASE_END_FRACTION, current_km)

    # Volume-trend-aware week-over-week cap
    effective_cap = _volume_trend_cap(profile)

    weekly_progression: List[float] = []

    # If runner's base already meets or exceeds the target peak, skip ramping
    # and hold around peak_km. Apply a mild week-to-week undulation (and the
    # normal recovery dips) so the held-volume block reads as real periodization
    # rather than a dead-flat, unvarying line (audit G5). The wave never exceeds
    # peak_km, and recovery weeks still dip to RECOVERY_WEEK_RATIO.
    if current_km >= peak_km:
        high_water = peak_km
        phase_start_week = 1
        _UNDULATION = (1.0, 0.96, 0.98)
        load_week_idx = 0
        for week_offset in range(weeks - phases["taper"]):
            week_number = phase_start_week + week_offset
            phase = get_phase(week_number, phases)
            if is_recovery_week(week_number, phase, phases):
                weekly_progression.append(round(high_water * RECOVERY_WEEK_RATIO, 1))
            else:
                factor = _UNDULATION[load_week_idx % len(_UNDULATION)]
                weekly_progression.append(round(high_water * factor, 1))
                load_week_idx += 1
    else:
        high_water = current_km

        base_weeks, high_water = _progress_ramp_phase(
            "base",
            phases["base"],
            phase_start_week=1,
            phase_start_km=current_km,
            phase_end_km=base_end_target,
            phases=phases,
            high_water=high_water,
            effective_cap=effective_cap,
        )
        weekly_progression.extend(base_weeks)

        build_start = max(high_water, base_end_target)
        build_weeks, high_water = _progress_ramp_phase(
            "build",
            phases["build"],
            phase_start_week=phases["base"] + 1,
            phase_start_km=build_start,
            phase_end_km=peak_km,
            phases=phases,
            high_water=high_water,
            effective_cap=effective_cap,
        )
        weekly_progression.extend(build_weeks)

        peak_weeks, high_water = _progress_peak_phase(
            phases, peak_km, high_water, effective_cap=effective_cap
        )
        weekly_progression.extend(peak_weeks)

    # Taper descends from the realized peak (high_water), which on short or
    # low-base plans can sit below the theoretical peak_km target — anchoring
    # to it keeps the first taper week from overshooting the actual peak.
    weekly_progression.extend(
        _progress_taper_phase(
            phases,
            high_water,
            target_distance,
            trail_profile=trail_profile,
        )
    )

    return weekly_progression
