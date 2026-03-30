"""Weekly mileage progression logic.

Handles peak mileage calculation and week-over-week progression
with 10% rule enforcement and phase-aware periodization.
"""

from typing import List, Optional

from app.core.phase_calculator import calculate_phases, is_recovery_week


def get_ideal_peak(target_distance: float, current_km: float, weeks: int) -> float:
    """Get ideal peak mileage based on race distance."""
    if target_distance == 30:
        ideal_peak = 50
    elif target_distance <= 5:
        ideal_peak = max(25, current_km * 2.0)
    elif target_distance <= 10:
        ideal_peak = max(30, current_km * 2.2)
    elif target_distance <= 21.1:
        ideal_peak = max(40, current_km * 2.3)
    else:
        ideal_peak = max(50, current_km * 2.0)

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

    return max(peak, current_km * 1.2)


def calculate_weekly_progression(current_km: float, target_distance: float, weeks: int,
                                 max_runs: int = 4, vdot: Optional[float] = None) -> List[float]:
    """
    Calculate weekly mileage with phase-aware progression and 10% rule enforcement.

    Key safety invariant: no non-recovery week increases more than 10% over the
    previous non-recovery week's mileage.  Recovery weeks reduce by 25% but the
    "high-water mark" is tracked separately so the post-recovery ramp resumes
    from the pre-recovery level -- never recalculating from the dip.

    Phases:
    - Base: Build to 70% of peak, recovery every 4th week
    - Build: Progress from 70% to 100% of peak, recovery every 4th week
    - Peak: Maintain near peak with slight variation
    - Taper: Distance-appropriate progressive reduction toward race week
    """
    phases = calculate_phases(weeks, target_distance)
    peak_km = get_peak_mileage(target_distance, current_km, weeks, vdot=vdot)
    weekly_progression: List[float] = []

    # high_water tracks the last non-recovery mileage (recovery dips don't reset it)
    high_water = current_km

    def _apply_10pct_cap(target: float, reference: float) -> float:
        """Enforce 10% rule: target can't exceed reference * 1.10."""
        return min(target, reference * 1.10)

    # -- Base phase: current -> 70% of peak
    base_end_target = peak_km * 0.70
    non_recovery_base = sum(1 for i in range(phases['base']) if not is_recovery_week(i + 1, 'base', phases))

    base_step = 0
    for week in range(phases['base']):
        week_number = week + 1
        if is_recovery_week(week_number, 'base', phases):
            week_km = high_water * 0.75
        else:
            if non_recovery_base > 0:
                ideal = current_km + (base_end_target - current_km) * ((base_step + 1) / non_recovery_base)
            else:
                ideal = current_km
            week_km = _apply_10pct_cap(ideal, high_water)
            week_km = max(week_km, high_water * 1.01)
            high_water = week_km
            base_step += 1

        weekly_progression.append(round(week_km, 1))

    # -- Build phase: 70% of peak -> 100% of peak
    build_start = max(high_water, base_end_target)
    non_recovery_build = sum(
        1 for i in range(phases['build'])
        if not is_recovery_week(phases['base'] + i + 1, 'build', phases)
    )

    build_step = 0
    for week in range(phases['build']):
        week_number = phases['base'] + week + 1
        should_recover = is_recovery_week(week_number, 'build', phases)

        if should_recover:
            week_km = high_water * 0.75
        else:
            if non_recovery_build > 0:
                ideal = build_start + (peak_km - build_start) * ((build_step + 1) / non_recovery_build)
            else:
                ideal = peak_km
            week_km = _apply_10pct_cap(ideal, high_water)
            week_km = max(week_km, high_water * 1.01)
            high_water = week_km
            build_step += 1

        weekly_progression.append(round(week_km, 1))

    # -- Peak phase: the highest mileage weeks
    # First peak week is capped at +10% over build high-water to prevent
    # abrupt jumps. Subsequent peak weeks are uncapped (summit by definition).
    for week in range(phases['peak']):
        week_km = peak_km * (0.97 + (week % 3) * 0.01)
        if week == 0 and phases['peak'] >= 2:
            week_km = min(week_km, high_water * 1.10)
        week_km = max(week_km, high_water)
        high_water = week_km
        weekly_progression.append(round(week_km, 1))

    # -- Taper phase: distance-appropriate reduction
    taper_weeks = phases['taper']
    for week in range(taper_weeks):
        if taper_weeks == 1:
            week_km = peak_km * 0.60
        elif taper_weeks == 2:
            week_km = peak_km * (0.80 if week == 0 else 0.60)
        elif taper_weeks == 3:
            week_km = peak_km * (0.85 if week == 0 else (0.70 if week == 1 else 0.55))
        else:
            taper_pcts = [0.90, 0.80, 0.65, 0.55]
            pct = taper_pcts[min(week, len(taper_pcts) - 1)]
            week_km = peak_km * pct

        weekly_progression.append(round(week_km, 1))

    return weekly_progression
