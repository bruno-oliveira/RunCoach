"""Weekly mileage progression logic.

Handles peak mileage calculation and week-over-week progression
with 10% rule enforcement and phase-aware periodization.
"""

from typing import List, Optional

from app.core.training.phase_calculator import calculate_phases, get_phase, is_recovery_week


# --- Progression safety constants ---------------------------------------------
# Non-recovery weeks can increase at most this fraction above the previous
# non-recovery mileage. The classic "10% rule" that prevents overuse injuries.
WEEK_OVER_WEEK_CAP = 1.10

# Recovery weeks cut mileage to this fraction of the high-water mark.
# A ~35% reduction gives the body a real absorption window without losing
# the fitness gained in the preceding load block.
RECOVERY_WEEK_RATIO = 0.65

# Minimum bump to register a "progressed" non-recovery week — otherwise the
# week would be flat and look like a plateau.
MIN_NON_RECOVERY_BUMP = 1.01

# Base phase ends at this fraction of peak mileage; build phase ramps from
# here to full peak. Gives the runner time to adapt to the eventual peak
# before quality work layers on.
BASE_PHASE_END_FRACTION = 0.70

# Small oscillation within peak weeks so the body doesn't sit on an exact
# ceiling. Cycles 0.97 → 0.98 → 0.99 → repeat.
PEAK_OSCILLATION_BASE = 0.97
PEAK_OSCILLATION_STEP = 0.01


# Absolute maximum weekly mileage per race distance.
# Geared toward recreational runners — sufficient to finish strong without
# requiring elite-level volume.
MAX_PEAK_MILEAGE = {
    5.0: 40.0,     # Recreational 5K runners peak around 25-40 km/wk
    10.0: 50.0,    # Recreational 10K runners ~30-50 km/wk
    21.1: 65.0,    # Recreational half marathon ~40-65 km/wk
    30.0: 75.0,    # Recreational trail 30K ~50-75 km/wk
    42.2: 85.0,    # Recreational marathon ~55-85 km/wk
}


def get_ideal_peak(target_distance: float, current_km: float, weeks: int) -> float:
    """Get ideal peak mileage based on race distance.

    Multipliers are conservative — suitable for recreational runners who
    want to finish strong without needing elite-level weekly volume.
    """
    if target_distance == 30:
        ideal_peak = max(35, current_km * 1.5)
    elif target_distance <= 5:
        ideal_peak = max(20, current_km * 1.5)
    elif target_distance <= 10:
        ideal_peak = max(25, current_km * 1.6)
    elif target_distance <= 21.1:
        ideal_peak = max(30, current_km * 1.7)
    else:
        ideal_peak = max(40, current_km * 1.5)

    # Apply absolute ceiling so high-base runners don't get absurd peaks
    cap = MAX_PEAK_MILEAGE.get(target_distance)
    if cap is not None:
        ideal_peak = min(ideal_peak, cap)

    return ideal_peak


def get_peak_mileage(target_distance: float, current_km: float, weeks: int,
                     vdot: Optional[float] = None) -> float:
    """
    Determine peak weekly mileage with length-based multipliers and optional VDOT adjustment.
    Higher VDOT runners can absorb slightly more volume (better aerobic fitness / recovery).
    """
    peak_multiplier = 1 + (1.5 * (weeks / 16))
    peak_multiplier = min(peak_multiplier, 2.6)

    ideal_peak = get_ideal_peak(target_distance, current_km, weeks)

    # VDOT adjustment: VDOT 30 = 0.95x, VDOT 50 = 1.0x, VDOT 65+ = 1.08x
    if vdot:
        vdot_factor = 0.95 + min(0.13, (vdot - 30) / 350)
        ideal_peak = ideal_peak * vdot_factor

    if current_km == 0:
        return ideal_peak

    peak = min(current_km * peak_multiplier, ideal_peak)

    # Ensure peak is at least 1.2x base but never exceeds the distance cap
    peak = max(peak, current_km * 1.2)
    cap = MAX_PEAK_MILEAGE.get(target_distance)
    if cap is not None:
        peak = min(peak, cap)

    return peak


def _get_taper_curve(taper_weeks: int, target_distance: float) -> list[float]:
    """Return taper percentage curve scaled to distance and taper length."""
    if taper_weeks == 1:
        return [0.55]
    elif taper_weeks == 2:
        if target_distance == 30.0:           # trail: more aggressive
            return [0.72, 0.50]
        return [0.75, 0.55]                   # half marathon
    elif taper_weeks == 3:
        return [0.85, 0.70, 0.50]             # marathon
    else:
        return [0.92, 0.82, 0.68, 0.50]       # 4+ week taper


