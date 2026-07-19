"""Weekly plan orchestration: assemble one week's daily workouts and metadata."""

from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.plan_validator import validate_week_plan
from app.contexts.plan.generators.weekly_plan_builder.budget import (
    allocate_easy_distances,
    apply_quality_caps,
    attach_duration_hints,
    build_workout_for_type,
    resolve_low_budget_quality,
)
from app.contexts.plan.generators.weekly_plan_builder.intensive_weekend import (
    apply_intensive_weekend,
)
from app.contexts.plan.generators.workout_scaler import (
    enforce_long_run_ratio_cap as _enforce_long_run_ratio_cap,
)
from app.contexts.plan.generators.workout_scaler import (
    enforce_long_run_time_cap as _enforce_long_run_time_cap,
)
from app.contexts.plan.generators.workout_scaler import (
    fill_shortfall as _fill_shortfall,
)
from app.contexts.plan.generators.workout_scaler import (
    long_run_pace_min_km as _long_run_pace_min_km,
)
from app.contexts.plan.generators.workout_scaler import (
    reclamp_quality_to_long_run as _reclamp_quality_to_long_run,
)
from app.contexts.plan.generators.workout_scaler import (
    scale_down as _scale_down,
)
from app.core.coaching.coaching_notes_generator import generate_coaching_note
from app.core.training import long_run_calculator, phase_calculator, workout_builders
from app.core.training import workout_distribution as workout_dist_mod
from app.core.training.key_workout_library import overlay_key_workout
from app.core.training.quality_caps import (
    LOW_FREQ_EASY_VS_LONG_RUN,
    MAX_EASY_RUN_KM,
    MAX_EASY_VS_LONG_RUN,
    QUALITY_MIN_DOSE_KM,
)
from app.core.training.training_constants import calculate_week_in_phase
from app.core.training.tuning import MAX_KEY_WORKOUT_VS_LONG_RUN
from app.core.training.vertical_simulation import attach_treadmill_prescriptions


def _vertical_simulation_targets(
    week_total_km: float,
    phase: str,
    is_recovery_week: bool,
    distribution: Dict[str, int],
    training_terrain: Optional[str],
    trail_profile,
) -> Optional[Dict[str, Any]]:
    """Build weekly mountain-load simulation targets for flat-only training.

    Race profile remains the source of mountain demands. When terrain access is
    flat, we surface executable proxies (uphill-effort minutes, eccentric load,
    and hike/run transitions) so athletes can prepare specifically.
    """
    if trail_profile is None or training_terrain != "flat":
        return None
    if trail_profile.elevation_class == "flat":
        return None

    phase_factor = {
        "base": 0.55,
        "build": 0.80,
        "peak": 1.00,
        "taper": 0.45,
    }.get(phase, 0.80)
    if is_recovery_week:
        phase_factor *= 0.75

    race_m_per_km = max(0.0, trail_profile.m_per_km)
    simulated_uphill_m = round(week_total_km * race_m_per_km * phase_factor)

    # Convert simulated vertical to uphill-effort minutes using a conservative
    # vertical ascent rate proxy for sustained trail climbing effort.
    vertical_rate_m_per_min = 12.0
    uphill_minutes = int(round(simulated_uphill_m / vertical_rate_m_per_min))
    downhill_minutes = int(round(uphill_minutes * 0.60))

    quality_sessions = sum(
        distribution.get(k, 0) for k in ("tempo", "interval", "hill")
    )
    transitions = max(2, quality_sessions * 2)
    if phase == "peak":
        transitions += 2

    return {
        "enabled": True,
        "race_elevation_class": trail_profile.elevation_class,
        "race_m_per_km": round(race_m_per_km, 1),
        "simulated_uphill_m": simulated_uphill_m,
        "uphill_effort_min": max(15, uphill_minutes),
        "downhill_eccentric_min": max(10, downhill_minutes),
        "hike_run_transition_reps": transitions,
        "guidance": (
            "Use incline treadmill, stairs, brisk power-hike blocks, and "
            "eccentric quad work to simulate mountain load on flat terrain."
        ),
    }


def low_freq_easy_vs_long_ratio(max_runs: Optional[int], trail_profile) -> float:
    """Easy-vs-long fraction: tighter for low-frequency road plans.

    At <= 3 runs/week on the road, the long run carries most of the week; a
    loose easy ceiling lets the single easy slot become a second long effort
    (long 14 km + "easy" 13 km for a 5K). Trail keeps the default — back-to-back
    long days are intentional there.
    """
    if trail_profile is None and max_runs is not None and max_runs <= 3:
        return LOW_FREQ_EASY_VS_LONG_RUN
    return MAX_EASY_VS_LONG_RUN


