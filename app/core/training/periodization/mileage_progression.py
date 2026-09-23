"""Weekly mileage progression logic.

Handles peak mileage calculation and week-over-week progression
with 10% rule enforcement and phase-aware periodization.
"""

from typing import Dict, List, Optional, Tuple

from app.core.training.periodization.phase_calculator import (
    calculate_phases,
    get_phase,
    is_recovery_week,
)
from app.core.training.profiles.road_profile import classify_road
from app.core.training.profiles.trail_profile import (
    TrailProfile,
    is_trail_target,
    trail_max_weekly_mileage,
)
from app.core.training.tuning import (
    BASE_PHASE_END_FRACTION,
    MAX_EASY_RUN_KM,
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


def typical_session_length_km(trail_profile: Optional[TrailProfile] = None) -> float:
    """The per-session distance (km) a plan's slots can typically hold.

    The reachability model needs a "typical session" to multiply by frequency,
    and inventing one would create a second set of magic numbers that drifts
    from the constants the week builder actually enforces. Road weeks are
    assembled from easy runs explicitly bounded by the absolute
    ``MAX_EASY_RUN_KM`` ceiling (~70-80 min of easy running) — that ceiling is
    the honest per-slot dose a schedule can assume. Trail/ultra sessions run
    longer by design (back-to-back long days carry the volume a road plan
    spreads across easy slots), so the discipline's own single-run ceiling
    stands in instead.

    Pure: a lookup over existing tuning constants, nothing more.
    """
    if trail_profile is not None:
        run_ceiling, _q_cap = _trail_run_ceilings(trail_profile)
        return run_ceiling
    return MAX_EASY_RUN_KM


def weekly_capacity(frequency: int, typical_session_length: float) -> float:
    """Weekly km the requested frequency can carry at typical session lengths.

    The capacity model in one line: a week is worth what its
    ``frequency`` sessions can each hold. Kept public so callers and tests
    reason about capacity with the same arithmetic the resolver uses.
    """
    return max(0, int(frequency)) * max(0.0, typical_session_length)


def resolve_reachable_target(
    target: float,
    frequency: int,
    typical_session_length: float,
    base_km: float = 0.0,
) -> Tuple[float, Optional[str], Dict[str, float]]:
    """Cap a modelled weekly target at what the schedule can actually deliver.

    The progression model derives its peak from the runner's base and the
    race's ideal volume; it is blind to how many sessions the runner has
    offered to carry that volume in. When the implied peak exceeds the week's
    capacity, the target is not a plan, it is a wish — downstream trimming
    produces a week that overshoots what its slots can hold or craters below
    the target it was sized from. This resolver makes reachability a
    first-class constraint *before* any week is built.

    Capacity is the larger of two honest floors:

    - ``typical_session_length x frequency`` — what the schedule can hold at
      the per-session dose the discipline's tuning assumes; and
    - ``base_km`` — what the runner already demonstrably runs. Their
      demonstrated per-session length is ``base / frequency``, which they have
      proven they can hold, so an established base raises the capacity floor
      (and keeps the cap from prescribing enforced detraining — the P1 rule).

    Semantics:

    - ``target <= capacity``: returned unchanged with ``cap_reason=None`` —
      the progression model is already reachable.
    - otherwise the target is capped at capacity, with the reason naming the
      binding floor: ``"frequency_capacity"`` when the typical-session term
      binds (the low-frequency case the capacity model exists for) and
      ``"base_volume_ceiling"`` when the runner's own base binds (a
      high-volume runner whose frequency cannot carry even their current
      week — the peak is pinned at the base rather than ramped past it). The
      ramp above the base is compressed proportionally by
      :func:`cap_progression_to_peak`.

    The result never drops below ``0.5 x typical_session_length`` (a week
    smaller than half a session is not a training week) nor above the
    requested target (this is a cap, never a raise).

    Returns ``(reachable, cap_reason, diagnostics)``. ``cap_reason`` is
    ``None`` when the requested target stands. The diagnostics dict carries
    ``requested``, ``reachable``, ``capacity``, ``scaled_from_start`` (the
    ramp's start after scaling — the runner's base, never above the reachable
    peak) and ``scaled_from_peak`` (the peak after scaling), so callers can
    log target fidelity without recomputing it.

    Deterministic and side-effect-free: no I/O, no clocks, no randomness.
    """
    frequency_capacity = weekly_capacity(frequency, typical_session_length)
    capacity = max(frequency_capacity, base_km)
    if target <= capacity:
        reachable, cap_reason = target, None
    elif base_km > frequency_capacity:
        reachable, cap_reason = base_km, "base_volume_ceiling"
    else:
        reachable, cap_reason = frequency_capacity, "frequency_capacity"
    # A week under half a session is not a training week; a cap must never
    # raise the target above what was asked for.
    reachable = max(reachable, min(target, 0.5 * typical_session_length))
    diagnostics = {
        "requested": target,
        "reachable": reachable,
        "capacity": capacity,
        "scaled_from_start": min(base_km, reachable),
        "scaled_from_peak": reachable,
    }
    return reachable, cap_reason, diagnostics


def cap_progression_to_peak(
    weekly_progression: List[float],
    reachable_peak: float,
    base_km: float,
) -> List[float]:
    """Rescale a weekly progression so its peak lands on ``reachable_peak``.

    The ramp's shape above the runner's established base is preserved: weeks
    at or below ``base_km`` pass through untouched (a reachability cap may
    never detrain an established base), and the excess above the base is
    compressed linearly so base maps to base and peak maps to the reachable
    peak — proportional spacing, one common factor. Pure: returns a new list.
    """
    if not weekly_progression:
        return []
    peak = max(weekly_progression)
    if peak <= reachable_peak or peak <= base_km or reachable_peak < base_km:
        # Nothing above the base to compress, or the cap would pin the ramp
        # below the runner's current volume — leave the shape alone.
        return list(weekly_progression)
    factor = (reachable_peak - base_km) / (peak - base_km)
    return [
        round(w, 1) if w <= base_km else round(base_km + (w - base_km) * factor, 1)
        for w in weekly_progression
    ]


def runs_per_week_volume_factor(max_runs: int) -> float:
    """Nudge the peak-mileage target around the reference training frequency.

    ``RUNS_PER_WEEK_REFERENCE`` runs/week is the neutral anchor (factor 1.0);
    higher-frequency schedules can absorb a little more weekly volume and
    lower-frequency ones a little less, so plans for the same race and fitness
    no longer land on identical km regardless of how many days the runner
    trains. The swing is clamped to stay modest; the absolute peak ceilings
    applied by the caller still bound the result.

    Public so other plan families (e.g. the fitness generator) can share the
    same frequency→volume relationship rather than re-deriving it.
    """
    factor = 1.0 + RUNS_PER_WEEK_VOLUME_STEP * (max_runs - RUNS_PER_WEEK_REFERENCE)
    return max(RUNS_PER_WEEK_FACTOR_MIN, min(RUNS_PER_WEEK_FACTOR_MAX, factor))


# Backwards-compatible private alias for in-module callers.
_runs_per_week_factor = runs_per_week_volume_factor


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
    trail_profile: Optional[TrailProfile] = None,
) -> float:
    """
    Determine peak weekly mileage with length-based multipliers and an optional
    bounded VDOT adjustment.

    VDOT primarily drives pace zones elsewhere. Its volume adjustment here is
    deliberately secondary and is often absorbed by race, duration, capacity,
    or absolute ceilings; callers must not interpret similar weekly totals as
    VDOT having no effect on the prescribed workout paces.

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
    #
    # NOTE: applying the ceiling *after* this floor (making it absolute) was
    # implemented and reverted. It fixes a real inconsistency — a 200 km/week
    # base targeted 126 km for a marathon against a documented 100 km ceiling,
    # and 180 km for a 5K against 50 — but it overrides a deliberate P1 safety
    # rule (``tests/test_security/test_p1_bugs.py::TestHighBaseDetraining``):
    # a high-base runner must not be taken more than 10% below what they already
    # run. The two invariants genuinely conflict, so resolving it is a product
    # call, not a silent swap.
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
        # Sub-marathon races don't need a deep two-week drawdown: the first
        # taper week stays closer to peak (only race week falls away sharply),
        # which preserves fitness and recovers a little weekly volume. Trail
        # still tapers a touch more than road (descent damage clears slower).
        if is_trail_target(target_distance, trail_profile):
            return [0.80, 0.52]
        return [0.82, 0.55]  # half marathon
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


def contracted_long_run_slot(
    target_distance: float,
    current_km: float,
    candidate_peak: float,
    easy_slots: int,
    q_cap: float,
    quality_slots: int,
) -> float:
    """Capacity of the long-run slot, from the cap the plan is *contracted* to.

    The week's long run is sized by
    ``long_run_calculator.calculate_long_run_distance`` and clamped by
    ``long_run_cap`` — the experience-tiered, volume-aware cap the plan actually
    enforces (18-19 km for a half marathon, not 28). The progression model used
    to size this slot from a free-standing per-distance table instead, so the
    modelled target asked for volume the week builder could not place. That
    over-statement was the residual shortfall the envelope harness measures, and
    it compounded: ``fill_shortfall`` derives its own spill cap from the same
    inflated target (``weekly_km=total_km``), so the delivered long run could
    exceed the contract cap computed at the volume the week actually delivered.

    The cap is volume-aware, so its argument is the week's own total — a fixed
    point. Two iterations converge: the first evaluates the cap at the total
    implied by the *static* tier cap, the second at the total that result
    implies. ``candidate_peak`` bounds the slot, so this only ever tightens the
    target, never raises it.

    Nothing moves where the static tier cap already binds: below
    ``base_cap / LONG_RUN_VOLUME_RATIO`` weekly km the volume term cannot exceed
    the tier cap, so both iterations return it and the slot is the tier value.
    """
    from app.core.training.periodization.long_run_calculator import long_run_cap
    from app.core.training.periodization.strength_plan import derive_experience_level

    experience = derive_experience_level(current_km)
    rest = MAX_EASY_RUN_KM * easy_slots + q_cap * quality_slots
    slot = long_run_cap(target_distance, experience, weekly_km=0.0)
    for _ in range(2):
        slot = long_run_cap(target_distance, experience, weekly_km=slot + rest)
    return min(slot, candidate_peak)


def calculate_weekly_progression(
    current_km: float,
    target_distance: float,
    weeks: int,
    max_runs: int = 4,
    vdot: Optional[float] = None,
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
    """
    phases = calculate_phases(weeks, target_distance, trail_profile=trail_profile)
    peak_km = get_peak_mileage(
        target_distance,
        current_km,
        weeks,
        vdot=vdot,
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
    else:
        # Apply the same absolute ceiling at the neutral four-run reference.
        # Previously it only re-applied when the frequency factor was above
        # one, so a high-base 48-loop plan targeted 153 km at four runs and
        # dropped to the safe 140 km ceiling when a fifth day was added.
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
        _Q_CAPS = {5.0: 5.0, 10.0: 8.0, 21.1: 10.0, 30.0: 12.0, 42.2: 12.0}
        q_cap = _Q_CAPS.get(target_distance, 8.0)
    quality_slots = 1 if max_runs >= 2 else 0
    easy_slots = max(0, max_runs - quality_slots - 1)
    if trail_profile is None:
        # Road: a week is one long run, one quality session, and ``easy_slots``
        # easy runs. Every easy slot is bounded by the absolute
        # ``MAX_EASY_RUN_KM`` cap that ``fill_shortfall`` enforces — sizing each
        # one at the long run's ceiling instead (which the 4+ run branch used to
        # do) over-estimated capacity by ``(run_ceiling - MAX_EASY_RUN_KM) *
        # easy_slots`` every week: 0 km for a 5K (the two caps coincide), 16 km
        # for a 10K, 28 km for a half, 48 km for a 4-run marathon. The long-run
        # slot is then sized from the cap the plan is actually contracted to
        # (see ``contracted_long_run_slot``), so the modelled target is what the
        # week builder can place rather than a free-standing table's guess. One
        # formula for every frequency.
        run_ceiling = contracted_long_run_slot(
            target_distance, current_km, peak_km, easy_slots, q_cap, quality_slots
        )
        distributable = (
            run_ceiling + MAX_EASY_RUN_KM * easy_slots + q_cap * quality_slots
        )
    else:
        # Trail/ultra easy runs are bounded by the long run itself rather than
        # by ``MAX_EASY_RUN_KM`` — back-to-back doubles are intentionally long —
        # so there every non-quality slot may carry up to the run ceiling.
        distributable = run_ceiling * (max_runs - quality_slots) + q_cap * quality_slots
    peak_km = min(peak_km, distributable)
    # Floor the base target at the runner's current volume: when current_km
    # already exceeds peak*0.70 the old ramp sloped DOWN to 0.70*peak, shedding
    # ~15% of established aerobic volume for the whole base phase. Hold (don't
    # detrain) an already-adequate base, then build from there (audit G5).
    base_end_target = max(peak_km * BASE_PHASE_END_FRACTION, current_km)

    effective_cap = WEEK_OVER_WEEK_CAP

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
