"""Weekly plan orchestration: assemble one week's daily workouts and metadata."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.domain.frequency import FrequencyComposer

from app.contexts.plan.generators.plan_validator import validate_week_plan
from app.contexts.plan.generators.weekly_plan_builder.backyard_week import (
    apply_backyard_week,
    weekend_budget_km,
)
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
    enforce_contract_long_run_cap as _enforce_contract_long_run_cap,
)
from app.contexts.plan.generators.workout_scaler import (
    enforce_long_run_progression_floor as _enforce_long_run_progression_floor,
)
from app.contexts.plan.generators.workout_scaler import (
    enforce_long_run_ratio_cap as _enforce_long_run_ratio_cap,
)
from app.contexts.plan.generators.workout_scaler import (
    enforce_long_run_share_cap as _enforce_long_run_share_cap,
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
from app.core.training.periodization import long_run_calculator, phase_calculator
from app.core.training.periodization import workout_distribution as workout_dist_mod
from app.core.training.periodization.quality_caps import (
    LOW_FREQ_EASY_VS_LONG_RUN,
    MAX_EASY_VS_LONG_RUN,
    QUALITY_MIN_DOSE_KM,
    volume_scaled_easy_cap,
)
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
from app.core.training.tuning import (
    MAX_KEY_WORKOUT_VS_LONG_RUN,
    QUALITY_PROGRESSION_MAX,
    QUALITY_PROGRESSION_STEP,
)
from app.core.training.workouts import workout_builders
from app.core.training.workouts.key_workout_library import (
    KeyWorkoutRotationState,
    overlay_key_workout,
)

logger = logging.getLogger(__name__)

# A week whose *fixed* slots (a prescriptive long run, the easy runs at their
# absolute cap, and the quality sessions) can only reach this fraction of the
# week's target must keep the long run flexible — otherwise the volume the
# builder cannot place is silently dropped and the week craters. See the
# volume-carrier guard in ``generate_daily_workouts``.
PINNED_LONG_RUN_FILL_FLOOR = 0.90


def _resizable_long_run_local(workouts: List[Dict[str, Any]]):
    """The week's long run, or ``None`` when it must not be resized.

    Mirrors ``workout_scaler._resizable_long_run``: a ``fixed_structure``
    long slot (a backyard loop simulation) is out of scope for budget passes.
    """
    from app.contexts.plan.generators.workout_scaler import _resizable_long_run

    return _resizable_long_run(workouts)


def _resize_long_run_growth(
    workout: Dict[str, Any], distance: float, pace_zones: Optional[Dict]
) -> None:
    """Resize the long run for the growth clamp via the shared resizer."""
    from app.contexts.plan.generators.workout_scaler import _resize_long_run

    _resize_long_run(workout, distance, pace_zones)


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


def _build_slot_labels(
    composer: "FrequencyComposer",
    phase: str,
    workout_types: List[Optional[str]],
) -> Dict[int, str]:
    """Map day indices to the composer slot labels for the PDF and UI."""
    from app.domain.frequency import SlotType

    _SLOT_TYPE_MAP = {
        "easy": SlotType.EASY,
        "long": SlotType.LONG,
        "medium_long": SlotType.MEDIUM_LONG,
        "recovery": SlotType.RECOVERY,
        "tempo": SlotType.QUALITY,
        "interval": SlotType.QUALITY,
        "hill": SlotType.QUALITY,
    }
    slots = list(composer.slots(phase))
    slot_cursor: Dict[SlotType, int] = {}
    labels: Dict[int, str] = {}
    for day_idx, wtype in enumerate(workout_types):
        if wtype is None:
            continue
        stype = _SLOT_TYPE_MAP.get(wtype)
        if stype is None:
            continue
        idx = slot_cursor.get(stype, 0)
        matching = [s for s in slots if s.slot_type == stype]
        if idx < len(matching) and matching[idx].label:
            labels[day_idx] = matching[idx].label
        slot_cursor[stype] = idx + 1
    return labels


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
    rotation_state: Optional[KeyWorkoutRotationState] = None,
    composer: Optional[FrequencyComposer] = None,
) -> List[Dict[str, Any]]:
    """Generate daily workouts for one week.

    ``rotation_state`` is the plan-level key-workout memory (one instance per
    generated plan): it powers the no-repeat selection window, the per-plan
    use cap, and the peak-vs-build interval work-set invariant. ``None`` (the
    default, kept for direct callers/tests) degrades to stateless selection.
    """
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
        composer=composer,
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
    # In-phase progressive overload: within build and peak, the quality-day
    # budget grows a step per week in the phase, so rep counts derived from
    # the budget rise monotonically instead of oscillating with rotation.
    # Applied before the caps below (which bound it) and compounding with the
    # 2-week build on-ramp further down (which still eases weeks 0-1 in).
    if phase in ("build", "peak") and not is_recovery_week and week_in_phase > 0:
        progression = min(
            QUALITY_PROGRESSION_MAX,
            1.0 + QUALITY_PROGRESSION_STEP * week_in_phase,
        )
        quality_distances = {
            qtype: round(dist * progression, 1)
            for qtype, dist in quality_distances.items()
        }

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

    if composer is not None:
        from app.core.training.periodization.week_scheduler import (
            schedule_from_composer,
        )

        quality_types = {
            k: distribution.get(k, 0) for k in ("tempo", "interval", "hill")
        }
        workout_types = schedule_from_composer(
            composer, phase, quality_types, is_recovery_week
        )
    else:
        workout_types = workout_dist_mod.schedule_workout_types(
            distribution.copy(),
            phase,
            week_number,
            is_recovery_week,
        )

    # Medium-long distance: sized from the composer's volume percentage.
    medium_long_distance = 0.0
    if composer is not None and any(wt == "medium_long" for wt in workout_types):
        from app.domain.frequency import SlotType

        for slot in composer.slots(phase):
            if slot.slot_type == SlotType.MEDIUM_LONG:
                medium_long_distance = round(total_km * slot.volume_pct, 1)
                break

    remaining_km = total_km - long_run_distance - medium_long_distance
    quality_total = sum(quality_distances.values())
    easy_runs = sum(1 for wt in workout_types if wt == "easy")
    easy_distances = allocate_easy_distances(
        remaining_km,
        quality_total,
        long_run_distance,
        easy_runs,
        max_easy_abs_km=float("inf")
        if trail_profile is not None
        else volume_scaled_easy_cap(total_km),
        easy_vs_long_ratio=low_freq_easy_vs_long_ratio(max_runs, trail_profile),
    )

    slot_labels = _build_slot_labels(composer, phase, workout_types) if composer else {}

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
                else (easy_distances[0] if easy_distances else 0)
            )
            easy_run_idx += 1
        elif workout_type == "long":
            distance = long_run_distance
        elif workout_type == "medium_long":
            distance = medium_long_distance
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
        if day in slot_labels:
            workout["slot_label"] = slot_labels[day]

        # The key-workout ceiling caps a *quality* session against the long run;
        # the long run itself (also overlaid) must not be clamped against its
        # own length, so only quality slots carry a ceiling.
        quality_ceiling = (
            long_run_distance * MAX_KEY_WORKOUT_VS_LONG_RUN
            if workout_type in ("tempo", "interval", "hill")
            else None
        )
        # Volume-carrier guard: the long run is the only slot left to absorb the
        # week's volume once the easy runs sit at their cap, and
        # ``fill_shortfall`` cannot expand a *prescriptive* long run at all
        # (``is_prescriptive`` is true for anything carrying a ``key_workout_id``).
        # Overlaying a key long workout therefore pins the week's largest flexible
        # slot, and whatever the easy runs cannot hold is silently dropped: at
        # 2-3 runs/week a quality session plus a pinned long run collapses
        # build/peak weeks far below their target — measured at 49 km against a
        # 64 km target, and a 30 km/week runner cratering to ~12 km mid-plan.
        # Keep the long run flexible whenever pinning it would leave the week
        # materially short of its target; the week's dedicated quality session
        # still supplies the intensity. A long-run overlay is only affordable
        # when the easy runs plus the pinned long run can still reach the target.
        pinned_capacity = (
            long_run_distance
            + easy_runs * volume_scaled_easy_cap(total_km)
            + quality_total
        )
        skip_overlay = workout_type == "long" and (
            easy_runs == 0 or pinned_capacity < total_km * PINNED_LONG_RUN_FILL_FLOOR
        )
        # Low-frequency quality slots: at ≤ 2 runs/week the week is one long
        # run plus ONE quality session, and that session is the only carrier
        # of both intensity and volume besides the long run. A key-workout
        # overlay installs a fixed library prescription (e.g. "2 km + 1 km +
        # 1 km + floats" → 8.2 km) whose price cannot grow with the weekly
        # budget — ``rebuild_key_workout`` snaps the distance back to the
        # prescription's own step total — so a 48 km target delivered 20.4 km:
        # tempo pinned at 8.2, long run crushed to the 0.60 share of the
        # remainder. The formulaic quality builders scale with weekly volume,
        # so at ≤ 2 runs the slot keeps the formulaic session and the overlay
        # is skipped. 3-run weeks keep overlays: their easy slot absorbs the
        # drift the fixed prescription leaves behind.
        if (
            max_runs is not None
            and max_runs <= 2
            and workout_type
            in (
                "tempo",
                "interval",
                "hill",
            )
        ):
            skip_overlay = True
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
                weekly_km=total_km,
                state=rotation_state,
                week_number=week_number,
            )

        workout["coaching_rationale"] = workout.get(
            "key_workout_rationale"
        ) or generate_coaching_note(
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
        rotation_state=rotation_state,
        composer=composer,
    )

    backyard = None
    if backyard_profile is not None:
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
        backyard = weekly_backyard_focus(
            phase, is_recovery, backyard_profile, simulation
        )
        backyard["installed"] = installed

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
        experience_level=experience_level,
        max_runs=max_runs_per_week,
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

    # Final long-run contract, in increasing authority: restore the cross-week
    # progression shape first, then re-assert the two ceilings the passes above
    # cannot guarantee on their own — and which ``reclamp_quality_to_long_run``
    # has just perturbed by shrinking the quality day. Road only; a trail plan's
    # long days are governed by the bracket cap and the ITW. The share cap runs
    # after every growth/fill pass below, so it stays the true last word on the
    # long run's share of its own week.
    if trail_profile is None and backyard_profile is None:
        if not is_recovery:
            _enforce_long_run_progression_floor(
                workouts, prev_long_run_km, pace_zones=pace_zones
            )
        _enforce_contract_long_run_cap(
            workouts,
            target_distance,
            experience_level,
            pace_zones=pace_zones,
            max_runs=max_runs_per_week,
        )

        # Long-run growth clamp (audit G3): ``fill_shortfall`` and the passes
        # above can grow the long run past the cross-week growth ceiling
        # (max(+18%, +3 km)) that ``calculate_long_run_distance`` enforced at
        # sizing time — a +31-41% single-step jump in the longest, highest-risk
        # session. Clamp before the low-frequency fill below, so the fill's
        # growth is bounded by the same ceiling instead of being cut by it
        # after the fact.
        growth_ceiling_km = None
        if not is_recovery and prev_long_run_km:
            from app.core.training.tuning import (
                LONG_RUN_GROWTH_ABS_KM,
                LONG_RUN_GROWTH_PCT,
            )

            growth_ceiling_km = max(
                prev_long_run_km * LONG_RUN_GROWTH_PCT,
                prev_long_run_km + LONG_RUN_GROWTH_ABS_KM,
            )
            growth_long = _resizable_long_run_local(workouts)
            if growth_long is not None:
                if (growth_long.get("distance") or 0) > growth_ceiling_km + 0.05:
                    _resize_long_run_growth(growth_long, growth_ceiling_km, pace_zones)

        # Low-frequency final fill: after every cap has had its word, a ≤2-run
        # week may still sit below its target because the single quality
        # partner is physiologically capped (Daniels work-share, per-distance
        # caps) and nothing re-grows the long run *after* the caps spoke. The
        # long run takes what the capped partner leaves of the target, bounded
        # by its contracted cap and — so the fill never manufactures the very
        # session-spike the growth clamp exists to prevent — by the cross-week
        # growth ceiling when one applies. The plan-level 10% pass still bounds
        # the week-over-week total.
        if max_runs_per_week is not None and max_runs_per_week <= 2 and not is_recovery:
            from app.contexts.plan.generators.workout_scaler import (
                _floor_to_100m as _floor100,
            )
            from app.contexts.plan.generators.workout_scaler import (
                _resizable_long_run as _resizable_long,
            )
            from app.contexts.plan.generators.workout_scaler import (
                _resize_long_run as _resize_lr,
            )

            fill_long = _resizable_long(workouts)
            if fill_long is not None:
                rest_km = round(
                    sum(
                        w.get("distance", 0) or 0
                        for w in workouts
                        if w.get("type") not in ("rest", "recovery", "long")
                    ),
                    1,
                )
                volume_bound = _floor100(
                    long_run_calculator.long_run_cap(
                        target_distance,
                        experience_level,
                        weekly_km=total_km,
                        max_runs=max_runs_per_week,
                    )
                )
                # The share ceiling still rules: the grown pair must satisfy
                # long / (long + rest) <= the frequency ceiling, i.e.
                # long <= ceiling * rest / (1 - ceiling).
                share_ceiling = long_run_calculator.get_weekly_long_run_ratio_cap(
                    phase, max_runs=max_runs_per_week
                )
                share_bound = (
                    _floor100(share_ceiling * rest_km / (1 - share_ceiling))
                    if share_ceiling < 1
                    else rest_km
                )
                desired = min(total_km - rest_km, volume_bound, share_bound)
                if growth_ceiling_km is not None:
                    desired = min(desired, growth_ceiling_km)
                current = fill_long.get("distance") or 0
                if desired > current + 0.1:
                    _resize_lr(fill_long, desired, pace_zones)
                    # The quality day must stay subordinate to the grown long
                    # run (its phys caps were computed against the old value).
                    _reclamp_quality_to_long_run(workouts)

            # The transition into build at 2 runs swaps the easy slot for a
            # quality slot, and the formulaic quality session is sized from the
            # week's (reachable-capped) target through the Daniels work-share —
            # which is computed against the week's *volume*. A collapsed week
            # therefore permits only a tiny interval, which keeps the week
            # collapsed: a self-reinforcing fixed point (measured: 11.4 km in a
            # 16.5 km week at the base→build boundary). Grow the single
            # formulaic quality slot toward its physiological cap computed at
            # the week's TARGET volume, breaking the loop; the plan-level 10%
            # pass still bounds the weekly total.
            from app.core.training.tuning import (
                MAX_WORK_ABS_KM_BY_ZONE,
                MAX_WORK_SHARE_BY_ZONE,
                WORK_ZONE_GROUP,
            )

            for qw in workouts:
                if qw.get("type") not in ("tempo", "interval", "hill"):
                    continue
                if qw.get("key_workout_id") or qw.get("fixed_structure"):
                    continue
                qd = qw.get("distance") or 0
                if qd <= 0:
                    continue

                work_m = sum(
                    (s.get("distance_m") or 0) * s.get("repeat", 1)
                    for s in (qw.get("steps") or [])
                    if s.get("kind") in ("run", "walk", "strides")
                    and s.get("pace_zone") in WORK_ZONE_GROUP
                )
                work_km = work_m / 1000.0
                zone = next(
                    (
                        s.get("pace_zone")
                        for s in (qw.get("steps") or [])
                        if s.get("pace_zone") in WORK_ZONE_GROUP
                    ),
                    None,
                )
                if zone is None or work_km <= 0:
                    continue
                group = WORK_ZONE_GROUP[zone]
                work_cap_target = min(
                    MAX_WORK_ABS_KM_BY_ZONE.get(group, 99.0),
                    MAX_WORK_SHARE_BY_ZONE.get(group, 1.0) * total_km,
                )
                if work_km >= work_cap_target - 0.05:
                    continue
                # Scale the session up so its work set reaches the cap the
                # target volume allows; bookends grow proportionally.
                scale = min(1.4, work_cap_target / work_km)
                from app.contexts.plan.generators.workout_scaler import set_distance

                set_distance(qw, round(qd * scale, 1), pace_zones)

        # The share cap is the true last word: it runs after the progression
        # floor, the contract cap, the growth clamp and the low-frequency fill,
        # so no pass above can leave the long run over its share of the week.
        _enforce_long_run_share_cap(
            workouts,
            phase,
            terrain,
            max_runs=max_runs_per_week,
            pace_zones=pace_zones,
            target_km=total_km,
            target_distance=target_distance,
            experience_level=experience_level,
        )
        # ... and the contract cap re-asserts itself after that: the reclamps
        # above shrink the quality day, which lowers the week's delivered
        # volume and with it the volume-aware cap the contract solves for —
        # a long run legal at the pre-clamp volume can sit past the cap at
        # the final one (measured: 12.9 km against a 12.2 cap on a 5K week).
        # It runs after the final reclamp (so no later pass shrinks the week
        # under it). At ≤ 3 runs it never takes the long run below the previous
        # loading week's minus the material-drop tolerance: there the volume
        # cap and the cross-week progression floor genuinely conflict (a 2-run
        # week's volume swings with its single partner), and a 10 %+ single-
        # step long-run drop is the worse fault. At 4+ runs the volume cap
        # rules — protecting the long there let loading-week longs ratchet
        # past the published band (a 19 km long run for a 10K).
        contract_floor_km = (
            round(prev_long_run_km * 0.90, 1)
            if (
                not is_recovery
                and prev_long_run_km
                and max_runs_per_week is not None
                and max_runs_per_week <= 3
            )
            else None
        )
        _reclamp_quality_to_long_run(workouts)
        _enforce_contract_long_run_cap(
            workouts,
            target_distance,
            experience_level,
            pace_zones=pace_zones,
            max_runs=max_runs_per_week,
            floor_km=contract_floor_km,
        )
        # The contract pass may have shrunk the long run below what the
        # quality sessions were fitted against — refit them so the step list
        # never promises more than the card says.
        _reclamp_quality_to_long_run(workouts)
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
