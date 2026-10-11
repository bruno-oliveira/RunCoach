"""Training plan generator -- thin orchestrator.

``generate_plan`` reads top to bottom as the life of a plan:

1. **Refuse** inputs no sound plan can be built from (``engine_floors``).
2. **Resolve** what the plan is built with: pace zones, the running frequency
   the weekly budget can actually fill, and a mileage progression capped at
   what that frequency can carry.
3. **Build** each week (``weekly_plan_builder``), holding it to the ramp cap
   against the load the previous weeks *delivered* (``plan_passes.ramp_cap``).
4. **Smooth** the whole plan and close it on race day (``plan_passes``).
5. **Finalize**: recompute every derived field, report where the delivered
   plan fell short of the model, and fail loudly on an unrunnable week.

The math lives in ``core/training``; callers should import those modules
directly for low-level helpers. This class exposes only the orchestration.
"""

import logging
from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.beginner_plan_generator import BeginnerPlanGenerator
from app.contexts.plan.generators.engine_floors import enforce_engine_floors
from app.contexts.plan.generators.plan_finalizer import (
    finalize_plan,
    reconcile_card_distances,
    refresh_plan_fields,
)
from app.contexts.plan.generators.plan_passes import (
    enforce_weekly_ramp_cap,
    install_backyard_race_day,
    install_race_day,
    refill_trail_week,
    refresh_duration_hints,
    smooth_recovery_dips,
    smooth_taper,
    sweep_trivial_sessions,
    week_total_km,
)
from app.contexts.plan.generators.weekly_plan_builder import build_weekly_plan
from app.contexts.plan.generators.workout_scaler import reclamp_quality_to_long_run
from app.core.training.frequency import get_composer
from app.core.training.periodization import mileage_progression
from app.core.training.periodization.phase_calculator import calculate_phases
from app.core.training.periodization.strength_plan import derive_experience_level
from app.core.training.physiology.goal_pace_model import pin_goal_race_pace
from app.core.training.physiology.personal_easy_band import with_personal_easy_band
from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.core.training.profiles.backyard_profile import BackyardProfile
from app.core.training.profiles.backyard_simulation import build_simulation_schedule
from app.core.training.profiles.trail_profile import (
    TRAIL_SENTINEL_KM,
    TrailProfile,
    classify_trail,
)
from app.core.training.training_config import MIN_VIABLE_RUN_KM
from app.core.training.workouts.key_workout_library import KeyWorkoutRotationState
from app.exceptions import (
    PlanGenerationException,
    ZeroMileageUnsupportedException,
)

logger = logging.getLogger(__name__)

# Floor on running days: a real training week still wants a long run, a quality
# session, and an easy run, so frequency is never reduced below this.
MIN_RUNNING_DAYS = 3


def _viable_run_frequency(current_km: float, max_runs: int) -> int:
    """Reduce running frequency when the weekly budget can't fill every run.

    Keeps each run at or above :data:`MIN_VIABLE_RUN_KM` where possible, without
    ever dropping below :data:`MIN_RUNNING_DAYS`. Returns ``max_runs`` unchanged
    for any adequately-resourced plan.
    """
    runs = max_runs
    while runs > MIN_RUNNING_DAYS and current_km / runs < MIN_VIABLE_RUN_KM:
        runs -= 1
    return runs


# A delivered peak this far below the modelled target peak is worth a log line.
# Below it the gap is rounding and per-run cap interaction; above it the model
# is promising volume the week layout cannot hold at the requested frequency.
PEAK_TARGET_SHORTFALL_RATIO = 0.85


def _log_peak_shortfall(
    training_plan: List[Dict[str, Any]],
    weekly_progression: List[float],
) -> None:
    """Report when the delivered peak falls materially short of the target.

    The weekly builder drops volume it cannot place inside the per-run caps
    rather than inflating a run past its ceiling (``workout_scaler.fill_shortfall``),
    so the delivered peak may legitimately sit under the periodisation target —
    most often on low-frequency or high-base plans, where the timeline, the
    long-run ratio and the per-run caps leave no room. The trade-off is
    intended, but a *material* gap should be visible rather than silent.

    Never mutates the plan and never raises: this is telemetry over a deliberate
    trade-off, not a guardrail. The fatal check is ``check_plan_structure``.
    """
    candidates = [
        (i, weekly_progression[i])
        for i, week in enumerate(training_plan)
        if i < len(weekly_progression)
        and not week.get("is_recovery")
        and not week.get("is_race_week")
    ]
    if not candidates:
        return
    index, target = max(candidates, key=lambda pair: pair[1])
    if target <= 0:
        return
    delivered = training_plan[index].get("total_km") or 0
    if delivered >= target * PEAK_TARGET_SHORTFALL_RATIO:
        return
    logger.warning(
        "Plan week %s peaks at %.1f km against a %.1f km model target (%.0f%%): "
        "the week layout cannot place the modelled volume at this frequency",
        training_plan[index].get("week", index + 1),
        delivered,
        target,
        delivered / target * 100,
    )


