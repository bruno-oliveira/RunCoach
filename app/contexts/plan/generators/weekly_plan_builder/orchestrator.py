"""Weekly plan orchestration: assemble one week's daily workouts and metadata.

``build_weekly_plan`` reads top to bottom as the life of a week:

1. **Place** it in the plan: phase, deload or not, how far into the phase,
   and how many sessions of each kind it carries.
2. **Build** the day cards (``daily_workouts``).
3. **Reshape** the weekend where the plan type owns it: a backyard loop
   simulation (``backyard_week``) or a trail Intensive Training Weekend
   (``intensive_weekend``).
4. **Fit** the cards to the week's budget (``workout_scaler``).
5. **Settle** the long run's contract (``long_run_contract``) — road only.
6. **Describe** the finished week: totals, validation verdict, tips.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.plan_validator import validate_week_plan
from app.contexts.plan.generators.weekly_plan_builder.backyard_week import (
    apply_backyard_week,
    weekend_budget_km,
)
from app.contexts.plan.generators.weekly_plan_builder.budget import (
    attach_duration_hints,
)
from app.contexts.plan.generators.weekly_plan_builder.daily_workouts import (
    generate_daily_workouts,
    low_freq_easy_vs_long_ratio,
)
from app.contexts.plan.generators.weekly_plan_builder.intensive_weekend import (
    apply_intensive_weekend,
)
from app.contexts.plan.generators.weekly_plan_builder.long_run_contract import (
    settle_road_long_run,
)
from app.contexts.plan.generators.workout_scaler import (
    enforce_long_run_ratio_cap,
    enforce_long_run_time_cap,
    fill_shortfall,
    reclamp_quality_to_long_run,
    scale_down,
)
from app.core.training.periodization import phase_calculator
from app.core.training.periodization import workout_distribution as workout_dist_mod
from app.core.training.periodization.training_constants import (
    calculate_week_in_phase,
    workouts_training_km,
)
from app.core.training.profiles.backyard_simulation import (
    fit_simulation_to_week,
    weekly_backyard_focus,
)
from app.core.training.profiles.vertical_simulation import (
    attach_treadmill_prescriptions,
)
from app.core.training.workouts import workout_builders
from app.core.training.workouts.key_workout_library import KeyWorkoutRotationState
from app.domain.frequency import FrequencyComposer

logger = logging.getLogger(__name__)


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


def _install_backyard_week(
    workouts: List[Dict[str, Any]],
    *,
    backyard_profile,
    backyard_schedule: Optional[Dict[int, Any]],
    week_number: int,
    phase: str,
    is_recovery: bool,
    week_in_phase: int,
    total_km: float,
    pace_zones: Optional[Dict],
    max_runs_per_week: int,
) -> Dict[str, Any]:
    """Turn the week into a backyard week; returns its ``backyard`` summary.

    The ladder decides whether this week carries a loop simulation, and the
    week's own volume gets the final say on how big it is.
    """
    scheduled = (backyard_schedule or {}).get(week_number)
    # The simulation takes the long run's slot, so the long run the
    # scheduler already sized is both the session it replaces and the
    # floor it must not fall below.
    displaced_long_km = max(
        (w.get("distance") or 0 for w in workouts if w.get("type") == "long"),
        default=0.0,
    )
    # The weekend and the rest of the week come out of one budget. Sized
    # against the whole week at a 70 % share, the simulation crowded the
    # easy runs out entirely on marginal plans — a 40 km week reached 44 km
    # with two 0.0 km "easy" cards left behind and a 23 % jump. Sized
    # against what is left after everything else has taken its *floor*, the
    # weekend is funded from the week's slack instead: the midweek work
    # keeps a real distance and the weekend still gets its room.
    other_floor_km = weekend_budget_km(workouts)
    simulation_budget = max(0.0, total_km - other_floor_km)
    simulation = (
        fit_simulation_to_week(scheduled, simulation_budget, displaced_long_km)
        if scheduled is not None and not is_recovery
        else None
    )
    installed = apply_backyard_week(
        workouts,
        phase=phase,
        is_recovery=is_recovery,
        week_in_phase=week_in_phase,
        total_km=total_km,
        profile=backyard_profile,
        simulation=simulation,
        pace_zones=pace_zones,
        max_runs=max_runs_per_week,
    )
    backyard = weekly_backyard_focus(phase, is_recovery, backyard_profile, simulation)
    backyard["installed"] = installed
    return backyard


def _fit_to_budget(
    workouts: List[Dict[str, Any]],
    *,
    total_km: float,
    phase: str,
    terrain: Optional[str],
    target_distance: float,
    experience_level: str,
    max_runs_per_week: int,
    trail_profile,
    is_backyard: bool,
    pace_zones: Optional[Dict],
) -> None:
    """Scale the cards onto the week's budget, then cap the long run (in place)."""
    scaled_km = scale_down(workouts, total_km, pace_zones=pace_zones)
    fill_shortfall(
        workouts,
        total_km,
        scaled_km,
        target_distance,
        pace_zones=pace_zones,
        trail_profile=trail_profile,
        easy_vs_long_ratio=low_freq_easy_vs_long_ratio(
            max_runs_per_week, trail_profile
        ),
        experience_level=experience_level,
        max_runs=max_runs_per_week,
        is_backyard=is_backyard,
    )
    enforce_long_run_ratio_cap(
        workouts,
        phase,
        training_terrain=terrain,
        trail_profile=trail_profile,
        pace_zones=pace_zones,
        max_runs=max_runs_per_week,
    )

    # Final word on the long run: clamp to the road time ceiling even after
    # shortfall-filling may have spilled volume back into it (audit E7).
    enforce_long_run_time_cap(workouts, pace_zones, trail_profile=trail_profile)
    # ... and re-fit key quality sessions against the long run's final length,
    # which the ratio/time caps above may have shrunk since overlay time.
    reclamp_quality_to_long_run(workouts)


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
    rotation_state: Optional[KeyWorkoutRotationState] = None,
    backyard_profile=None,
    backyard_schedule: Optional[Dict[int, Any]] = None,
    composer: Optional[FrequencyComposer] = None,
) -> Dict[str, Any]:
    """Generate a single week's training plan.

    ``intensive_weekend_enabled`` opts the plan into a trail Intensive
    Training Weekend on the final peak week (off by default — it's a
    distinctive, demanding block the runner chooses to activate).

    ``rotation_state`` is the plan-level key-workout memory shared across the
    weeks of one plan (see :func:`generate_daily_workouts`).

    ``backyard_profile`` + ``backyard_schedule`` turn the week into a backyard
    week: the ladder decides whether this week carries a loop simulation, and
    the week's own volume gets the final say on how big it is.
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
        composer=composer,
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
        is_backyard=backyard_profile is not None,
        rotation_state=rotation_state,
        composer=composer,
    )

    backyard = None
    if backyard_profile is not None:
        backyard = _install_backyard_week(
            workouts,
            backyard_profile=backyard_profile,
            backyard_schedule=backyard_schedule,
            week_number=week_number,
            phase=phase,
            is_recovery=is_recovery,
            week_in_phase=week_in_phase,
            total_km=total_km,
            pace_zones=pace_zones,
            max_runs_per_week=max_runs_per_week,
        )

    intensive_weekend = None
    # A backyard plan already reshapes its own weekend; an ITW on top would
    # put a threshold session in front of a loop simulation.
    if intensive_weekend_enabled and backyard_profile is None:
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

    _fit_to_budget(
        workouts,
        total_km=total_km,
        phase=phase,
        terrain=terrain,
        target_distance=target_distance,
        experience_level=experience_level,
        max_runs_per_week=max_runs_per_week,
        trail_profile=trail_profile,
        is_backyard=backyard_profile is not None,
        pace_zones=pace_zones,
    )
    if trail_profile is None and backyard_profile is None:
        settle_road_long_run(
            workouts,
            phase=phase,
            terrain=terrain,
            target_distance=target_distance,
            total_km=total_km,
            experience_level=experience_level,
            max_runs_per_week=max_runs_per_week,
            is_recovery=is_recovery,
            prev_long_run_km=prev_long_run_km,
            pace_zones=pace_zones,
        )
    actual_total_km = round(sum(w.get("distance", 0) for w in workouts), 1)

    attach_duration_hints(workouts, pace_zones)

    is_valid, validation_message = validate_week_plan(
        workouts, actual_total_km, total_km, phase
    )
    # This verdict is a *model-consistency* signal, not a plan-quality one: the
    # builder deliberately drops volume it cannot place inside the per-run caps
    # (see ``workout_scaler.fill_shortfall``), so a week can land under the
    # volume the periodisation model asked for while still being a sound,
    # runnable week. It is therefore logged per week at DEBUG for diagnosis,
    # and the *material, plan-level* shortfall is reported once per plan by
    # ``plan_generator`` — otherwise a real regression would be lost in the
    # noise of an expected one.
    if not is_valid:
        logger.debug(
            "Week %s (%s): delivered %.1f km against a %.1f km target — %s",
            week_number,
            phase,
            actual_total_km,
            total_km,
            validation_message,
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
        # Derived from the workouts by the shared helper (not carried over
        # from the modelled target): a week dict always reports the volume
        # its own sessions sum to, so every reader of this field — persistence,
        # rendering, audits — agrees with the day cards underneath it.
        "training_km": workouts_training_km(workouts),
        "daily_workouts": workouts,
        "training_tips": training_tips,
        "vertical_simulation": vertical_simulation,
        "intensive_weekend": intensive_weekend,
        "backyard": backyard,
        "validation": {"valid": is_valid, "message": validation_message},
        "strength_training": [
            w["strength_session"] for w in workouts if w.get("strength_session")
        ],
    }
