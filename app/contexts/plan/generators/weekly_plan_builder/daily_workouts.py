"""The week's day cards: size each kind of session, place it, then build it.

``generate_daily_workouts`` answers three questions in order — *how much* of
the week each kind of session gets (long run, quality, medium-long, easy),
*which day* each one lands on, and *what* the session on that day actually is
(the formulaic builder, optionally overlaid with a key workout from the
library). Fitting the result to the week's budget is the orchestrator's job.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.contexts.plan.generators.weekly_plan_builder.backyard_week import (
    SECOND_DAY_INDEX,
)
from app.contexts.plan.generators.weekly_plan_builder.budget import (
    allocate_easy_distances,
    apply_quality_caps,
    build_workout_for_type,
    resolve_low_budget_quality,
)
from app.contexts.plan.generators.workout_scaler import long_run_pace_min_km
from app.core.coaching.coaching_notes_generator import generate_coaching_note
from app.core.training.custom_plan import (
    CUSTOM_PHASES,
    CustomRotation,
    SlotKind,
    quality_assignment,
    rewrite_distribution,
    session_type,
)
from app.core.training.periodization import long_run_calculator
from app.core.training.periodization import workout_distribution as workout_dist_mod
from app.core.training.periodization.quality_caps import (
    LOW_FREQ_EASY_VS_LONG_RUN,
    MAX_EASY_VS_LONG_RUN,
    QUALITY_MIN_DOSE_KM,
    trail_easy_cap,
    volume_scaled_easy_cap,
)
from app.core.training.periodization.week_scheduler import schedule_from_composer
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
from app.core.training.workouts.key_workout_library.selection import (
    fits_key_workout_budget,
)
from app.core.training.workouts.long_run_shapes import build_shaped_long_run
from app.domain.frequency import FrequencyComposer, SlotType

QUALITY_TYPES = ("tempo", "interval", "hill")

# A week whose *fixed* slots (a prescriptive long run, the easy runs at their
# absolute cap, and the quality sessions) can only reach this fraction of the
# week's target must keep the long run flexible — otherwise the volume the
# builder cannot place is silently dropped and the week craters. See the
# volume-carrier guard in ``generate_daily_workouts``.
PINNED_LONG_RUN_FILL_FLOOR = 0.90

_SLOT_TYPE_FOR_WORKOUT = {
    "easy": SlotType.EASY,
    "long": SlotType.LONG,
    "medium_long": SlotType.MEDIUM_LONG,
    "recovery": SlotType.RECOVERY,
    "tempo": SlotType.QUALITY,
    "interval": SlotType.QUALITY,
    "hill": SlotType.QUALITY,
}


def _build_slot_labels(
    composer: FrequencyComposer,
    phase: str,
    workout_types: List[Optional[str]],
) -> Dict[int, str]:
    """Map day indices to the composer slot labels for the PDF and UI."""
    slots = list(composer.slots(phase))
    slot_cursor: Dict[SlotType, int] = {}
    labels: Dict[int, str] = {}
    for day_idx, wtype in enumerate(workout_types):
        if wtype is None:
            continue
        stype = _SLOT_TYPE_FOR_WORKOUT.get(wtype)
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


def _quality_budgets(
    total_km: float,
    phase: str,
    distribution: Dict[str, int],
    is_recovery_week: bool,
    long_run_distance: float,
    target_distance: float,
    week_in_phase: int,
    terrain: Optional[str],
    trail_profile,
) -> Dict[str, float]:
    """Each quality type's km budget for the week, after overload and caps."""
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
    # floor still guarantees each session stays worth running.
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
    return quality_distances


def _schedule_week(
    composer: Optional[FrequencyComposer],
    distribution: Dict[str, int],
    phase: str,
    week_number: int,
    is_recovery_week: bool,
    is_backyard: bool,
) -> List[Optional[str]]:
    """The workout type on each of the seven days (``None`` for a day off)."""
    if composer is not None:
        quality_types = {k: distribution.get(k, 0) for k in QUALITY_TYPES}
        return schedule_from_composer(composer, phase, quality_types, is_recovery_week)
    return workout_dist_mod.schedule_workout_types(
        distribution.copy(),
        phase,
        week_number,
        is_recovery_week,
        reserved_days=frozenset({SECOND_DAY_INDEX}) if is_backyard else frozenset(),
    )