# A loading week whose planned km falls this far below its (reachable) target
# is worth one warning line per week: the reachability gate caps the target at
# what the frequency can carry, so a remaining gap is the week builder dropping
# volume it cannot place inside the per-run caps — the signal the adaptation
# side needs when it judges plan-vs-actual adherence.
WEEKLY_SHORTFALL_RATIO = 0.75


def _log_weekly_shortfalls(
    training_plan: List[Dict[str, Any]],
    weekly_progression: List[float],
    current_km: float,
    target_distance: float,
    weeks: int,
    max_runs_per_week: int,
) -> int:
    """Warn once per loading week that fell >25% short of its reachable target.

    Runs after every smoothing/race-day pass, so ``total_km`` is what the
    runner will actually see. Taper, deload and race weeks are exempt — their
    shortfall is the design, not a fidelity loss. The plan itself has no id
    yet (one is assigned at persistence), so each line carries the generation
    signature (base / goal / weeks / frequency) instead; the week index and
    the target/actual pair make the record joinable downstream.

    Never mutates the plan and never raises. Returns the number of shortfalls
    so tests and callers can assert on fidelity without parsing logs.
    """
    shortfalls = []
    for i, weekly_plan in enumerate(training_plan):
        if i >= len(weekly_progression):
            break
        if (
            weekly_plan.get("is_recovery")
            or weekly_plan.get("is_race_week")
            or weekly_plan.get("phase") == "taper"
        ):
            continue
        target = weekly_progression[i]
        actual = weekly_plan.get("total_km") or 0
        if target > 0 and actual < target * WEEKLY_SHORTFALL_RATIO:
            shortfalls.append((weekly_plan.get("week", i + 1), target, actual))
    for week_num, target, actual in shortfalls:
        logger.warning(
            "Weekly mileage shortfall: week %s planned %.1f km against a %.1f km "
            "reachable target (%.0f%%) [plan: %.0f km base, %.1f km goal, "
            "%d weeks, %d runs/week]",
            week_num,
            actual,
            target,
            actual / target * 100,
            current_km,
            target_distance,
            weeks,
            max_runs_per_week,
        )
    return len(shortfalls)


def _plan_pace_zones(
    vdot: Optional[float],
    target_distance: float,
    trail_profile: Optional[TrailProfile],
    backyard_profile: Optional[BackyardProfile],
    goal_pace_min_km: Optional[float],
    easy_pace_min_km: Optional[float],
) -> Optional[Dict]:
    """The pace zones every step of the plan is written from, or ``None``."""
    # Pass the target so the zones carry a ``race`` entry (5K/10K are
    # always present, longer targets only when the distance is given).
    # Race day and every goal-pace rehearsal read their pace from it.
    # A backyard has no race pace to derive: the loop budget sets it, and
    # asking the VDOT model for a "race pace" over a 160 km projection just
    # makes its solver fail loudly on the way to a number nothing reads.
    zone_target = 0.0 if backyard_profile is not None else target_distance
    pace_zones = VDOTCalculator.get_pace_zones(vdot, zone_target) if vdot else None
    # Road only: a trail goal pace is climbing and terrain as much as
    # fitness, so it says nothing about the flat pace a rehearsal targets.
    if pace_zones and trail_profile is None:
        pin_goal_race_pace(pace_zones, goal_pace_min_km, target_distance)
    return with_personal_easy_band(pace_zones, easy_pace_min_km)