def _ramp_week_km(start_km: float, end_km: float, step_idx: int,
                  total_steps: int, high_water: float) -> float:
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
    capped = min(ideal, high_water * WEEK_OVER_WEEK_CAP)
    # Only enforce minimum bump when actually ramping up
    if end_km > start_km:
        return max(capped, high_water * MIN_NON_RECOVERY_BUMP)
    return capped


def _progress_ramp_phase(phase_name: str, phase_weeks: int, phase_start_week: int,
                         phase_start_km: float, phase_end_km: float,
                         phases: dict, high_water: float) -> tuple[list[float], float]:
    """Progress a ramp-style phase (base or build) one week at a time.

    Returns ``(weeks_km, new_high_water)``. Non-recovery weeks ramp linearly
    from ``phase_start_km`` to ``phase_end_km`` under the 10% cap; recovery
    weeks dip to ``RECOVERY_WEEK_RATIO * high_water`` without disturbing the
    high-water mark.
    """
    non_recovery_count = sum(
        1 for i in range(phase_weeks)
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
            phase_start_km, phase_end_km, step_idx, non_recovery_count, high_water,
        )
        high_water = week_km
        weeks_km.append(round(week_km, 1))
        step_idx += 1

    return weeks_km, high_water


def _progress_peak_phase(phases: dict, peak_km: float,
                         high_water: float) -> tuple[list[float], float]:
    """Progress the peak phase.

    Peak weeks oscillate slightly around peak_km so the body doesn't sit on
    a flat ceiling. The first peak week is capped to +10% over build
    high-water to prevent an abrupt jump; subsequent weeks are uncapped.
    4+ week peaks include a mid-phase recovery week.
    """
    peak_weeks = phases['peak']
    phase_start_week = phases['base'] + phases['build'] + 1
    weeks_km: list[float] = []

    for week_offset in range(peak_weeks):
        week_number = phase_start_week + week_offset
        if is_recovery_week(week_number, 'peak', phases):
            weeks_km.append(round(high_water * RECOVERY_WEEK_RATIO, 1))
            continue

        oscillation = PEAK_OSCILLATION_BASE + (week_offset % 3) * PEAK_OSCILLATION_STEP
        week_km = peak_km * oscillation
        if week_offset == 0 and peak_weeks >= 2:
            week_km = min(week_km, high_water * WEEK_OVER_WEEK_CAP)
        week_km = max(week_km, high_water)
        high_water = week_km
        weeks_km.append(round(week_km, 1))

    return weeks_km, high_water


def _progress_taper_phase(phases: dict, peak_km: float,
                          target_distance: float) -> list[float]:
    """Progress the taper phase.

    Shorter races taper faster; marathon tapers more gradually. Trail tapers
    more aggressively than half (eccentric damage needs extra recovery).
    The curve is independent of high_water — it scales straight from peak.
    """
    taper_weeks = phases['taper']
    curve = _get_taper_curve(taper_weeks, target_distance)
    return [
        round(peak_km * curve[min(week, len(curve) - 1)], 1)
        for week in range(taper_weeks)
    ]


def calculate_weekly_progression(current_km: float, target_distance: float, weeks: int,
                                 max_runs: int = 4, vdot: Optional[float] = None) -> List[float]:
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
    """
    phases = calculate_phases(weeks, target_distance)
    peak_km = get_peak_mileage(target_distance, current_km, weeks, vdot=vdot)
    base_end_target = peak_km * BASE_PHASE_END_FRACTION

    weekly_progression: List[float] = []

    # If runner's base already meets or exceeds the target peak, skip ramping
    # and hold steady at peak_km with recovery weeks as normal.
    if current_km >= peak_km:
        high_water = peak_km
        phase_start_week = 1
        for week_offset in range(weeks - phases['taper']):
            week_number = phase_start_week + week_offset
            phase = get_phase(week_number, phases)
            if is_recovery_week(week_number, phase, phases):
                weekly_progression.append(round(high_water * RECOVERY_WEEK_RATIO, 1))
            else:
                weekly_progression.append(round(high_water, 1))
    else:
        high_water = current_km

        base_weeks, high_water = _progress_ramp_phase(
            'base', phases['base'], phase_start_week=1,
            phase_start_km=current_km, phase_end_km=base_end_target,
            phases=phases, high_water=high_water,
        )
        weekly_progression.extend(base_weeks)

        build_start = max(high_water, base_end_target)
        build_weeks, high_water = _progress_ramp_phase(
            'build', phases['build'], phase_start_week=phases['base'] + 1,
            phase_start_km=build_start, phase_end_km=peak_km,
            phases=phases, high_water=high_water,
        )
        weekly_progression.extend(build_weeks)

        peak_weeks, high_water = _progress_peak_phase(phases, peak_km, high_water)
        weekly_progression.extend(peak_weeks)

    weekly_progression.extend(_progress_taper_phase(phases, peak_km, target_distance))

    return weekly_progression