def _medium_long_distance(
    composer: Optional[FrequencyComposer],
    phase: str,
    workout_types: List[Optional[str]],
    total_km: float,
) -> float:
    """Medium-long distance: sized from the composer's volume percentage."""
    if composer is None or not any(wt == "medium_long" for wt in workout_types):
        return 0.0
    for slot in composer.slots(phase):
        if slot.slot_type == SlotType.MEDIUM_LONG:
            return round(total_km * slot.volume_pct, 1)
    return 0.0


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
    is_backyard: bool = False,
    custom_rotation: Optional[CustomRotation] = None,
) -> List[Dict[str, Any]]:
    """Generate daily workouts for one week.

    ``custom_rotation`` makes this a custom plan's week: the runner's chosen
    sessions fill the long run and the build/peak quality days (see
    ``app.core.training.custom_plan``). The budgets, caps and placement are
    unchanged — a choice decides *what* a day is, never how much of it.

    ``is_backyard`` keeps weekday easy runs uncapped: backyard volume is bounded
    by the goal's own weekly min/max, and its highest-volume runners carry it in
    weekday easy runs that the trail ceiling would clip.

    ``rotation_state`` is the plan-level key-workout memory (one instance per
    generated plan): it powers the no-repeat selection window, the per-plan
    use cap, and the peak-vs-build interval work-set invariant. ``None`` (the
    default, kept for direct callers/tests) degrades to stateless selection.
    """
    # How much: the long run first, because every other budget is sized
    # against it.
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
        long_run_pace_min_km=long_run_pace_min_km(pace_zones),
        max_runs=max_runs,
        prev_long_run_km=prev_long_run_km,
        composer=composer,
    )
    # A custom week types its quality days by the runner's picks *before* the
    # budgets, which are sized per type.
    assignment = (
        quality_assignment(custom_rotation, phase, distribution)
        if custom_rotation is not None
        else None
    )
    if assignment:
        rewritten = rewrite_distribution(distribution, assignment)
        distribution.clear()
        distribution.update(rewritten)

    quality_distances = _quality_budgets(
        total_km,
        phase,
        distribution,
        is_recovery_week,
        long_run_distance,
        target_distance,
        week_in_phase,
        terrain,
        trail_profile,
    )
    resolve_low_budget_quality(
        distribution,
        quality_distances,
        remaining_km=total_km - long_run_distance,
        long_run_distance=long_run_distance,
        target_distance=target_distance,
        phase=phase,
    )

    # Which day.
    workout_types = _schedule_week(
        composer, distribution, phase, week_number, is_recovery_week, is_backyard
    )

    medium_long_distance = _medium_long_distance(
        composer, phase, workout_types, total_km
    )
    remaining_km = total_km - long_run_distance - medium_long_distance
    quality_total = sum(quality_distances.values())
    easy_runs = sum(1 for wt in workout_types if wt == "easy")
    if is_backyard:
        easy_abs_cap = float("inf")
    elif trail_profile is not None:
        easy_abs_cap = trail_easy_cap(total_km)
    else:
        easy_abs_cap = volume_scaled_easy_cap(total_km)
    easy_distances = allocate_easy_distances(
        remaining_km,
        quality_total,
        long_run_distance,
        easy_runs,
        max_easy_abs_km=easy_abs_cap,
        easy_vs_long_ratio=low_freq_easy_vs_long_ratio(max_runs, trail_profile),
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
    pinned_easy_cap = volume_scaled_easy_cap(total_km) if is_backyard else easy_abs_cap
    pinned_capacity = long_run_distance + easy_runs * pinned_easy_cap + quality_total
    long_run_must_stay_flexible = (
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
    quality_stays_formulaic = max_runs is not None and max_runs <= 2

    # A custom plan's long run is a shape laid over the day's distance, so it
    # stays flexible and the volume guard above has nothing to refuse.
    long_shape_id = _custom_long_shape(
        custom_rotation, phase, is_recovery_week, workout_types
    )
    pending_picks = list(assignment or [])

    # What: build each day's session.
    slot_labels = _build_slot_labels(composer, phase, workout_types) if composer else {}
    easy_run_idx = 0
    quality_slot_counts: Dict[str, int] = {}
    workouts: List[Dict[str, Any]] = []

    for day in range(7):
        workout_type = workout_types[day]
        if workout_type is None:
            continue
        is_quality = workout_type in QUALITY_TYPES

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
        elif is_quality:
            distance = quality_distances.get(workout_type, 0)
        else:
            distance = 0

        workout = build_workout_for_type(
            workout_type,
            day + 1,
            distance,
            total_km,
            phase,
            pace_zones,
        )
        if workout_type == "long" and long_shape_id:
            workout = (
                build_shaped_long_run(long_shape_id, day + 1, distance, pace_zones)
                or workout
            )
        if day in slot_labels:
            workout["slot_label"] = slot_labels[day]

        skip_overlay = (
            workout_type == "long"
            and (long_run_must_stay_flexible or bool(long_shape_id))
        ) or (is_quality and quality_stays_formulaic)
        pick = _take_pick(pending_picks, workout_type) if is_quality else None
        if pick is not None and custom_rotation is not None:
            slot, menu = pick
            turn = next(
                (
                    i
                    for i, wid in enumerate(menu)
                    if session_type(wid) == workout_type
                    and fits_key_workout_budget(wid, workout.get("distance"))
                ),
                None,
            )
            chosen = menu[turn] if turn is not None else None
            custom_rotation.advance(phase, slot, 1 if turn is None else turn + 1)
            if chosen is None:
                # Every choice for this cell needs more room than the day has;
                # the engine's own session runs instead, and the card says why.
                workout["custom_deferral_code"] = "quality_budget"
            else:
                overlay_key_workout(
                    workout,
                    workout_type,
                    phase,
                    target_distance,
                    week_in_phase,
                    terrain,
                    pace_zones,
                    trail_profile=trail_profile,
                    force_id=chosen,
                    max_distance=long_run_distance * MAX_KEY_WORKOUT_VS_LONG_RUN,
                    weekly_km=total_km,
                    state=rotation_state,
                    week_number=week_number,
                )
            skip_overlay = True
        if not skip_overlay:
            # 0-based count of same-type quality slots already overlaid this
            # week: a second tempo/interval slot must rotate to a different
            # library session instead of duplicating the first.
            slot_index = quality_slot_counts.get(workout_type, 0)
            if is_quality:
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
                # The key-workout ceiling caps a *quality* session against the
                # long run; the long run itself (also overlaid) must not be
                # clamped against its own length, so only quality slots carry
                # a ceiling.
                max_distance=(
                    long_run_distance * MAX_KEY_WORKOUT_VS_LONG_RUN
                    if is_quality
                    else None
                ),
                slot_index=slot_index,
                weekly_km=total_km,
                state=rotation_state,
                week_number=week_number,
            )

        workout["coaching_rationale"] = (
            workout.get("key_workout_rationale") or workout.get("coaching_rationale")
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
        custom=(
            (
                custom_rotation.spec.strength.sessions_per_week,
                custom_rotation.spec.strength.template,
            )
            if custom_rotation is not None
            else None
        ),
    )

    return workouts


def _custom_long_shape(
    rotation: Optional[CustomRotation],
    phase: str,
    is_recovery_week: bool,
    workout_types: List[Optional[str]],
) -> Optional[str]:
    """The shape this week's long run takes, or ``None`` for the engine's own.

    Recovery weeks and the taper keep the plain long run: a deload is not the
    week to rehearse a fast finish.
    """
    if rotation is None or phase not in CUSTOM_PHASES or is_recovery_week:
        return None
    if "long" not in workout_types:
        return None
    menu = rotation.ordered(phase, SlotKind.LONG)
    if not menu:
        return None
    rotation.advance(phase, SlotKind.LONG)
    return menu[0]


def _take_pick(
    pending: List[Tuple[SlotKind, List[str]]], workout_type: str
) -> Optional[Tuple[SlotKind, List[str]]]:
    """Claim the runner's pick for a quality day of ``workout_type``.

    ``rewrite_distribution`` typed the days from the picks, so a day normally
    finds its own; a day the low-budget pass re-typed falls back to the next
    pick in order.
    """
    for i, (slot, menu) in enumerate(pending):
        if menu and session_type(menu[0]) == workout_type:
            return pending.pop(i)
    return pending.pop(0) if pending else None