def _reachable_progression(
    current_km: float,
    target_distance: float,
    weeks: int,
    max_runs_per_week: int,
    vdot: Optional[float],
    trail_profile: Optional[TrailProfile],
) -> List[float]:
    """The weekly mileage targets, capped at what the frequency can carry.

    Reachability gate: the progression model sizes its peak from the runner's
    base and the race's ideal volume, blind to how many sessions the runner
    offered to carry that volume in. A peak above ``typical session x
    frequency`` is not a plan but a wish — the week builder would trim it into
    overshoot or crater under the target it was sized from. Resolve the
    reachable peak BEFORE any week is built, so the target every downstream
    pass scales against is one the schedule can actually deliver. Trail/ultra
    capacity sits on the discipline's own run ceiling, where the progression
    model is already bracket-capped, so this gate rarely binds there; it
    exists for the low-mileage / low-frequency road plans where it binds
    hardest.

    NOTE: a pass that probed the builder and rescaled the modelled peak to
    what it delivered was implemented here and **reverted**. The gap at low
    frequency is a roughly *constant fraction* of the target (the week's
    non-long slots are capped and the leftover is dropped by design), not a
    capacity ceiling — so rescaling the target moved it without changing the
    ratio, and at 2 runs it cut prescribed volume ~25% for no gain
    (42.2/45base/2r delivered 45.0 -> 33.7 km). Measuring it is still the
    right shape of fix; the missing piece is a *product* decision about the
    2-run per-slot caps, because no target is reachable while the week can
    only place ~90% of it.
    """
    weekly_progression = mileage_progression.calculate_weekly_progression(
        current_km,
        target_distance,
        weeks,
        max_runs_per_week,
        vdot,
        trail_profile=trail_profile,
    )
    session_km = mileage_progression.typical_session_length_km(trail_profile)
    peak_target = max(weekly_progression, default=0.0)
    reachable_peak, cap_reason, capacity_diag = (
        mileage_progression.resolve_reachable_target(
            peak_target,
            max_runs_per_week,
            session_km,
            base_km=current_km,
        )
    )
    if cap_reason is None:
        return weekly_progression
    logger.info(
        "Mileage target capped (%s): requested peak %.1f km, reachable "
        "%.1f km (capacity %.1f km = %.1f km/session x %d runs; base %.1f km)",
        cap_reason,
        peak_target,
        reachable_peak,
        capacity_diag["capacity"],
        session_km,
        max_runs_per_week,
        current_km,
    )
    return mileage_progression.cap_progression_to_peak(
        weekly_progression, reachable_peak, current_km
    )


def _final_week_targets(
    training_plan: List[Dict[str, Any]], weekly_progression: List[float]
) -> List[float]:
    """Each week's modelled target, as stamped onto the week dict (audit G2).

    The periodisation model deliberately budgets race week as a taper week
    *excluding* the race — but the rendered week's ``total_km`` includes the
    race card, so any surface comparing target vs delivered saw a phantom ~2x
    overshoot on the most psychologically loaded week (a marathon taper target
    of 24 km against 49 km rendered). The race week's stamped target is
    therefore the final race-week card total, so every reader of
    ``weekly_target_km`` compares like with like.
    """
    final_targets: List[float] = []
    for i, weekly_plan in enumerate(training_plan):
        if weekly_plan.get("is_race_week"):
            # Frequency/coherence caps may intentionally keep less than
            # the aspirational pre-race share. Stamp the final cards so the
            # stored target and delivered race week compare like with like.
            target = sum(
                workout.get("distance", 0) or 0
                for workout in weekly_plan.get("daily_workouts", [])
            )
        else:
            target = weekly_progression[i] if i < len(weekly_progression) else 0.0
        final_targets.append(round(target, 1))
    return final_targets