def generate_daily_workouts(
    week_number: int,
    total_km: float,
    distribution: Dict[str, int],
    target_distance: float,
    weeks: int,
    phase: str,
    is_recovery_week: bool,
    vdot: Optional[float] = None,
    pace_zones: Optional[Dict] = None,
    experience_level: str = "beginner",
    week_in_phase: int = 0,
    terrain: Optional[str] = None,
    trail_profile=None,
    max_runs: Optional[int] = None,
    prev_long_run_km: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Generate daily workouts for one week."""
    long_run_distance = long_run_calculator.calculate_long_run_distance(
        total_km,
        target_distance,
        weeks,
        week_number,
        phase,
        is_recovery_week,
        experience_level,
        trail_profile=trail_profile,
        training_terrain=terrain,
        long_run_pace_min_km=_long_run_pace_min_km(pace_zones),
        max_runs=max_runs,
        prev_long_run_km=prev_long_run_km,
    )
    quality_distances = long_run_calculator.calculate_quality_distances(
        total_km,
        phase,
        distribution,
        is_recovery_week,
        long_run_distance,
        target_distance,
        terrain=terrain,
        trail_profile=trail_profile,
    )
    quality_distances = apply_quality_caps(
        quality_distances,
        long_run_distance,
        target_distance,
        phase,
    )

    # Ease into build intensity: base quality is a deliberately light dose,
    # and jumping straight to the full build budget produced a ~90% week-
    # over-week leap in quality km (marathon: 4.0 -> 7.6). The first two
    # build weeks ramp at 75% / 90% of the computed budget; the min-dose
    # floor below still guarantees each session stays worth running.
    if phase == "build" and not is_recovery_week and week_in_phase in (0, 1):
        ramp = 0.75 if week_in_phase == 0 else 0.90
        quality_distances = {
            # Already-light sessions ARE the on-ramp: never ramp a dose below
            # its meaningful floor (which would get it demoted to easy and
            # strip the slot entirely — observed on 2-run/week plans).
            qtype: (
                round(dist * ramp, 1)
                if dist * ramp >= QUALITY_MIN_DOSE_KM.get(qtype, 0)
                else dist
            )
            for qtype, dist in quality_distances.items()
        }

    resolve_low_budget_quality(
        distribution,
        quality_distances,
        remaining_km=total_km - long_run_distance,
        long_run_distance=long_run_distance,
        target_distance=target_distance,
        phase=phase,
    )

    workout_types = workout_dist_mod.schedule_workout_types(
        distribution.copy(),
        phase,
        week_number,
        is_recovery_week,
    )

    remaining_km = total_km - long_run_distance
    quality_total = sum(quality_distances.values())
    easy_runs = sum(1 for wt in workout_types if wt == "easy")
    easy_distances = allocate_easy_distances(
        remaining_km,
        quality_total,
        long_run_distance,
        easy_runs,
        max_easy_abs_km=float("inf") if trail_profile is not None else MAX_EASY_RUN_KM,
        easy_vs_long_ratio=low_freq_easy_vs_long_ratio(max_runs, trail_profile),
    )

    easy_run_idx = 0
    quality_slot_counts: Dict[str, int] = {}
    workouts: List[Dict[str, Any]] = []

    for day in range(7):
        workout_type = workout_types[day]
        if workout_type is None:
            continue
        day_number = day + 1

        if workout_type == "easy":
            distance = (
                easy_distances[easy_run_idx]
                if easy_run_idx < len(easy_distances)
                else easy_distances[0]
            )
            easy_run_idx += 1
        elif workout_type == "long":
            distance = long_run_distance
        elif workout_type in ("tempo", "interval", "hill"):
            distance = quality_distances.get(workout_type, 0)
        else:
            distance = 0

        workout = build_workout_for_type(
            workout_type,
            day_number,
            distance,
            total_km,
            phase,
            pace_zones,
        )

        # The key-workout ceiling caps a *quality* session against the long run;
        # the long run itself (also overlaid) must not be clamped against its
        # own length, so only quality slots carry a ceiling.
        quality_ceiling = (
            long_run_distance * MAX_KEY_WORKOUT_VS_LONG_RUN
            if workout_type in ("tempo", "interval", "hill")
            else None
        )
        # Volume-carrier guard: when the week has no easy run, the long run is
        # the only flexible slot that can absorb the week's volume budget.
        # Overlaying a prescriptive key workout (e.g. a fast-finish long) pins
        # its distance, so ``fill_shortfall`` has nowhere to place the
        # remaining km. At low training frequencies (2 runs/week) a quality
        # session plus a pinned long run collapses build/peak weeks far below
        # their target — a 30 km/week runner can crater to ~12 km mid-plan.
        # Keep the long run flexible in that case; the week's dedicated quality
        # session still supplies the intensity.
        skip_overlay = workout_type == "long" and easy_runs == 0
        if not skip_overlay:
            # 0-based count of same-type quality slots already overlaid this
            # week: a second tempo/interval slot must rotate to a different
            # library session instead of duplicating the first.
            slot_index = quality_slot_counts.get(workout_type, 0)
            if workout_type in ("tempo", "interval", "hill"):
                quality_slot_counts[workout_type] = slot_index + 1
            overlay_key_workout(
                workout,
                workout_type,
                phase,
                target_distance,
                week_in_phase,
                terrain,
                pace_zones,
                trail_profile=trail_profile,
                max_distance=quality_ceiling,
                slot_index=slot_index,
            )

        workout["coaching_rationale"] = generate_coaching_note(
            workout_type,
            phase,
            week_number,
            target_distance,
            is_recovery_week,
            pace_zones=pace_zones,
        )
        workouts.append(workout)

    workout_builders.attach_strength_sessions(
        workouts,
        week_number,
        phase,
        experience_level=experience_level,
        target_distance=target_distance,
        trail_profile=trail_profile,
    )

    return workouts


def build_weekly_plan(
    week_number: int,
    total_km: float,
    target_distance: float,
    max_runs_per_week: int,
    weeks: int,
    vdot: Optional[float] = None,
    pace_zones: Optional[Dict] = None,
    experience_level: str = "beginner",
    terrain: Optional[str] = None,
    trail_profile=None,
    intensive_weekend_enabled: bool = False,
    prev_long_run_km: Optional[float] = None,
) -> Dict[str, Any]:
    """Generate a single week's training plan.

    ``intensive_weekend_enabled`` opts the plan into a trail Intensive
    Training Weekend on the final peak week (off by default — it's a
    distinctive, demanding block the runner chooses to activate).
    """
    phases = phase_calculator.calculate_phases(
        weeks,
        target_distance,
        trail_profile=trail_profile,
    )
    phase = phase_calculator.get_phase(week_number, phases)
    is_recovery = phase_calculator.is_recovery_week(week_number, phase, phases)

    week_in_phase = calculate_week_in_phase(week_number, phase, phases)

    distribution = workout_dist_mod.get_workout_distribution(
        total_km,
        max_runs_per_week,
        phase,
        is_recovery,
        week_number,
        phases,
        target_distance,
        terrain=terrain,
        trail_profile=trail_profile,
    )

    workouts = generate_daily_workouts(
        week_number,
        total_km,
        distribution,
        target_distance,
        weeks,
        phase,
        is_recovery,
        vdot=vdot,
        pace_zones=pace_zones,
        experience_level=experience_level,
        week_in_phase=week_in_phase,
        terrain=terrain,
        trail_profile=trail_profile,
        max_runs=max_runs_per_week,
        prev_long_run_km=prev_long_run_km,
    )

    intensive_weekend = None
    if intensive_weekend_enabled:
        intensive_weekend = apply_intensive_weekend(
            workouts,
            phase,
            week_number,
            phases,
            week_in_phase,
            total_km,
            target_distance,
            pace_zones,
            trail_profile,
            terrain,
        )

    easy_vs_long_ratio = low_freq_easy_vs_long_ratio(max_runs_per_week, trail_profile)
    actual_total_km = _scale_down(workouts, total_km, pace_zones=pace_zones)
    actual_total_km = _fill_shortfall(
        workouts,
        total_km,
        actual_total_km,
        target_distance,
        pace_zones=pace_zones,
        trail_profile=trail_profile,
        easy_vs_long_ratio=easy_vs_long_ratio,
    )
    actual_total_km = _enforce_long_run_ratio_cap(
        workouts,
        phase,
        training_terrain=terrain,
        trail_profile=trail_profile,
        pace_zones=pace_zones,
        max_runs=max_runs_per_week,
    )

    # Final word on the long run: clamp to the road time ceiling even after
    # shortfall-filling may have spilled volume back into it (audit E7).
    _enforce_long_run_time_cap(workouts, pace_zones, trail_profile=trail_profile)
    # ... and re-fit key quality sessions against the long run's final length,
    # which the ratio/time caps above may have shrunk since overlay time.
    _reclamp_quality_to_long_run(workouts)
    actual_total_km = round(sum(w.get("distance", 0) for w in workouts), 1)

    attach_duration_hints(workouts, pace_zones)

    is_valid, validation_message = validate_week_plan(
        workouts, actual_total_km, total_km, phase
    )

    training_tips = workout_builders.generate_training_tips(
        week_number,
        target_distance,
        trail_profile=trail_profile,
        training_terrain=terrain,
    )
    vertical_simulation = _vertical_simulation_targets(
        actual_total_km,
        phase,
        is_recovery,
        distribution,
        training_terrain=terrain,
        trail_profile=trail_profile,
    )
    attach_treadmill_prescriptions(
        workouts,
        vertical_simulation,
        trail_profile,
        terrain,
    )

    return {
        "week": week_number,
        "phase": phase,
        "is_recovery": is_recovery,
        "total_km": actual_total_km,
        "daily_workouts": workouts,
        "training_tips": training_tips,
        "vertical_simulation": vertical_simulation,
        "intensive_weekend": intensive_weekend,
        "validation": {"valid": is_valid, "message": validation_message},
        "strength_training": [
            w["strength_session"] for w in workouts if w.get("strength_session")
        ],
    }