def _report_plan_health(
    training_plan: List[Dict[str, Any]],
    issues: Dict[str, List[str]],
    current_km: float,
    target_distance: float,
    weeks: int,
    max_runs_per_week: int,
) -> None:
    """Plan-level safety net: fail loudly on a week no runner could run.

    Fatal issues fail the generation; softer inconsistencies are logged for
    telemetry. The weekly builder's own ``validate_week_plan`` verdicts —
    stored on each week as ``validation`` and previously only logged at DEBUG
    — are aggregated here so a plan that shipped with model-consistency
    failures is visible in one line next to the structural warnings, instead
    of lost in per-week debug noise (audit G9).
    """
    week_validation_failures = [
        f"wk{w.get('week', i + 1)}: {w['validation'].get('message', 'invalid')}"
        for i, w in enumerate(training_plan)
        if w.get("validation", {}).get("status") == "error"
    ]
    degraded_weeks = [
        w.get("week", i + 1)
        for i, w in enumerate(training_plan)
        if w.get("validation", {}).get("status") == "degraded"
    ]
    all_warnings = issues["warnings"] + [
        f"week validation: {msg}" for msg in week_validation_failures
    ]
    if all_warnings:
        logger.warning(
            "Plan structure warnings (%.0f km base, %.1f km target, %d wks): %s",
            current_km,
            target_distance,
            weeks,
            "; ".join(all_warnings),
        )
    if degraded_weeks:
        logger.info(
            "Plan volume degraded in %d week(s) %s (%.0f km base, %.1f km "
            "target, %d wks, %d runs/week)",
            len(degraded_weeks),
            degraded_weeks,
            current_km,
            target_distance,
            weeks,
            max_runs_per_week,
        )
    if issues["fatal"]:
        logger.error(
            "Degenerate plan (%.0f km base, %.1f km target, %d wks): %s",
            current_km,
            target_distance,
            weeks,
            "; ".join(issues["fatal"]),
        )
        raise PlanGenerationException(
            "Plan generation produced an unusable week: " + "; ".join(issues["fatal"]),
            user_message=(
                "We couldn't build a sound plan from these inputs. Try a "
                "slightly higher current mileage or a longer training window."
            ),
        )


class TrainingPlanGenerator:
    def generate_plan(
        self,
        current_km: float,
        target_distance: float,
        weeks: int,
        max_runs_per_week: int = 4,
        vdot: Optional[float] = None,
        terrain: Optional[str] = None,
        trail_profile: Optional[TrailProfile] = None,
        intensive_weekend_enabled: bool = False,
        backyard_profile: Optional[BackyardProfile] = None,
        goal_pace_min_km: Optional[float] = None,
        easy_pace_min_km: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Generate a comprehensive training plan.

        ``vdot`` is the fitness the training paces are built from — what the
        runner can do now. ``goal_pace_min_km`` is what they are chasing: on a
        road plan it sets the pace of race day and every goal-pace rehearsal,
        and nothing else. ``easy_pace_min_km`` is the pace they have been
        jogging at an easy heart rate: it replaces the VDOT's easy band, and
        nothing else.

        Trail/ultra plans pass ``trail_profile``; legacy callsites that pass
        ``target_distance=30.0`` (with optional ``terrain``) get a default
        profile constructed here so back-compat is preserved.

        ``intensive_weekend_enabled`` opts a trail plan into an Intensive
        Training Weekend block on its final peak week (off by default).

        ``backyard_profile`` makes this a backyard plan: the periodisation is
        still the ultra engine's (which is why the profile also supplies a
        ``trail_profile`` when the caller hasn't), but the weekends carry a
        progressive ladder of loop simulations and the plan closes on the
        goal loop count instead of on a distance.
        """
        self.last_generation_adjustments: List[Dict[str, Any]] = []

        # Back-compat: synthesize a TrailProfile for legacy 30 km callers.
        if trail_profile is None and target_distance == TRAIL_SENTINEL_KM:
            elev = 200.0 if terrain == "flat" else 1000.0
            trail_profile = classify_trail(target_distance, elev)
        # A backyard goal periodises as the ultra it projects onto.
        if backyard_profile is not None and trail_profile is None:
            trail_profile = backyard_profile.as_trail_profile()

        if current_km == 0:
            return self._generate_from_zero(target_distance, weeks, max_runs_per_week)
        enforce_engine_floors(
            current_km, target_distance, weeks, trail_profile, backyard_profile
        )

        pace_zones = _plan_pace_zones(
            vdot,
            target_distance,
            trail_profile,
            backyard_profile,
            goal_pace_min_km,
            easy_pace_min_km,
        )
        max_runs_per_week = self._resolve_run_frequency(current_km, max_runs_per_week)

        # Select the frequency composer: drives structural decisions (quality
        # count, long-run ratios, day scheduling) while the existing math
        # (VDOT, mileage progression, caps) stays in core/training.
        # Trail and backyard plans keep the legacy path for now (Phase 4).
        composer = None
        if trail_profile is None and backyard_profile is None:
            composer = get_composer(max_runs_per_week)

        # The simulation ladder is a plan-level decision (spacing, deloads, and
        # where the dress rehearsal lands all depend on the whole shape), so it
        # is built once here and consulted per week.
        backyard_schedule = None
        if backyard_profile is not None:
            backyard_schedule = build_simulation_schedule(
                weeks,
                calculate_phases(weeks, target_distance, trail_profile=trail_profile),
                backyard_profile,
            )

        weekly_progression = _reachable_progression(
            current_km, target_distance, weeks, max_runs_per_week, vdot, trail_profile
        )

        # Downstream weekly_plan_builder still keys off the legacy ``terrain``
        # string; expose the elevation_class so flat/rolling/hilly/mountainous
        # all dispatch correctly without a wider signature change.
        downstream_terrain = (
            terrain
            if terrain is not None
            else (trail_profile.elevation_class if trail_profile is not None else None)
        )

        training_plan: List[Dict[str, Any]] = []
        high_water_km = current_km
        # Plan-level key-workout memory: no-repeat window, per-plan use cap,
        # and the peak-vs-build interval work-set invariant all live here.
        rotation_state = KeyWorkoutRotationState()
        # Previous *loading* week's long run, used to bound how fast the single
        # long run grows week to week (deloads are skipped so the post-deload
        # ramp resumes from the pre-dip long run, not the reduced one).
        prev_long_run_km: Optional[float] = None
        experience_level = derive_experience_level(current_km)
        for week in range(1, weeks + 1):
            week_km = weekly_progression[week - 1]
            weekly_plan = build_weekly_plan(
                week,
                week_km,
                target_distance,
                max_runs_per_week,
                weeks,
                vdot=vdot,
                pace_zones=pace_zones,
                experience_level=experience_level,
                terrain=downstream_terrain,
                trail_profile=trail_profile,
                intensive_weekend_enabled=intensive_weekend_enabled,
                prev_long_run_km=prev_long_run_km,
                rotation_state=rotation_state,
                backyard_profile=backyard_profile,
                backyard_schedule=backyard_schedule,
                composer=composer,
            )
            is_recovery = weekly_plan.get("is_recovery", False)

            enforce_weekly_ramp_cap(
                weekly_plan, high_water_km, max_runs_per_week, pace_zones
            )

            # The 10% cap above shrinks flexible workouts — including the
            # long run — after the weekly builder fitted key quality sessions
            # against the original long run. Re-fit them here, before this
            # week's total becomes the next week's high-water baseline, so a
            # quality day never rivals the final long run. (The later
            # smoothing passes only rescale recovery/taper weeks, which carry
            # no key quality overlays.)
            reclamp_quality_to_long_run(weekly_plan["daily_workouts"])
            weekly_plan["total_km"] = week_total_km(weekly_plan["daily_workouts"])

            if (
                trail_profile is not None
                and backyard_profile is None
                and not is_recovery
                and weekly_plan.get("phase") != "taper"
            ):
                refill_trail_week(weekly_plan, week_km, high_water_km, pace_zones)

            # Week-level scaling above can move a workout across the 3 km
            # display boundary; refresh duration hints from final distances.
            refresh_duration_hints(weekly_plan["daily_workouts"], pace_zones)

            if not is_recovery:
                high_water_km = max(high_water_km, weekly_plan["total_km"])
                long_run_km = _long_run_km(weekly_plan)
                if long_run_km is not None:
                    prev_long_run_km = long_run_km

            training_plan.append(weekly_plan)

        smooth_recovery_dips(training_plan, pace_zones)
        smooth_taper(
            training_plan,
            target_distance,
            weeks,
            pace_zones,
            trail_profile=trail_profile,
        )
        sweep_trivial_sessions(training_plan, pace_zones)
        if backyard_profile is not None:
            install_backyard_race_day(
                training_plan, backyard_profile, pace_zones, max_runs=max_runs_per_week
            )
        else:
            install_race_day(
                training_plan,
                target_distance,
                pace_zones,
                trail_profile=trail_profile,
                max_runs=max_runs_per_week,
            )

        # Reconcile executable steps and card budgets before deriving the
        # delivered peak and race-aware targets.
        reconcile_card_distances(training_plan)
        refresh_plan_fields(training_plan)

        # Recompute every derived field and validation verdict from the fully
        # mutated output, then run the same structural guard over what will be
        # persisted/exported.  No intermediate builder verdict survives here.
        issues = finalize_plan(
            training_plan, _final_week_targets(training_plan, weekly_progression)
        )
        self._record_frequency_volume_cap(training_plan, current_km, max_runs_per_week)

        # Model-vs-builder reconciliation: the builder may legitimately deliver
        # less than the periodisation model asked for (it drops volume it cannot
        # place inside the per-run caps rather than inflating a run). Report a
        # *material* shortfall once per plan instead of letting it pass silently.
        _log_peak_shortfall(training_plan, weekly_progression)
        _log_weekly_shortfalls(
            training_plan,
            weekly_progression,
            current_km,
            target_distance,
            weeks,
            max_runs_per_week,
        )
        _report_plan_health(
            training_plan, issues, current_km, target_distance, weeks, max_runs_per_week
        )
        return training_plan

    def _generate_from_zero(
        self, target_distance: float, weeks: int, max_runs_per_week: int
    ) -> List[Dict[str, Any]]:
        """A runner with no base gets the beginner plan, or a refusal."""
        if target_distance not in [5.0, 10.0]:
            raise ZeroMileageUnsupportedException(
                f"A {target_distance} km race requires an existing running base. "
                "Please start with a 5K or 10K beginner plan to build your fitness first.",
                suggestion="Try a 5K or 10K plan with 0 km/week to get started.",
            )
        beginner_generator = BeginnerPlanGenerator()
        beginner_plan = beginner_generator.generate_plan(
            target_distance, weeks, max_runs_per_week
        )
        self.last_requested_runs_per_week = max_runs_per_week
        self.last_resolved_runs_per_week = (
            beginner_generator.last_resolved_runs_per_week
        )
        return beginner_plan

    def _resolve_run_frequency(self, current_km: float, max_runs_per_week: int) -> int:
        """The running days the weekly budget can actually fill.

        Don't shatter a very low weekly budget into trivially short runs.
        Below ~2.5 km/run a plan reads as unrealistic (four 1.3 km runs for a
        5 km/week base), so drop the running frequency until each run carries
        a viable dose — a deliberately more "templated" shape at the low end.
        Floored at MIN_RUNNING_DAYS so the long + quality + easy structure
        survives. (This is the same realism line the plan test-grid draws when
        it skips combos under 2.5 km/run.) The reduction is surfaced — logged
        here and recorded on the instance as ``last_resolved_runs_per_week``
        — so a caller (or the web layer) can tell the runner the plan carries
        fewer running days than they asked for instead of silently under-
        delivering the requested schedule (audit G8).
        """
        self.last_requested_runs_per_week = max_runs_per_week
        resolved_runs = _viable_run_frequency(current_km, max_runs_per_week)
        if resolved_runs < max_runs_per_week:
            logger.warning(
                "Requested %d runs/week resolved to %d for a %.1f km/week base: "
                "each run needs at least %.1f km to be a real session",
                max_runs_per_week,
                resolved_runs,
                current_km,
                MIN_VIABLE_RUN_KM,
            )
        self.last_resolved_runs_per_week = resolved_runs
        return resolved_runs

    def _record_frequency_volume_cap(
        self,
        training_plan: List[Dict[str, Any]],
        current_km: float,
        max_runs_per_week: int,
    ) -> None:
        """Note on the plan when the frequency could not hold the runner's base."""
        delivered_peak = max(
            (
                week.get("training_km", 0) or 0
                for week in training_plan
                if not week.get("is_recovery") and not week.get("is_race_week")
            ),
            default=0.0,
        )
        if current_km <= 0 or delivered_peak >= current_km * 0.90:
            return
        adjustment = {
            "code": "frequency_volume_cap",
            "requested_base_km": round(current_km, 1),
            "delivered_peak_km": round(delivered_peak, 1),
            "resolved_runs_per_week": max_runs_per_week,
            "message": (
                "The selected run frequency cannot preserve the current "
                "weekly volume inside the plan's per-session safety limits."
            ),
        }
        self.last_generation_adjustments.append(adjustment)
        training_plan[0].setdefault("generation_adjustments", []).append(adjustment)


def _long_run_km(weekly_plan: Dict[str, Any]) -> Optional[float]:
    """The week's long-run distance, or ``None`` when it carries none."""
    for w in weekly_plan["daily_workouts"]:
        if w.get("type") == "long" and (w.get("distance", 0) or 0) > 0:
            return w["distance"]
    return None
