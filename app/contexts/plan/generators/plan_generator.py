"""Training plan generator -- thin orchestrator.

Delegates to focused modules:
- phase_calculator: phase distribution, distance categories, recovery weeks
- mileage_progression: weekly mileage progression with 10% rule
- workout_distribution: workout type counts and day scheduling
- workout_builders: individual workout generation
- long_run_calculator: long run and quality workout distances
- weekly_plan_builder: single-week plan assembly, scaling, validation

Callers should import those modules directly for low-level helpers; this class
exposes only the high-level ``generate_plan`` orchestration.
"""

import logging
from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.beginner_plan_generator import BeginnerPlanGenerator
from app.contexts.plan.generators.plan_finalizer import (
    finalize_plan,
    reconcile_card_distances,
    refresh_plan_fields,
)
from app.contexts.plan.generators.weekly_plan_builder import (
    attach_duration_hints,
    build_weekly_plan,
)
from app.core.training.periodization import mileage_progression

# Re-export for any code that imports PHASE_DISTRIBUTIONS from here
from app.core.training.periodization.phase_calculator import (
    PHASE_DISTRIBUTIONS,  # noqa: F401
)
from app.core.training.periodization.strength_plan import derive_experience_level
from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.core.training.profiles.backyard_profile import (
    BackyardProfile,
    backyard_max_weeks,
    backyard_min_weekly_km,
    backyard_min_weeks,
)
from app.core.training.profiles.backyard_simulation import build_simulation_schedule
from app.core.training.profiles.trail_profile import (
    TRAIL_SENTINEL_KM,
    TrailProfile,
    classify_trail,
    trail_min_weekly_mileage,
    trail_min_weeks,
)
from app.core.training.training_config import DISTANCE_CONSTRAINTS, get_constraints
from app.core.training.workouts import workout_builders, workout_steps
from app.core.training.workouts.key_workout_library import KeyWorkoutRotationState
from app.exceptions import (
    InadequateBaseException,
    InsufficientTimeException,
    PlanGenerationException,
    ValidationException,
    ZeroMileageUnsupportedException,
)

logger = logging.getLogger(__name__)

# Below this per-run distance a plan reads as unrealistic (trivially short runs);
# the generator drops running frequency rather than emit such runs.
MIN_VIABLE_RUN_KM = 2.5
# Floor on running days: a real training week still wants a long run, a quality
# session, and an easy run, so frequency is never reduced below this.
MIN_RUNNING_DAYS = 3

# Card types that ask the runner to run. A card of one of these types whose
# distance has drained to 0 is not a session — it renders as an easy run with
# no distance on it — and every pass that tidies a week should be allowed to
# turn it into the rest day it effectively is.
RUNNING_CARD_TYPES = ("easy", "medium_long", "tempo", "interval", "hill")

# Floors for the trivial-session sweep. A *quality* card below this dose
# cannot hold warm-up, work, and cool-down and is relabelled as the easy run
# it effectively was. An *easy* card below the coherence floor is not a run by
# any measure (worst case observed: 0.3 km) and is rendered as rest. Between
# the coherence floor and a real session sits honest territory — a 1.5 km jog
# in a small week — which the sweep must leave alone: converting it erodes
# frequency and deflates the ramp baseline for no coaching gain.
MIN_VIABLE_QUALITY_KM = 2.5
MIN_COHERENT_RUN_KM = 1.0

# How far the 10 % weekly cap may shrink a flexible session before it stops.
# A ratio rather than an absolute distance: an absolute floor disables the cap
# on the low-base high-frequency plans that sit *at* that floor, while a ratio
# can never reach zero — so the cap keeps working and no session is ever
# deleted into a 0.0 km card.
FLEXIBLE_TRIM_FLOOR_RATIO = 0.5


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
    ) -> List[Dict[str, Any]]:
        """Generate a comprehensive training plan.

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
            if target_distance in [5.0, 10.0]:
                beginner_generator = BeginnerPlanGenerator()
                beginner_plan = beginner_generator.generate_plan(
                    target_distance, weeks, max_runs_per_week
                )
                self.last_requested_runs_per_week = max_runs_per_week
                self.last_resolved_runs_per_week = (
                    beginner_generator.last_resolved_runs_per_week
                )
                return beginner_plan
            raise ZeroMileageUnsupportedException(
                f"A {target_distance} km race requires an existing running base. "
                "Please start with a 5K or 10K beginner plan to build your fitness first.",
                suggestion="Try a 5K or 10K plan with 0 km/week to get started.",
            )

        # ── Engine-level input floors ────────────────────────────────────
        # ``PlanRequest`` enforces these for web traffic, but the generator is
        # also called directly (backtests, scripts, future endpoints). The
        # sweep that motivated these guards produced a +21 % ramp breach and
        # a 0.0 km easy card on a *loading* week from a base the schema would
        # have refused — below-floor inputs don't just make conservative
        # plans, they compose into broken ones. Raise the same domain
        # exceptions the schema raises rather than inventing a second
        # vocabulary for the same refusal.
        if trail_profile is None and backyard_profile is None:
            constraints = get_constraints(target_distance)
            if constraints is None:
                # 30.0 never reaches here: the legacy branch above already
                # promoted it to a trail profile.
                road_names = ", ".join(
                    c.name
                    for d, c in DISTANCE_CONSTRAINTS.items()
                    if d != TRAIL_SENTINEL_KM
                )
                raise ValidationException(
                    f"Unsupported road target distance: {target_distance} km",
                    user_message=(
                        "Please select a valid distance: "
                        f"{road_names}, or pick Trail/Ultra for a custom goal."
                    ),
                )
            if current_km < constraints.min_mileage:
                raise InadequateBaseException(
                    f"Current mileage ({current_km:g} km/week) is below the "
                    f"recommended minimum ({constraints.min_mileage:g} km/week) "
                    f"for {constraints.name} training",
                    suggestion=constraints.low_mileage_msg,
                )
            if weeks < constraints.min_weeks:
                raise InsufficientTimeException(
                    f"Training for {constraints.name} requires at least "
                    f"{constraints.min_weeks} weeks",
                    suggestion=(
                        f"Consider extending your training to "
                        f"{constraints.min_weeks} weeks. "
                        f"{constraints.insufficient_time_reason}"
                    ),
                )
            if weeks > constraints.max_weeks:
                raise ValidationException(
                    f"{constraints.name} plans are capped at "
                    f"{constraints.max_weeks} weeks; requested {weeks}",
                    user_message=(
                        f"{constraints.excessive_time_reason}. "
                        "Consider a shorter training period."
                    ),
                )
            # NOTE: runs-per-week floors (HM ≥ 3, marathon ≥ 4) are *product
            # policy* and stay schema-only. The engine is deliberately
            # permissive here — it composes gracefully at 2-3 runs (the
            # frequency composers, the envelope grid, and the physiological
            # envelope ledger all exercise that space) — so refusing would
            # break the engine's contract, not protect it.
        elif backyard_profile is not None:
            min_km = backyard_min_weekly_km(backyard_profile)
            if current_km < min_km:
                raise InadequateBaseException(
                    f"Current mileage ({current_km:g} km/week) is below the "
                    f"recommended minimum ({min_km:g} km/week) for a "
                    f"{backyard_profile.target_loops}-loop goal",
                    suggestion=(
                        "Build a steady base of easy running first — a backyard "
                        "asks you to repeat a loop you're already comfortable "
                        "with, not to discover one."
                    ),
                )
            min_w = backyard_min_weeks(backyard_profile)
            max_w = backyard_max_weeks(backyard_profile)
            if weeks < min_w:
                raise InsufficientTimeException(
                    f"Training for {backyard_profile.target_loops} loops requires "
                    f"at least {min_w} weeks",
                    suggestion=(
                        f"This goal needs {min_w}–{max_w} weeks to build the "
                        "aerobic base, the loop-pace habit, and enough "
                        "simulations to rehearse the format."
                    ),
                )
        elif current_km < trail_min_weekly_mileage(trail_profile):
            min_km = trail_min_weekly_mileage(trail_profile)
            raise InadequateBaseException(
                f"Current mileage ({current_km:g} km/week) is below the "
                f"recommended minimum ({min_km:g} km/week) for a "
                f"{trail_profile.distance_km:g} km trail/ultra",
                suggestion=(
                    "Build a steady base of easy running first — "
                    "trail-specific volume and elevation work compounds "
                    "the load quickly."
                ),
            )
        elif weeks < trail_min_weeks(trail_profile):
            raise InsufficientTimeException(
                f"Training for a {trail_profile.distance_km:g} km trail/ultra "
                f"requires at least {trail_min_weeks(trail_profile)} weeks",
                suggestion=(
                    "This bracket needs time to build trail-specific "
                    "strength, time-on-feet, and fueling habits."
                ),
            )

        # Pass the target so the zones carry a ``race`` entry (5K/10K are
        # always present, longer targets only when the distance is given).
        # Race day and every goal-pace rehearsal read their pace from it.
        # A backyard has no race pace to derive: the loop budget sets it, and
        # asking the VDOT model for a "race pace" over a 160 km projection just
        # makes its solver fail loudly on the way to a number nothing reads.
        zone_target = 0.0 if backyard_profile is not None else target_distance
        pace_zones = VDOTCalculator.get_pace_zones(vdot, zone_target) if vdot else None

        experience_level = derive_experience_level(current_km)

        # Don't shatter a very low weekly budget into trivially short runs.
        # Below ~2.5 km/run a plan reads as unrealistic (four 1.3 km runs for a
        # 5 km/week base), so drop the running frequency until each run carries
        # a viable dose — a deliberately more "templated" shape at the low end.
        # Floored at MIN_RUNNING_DAYS so the long + quality + easy structure
        # survives. (This is the same realism line the plan test-grid draws when
        # it skips combos under 2.5 km/run.) The reduction is surfaced — logged
        # here and recorded on the instance as ``last_resolved_runs_per_week``
        # — so a caller (or the web layer) can tell the runner the plan carries
        # fewer running days than they asked for instead of silently under-
        # delivering the requested schedule (audit G8).
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
        max_runs_per_week = resolved_runs

        # Select the frequency composer: drives structural decisions (quality
        # count, long-run ratios, day scheduling) while the existing math
        # (VDOT, mileage progression, caps) stays in core/training.
        # Trail and backyard plans keep the legacy path for now (Phase 4).
        composer = None
        if trail_profile is None and backyard_profile is None:
            from app.core.training.frequency import get_composer

            composer = get_composer(max_runs_per_week)

        # The simulation ladder is a plan-level decision (spacing, deloads, and
        # where the dress rehearsal lands all depend on the whole shape), so it
        # is built once here and consulted per week.
        backyard_schedule = None
        if backyard_profile is not None:
            from app.core.training.periodization.phase_calculator import (
                calculate_phases,
            )

            backyard_schedule = build_simulation_schedule(
                weeks,
                calculate_phases(weeks, target_distance, trail_profile=trail_profile),
                backyard_profile,
            )

        weekly_progression = mileage_progression.calculate_weekly_progression(
            current_km,
            target_distance,
            weeks,
            max_runs_per_week,
            vdot,
            trail_profile=trail_profile,
        )

        # Reachability gate: the progression model sizes its peak from the
        # runner's base and the race's ideal volume, blind to how many
        # sessions the runner offered to carry that volume in. A peak above
        # ``typical session x frequency`` is not a plan but a wish — the week
        # builder would trim it into overshoot or crater under the target it
        # was sized from. Resolve the reachable peak BEFORE any week is built,
        # so the target every downstream pass scales against is one the
        # schedule can actually deliver. Trail/ultra capacity sits on the
        # discipline's own run ceiling, where the progression model is already
        # bracket-capped, so this gate rarely binds there; it exists for the
        # low-mileage / low-frequency road plans where it binds hardest.
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
        if cap_reason is not None:
            weekly_progression = mileage_progression.cap_progression_to_peak(
                weekly_progression, reachable_peak, current_km
            )
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

        # Downstream weekly_plan_builder still keys off the legacy ``terrain``
        # string; expose the elevation_class so flat/rolling/hilly/mountainous
        # all dispatch correctly without a wider signature change.
        downstream_terrain = (
            terrain
            if terrain is not None
            else (trail_profile.elevation_class if trail_profile is not None else None)
        )

        # NOTE: a pass that probed the builder and rescaled the modelled peak to
        # what it delivered was implemented here and **reverted**. The gap at low
        # frequency is a roughly *constant fraction* of the target (the week's
        # non-long slots are capped and the leftover is dropped by design), not a
        # capacity ceiling — so rescaling the target moved it without changing the
        # ratio, and at 2 runs it cut prescribed volume ~25% for no gain
        # (42.2/45base/2r delivered 45.0 -> 33.7 km). Measuring it is still the
        # right shape of fix; the missing piece is a *product* decision about the
        # 2-run per-slot caps, because no target is reachable while the week can
        # only place ~90% of it.

        training_plan = []
        actual_high_water = current_km
        # Plan-level key-workout memory: no-repeat window, per-plan use cap,
        # and the peak-vs-build interval work-set invariant all live here.
        rotation_state = KeyWorkoutRotationState()
        # Previous *loading* week's long run, used to bound how fast the single
        # long run grows week to week (deloads are skipped so the post-deload
        # ramp resumes from the pre-dip long run, not the reduced one).
        prev_long_run_km: Optional[float] = None
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

            # Enforce 10% cap against actual high-water mark.
            #
            # Only flexible workouts (easy, long) absorb the cap. Prescriptive
            # workouts (key overlays + tempo / interval / hill) keep their
            # authored distance — silently rescaling them would leave the
            # description and step list describing a different session than
            # the runner's distance number says. If flexible headroom is
            # exhausted, the small overage rides into the next week's budget
            # rather than corrupting a prescription.
            from app.contexts.plan.generators.weekly_plan_builder import (
                attach_duration_hints,
            )
            from app.contexts.plan.generators.workout_scaler import (
                is_prescriptive as _is_prescriptive,
            )
            from app.contexts.plan.generators.workout_scaler import (
                set_distance as _set_distance,
            )

            is_recovery = weekly_plan.get("is_recovery", False)
            actual_km = weekly_plan["total_km"]
            if not is_recovery and actual_high_water > 0:
                ceiling = actual_high_water * mileage_progression.WEEK_OVER_WEEK_CAP
                if actual_km > ceiling and actual_km > 0:
                    flexible = [
                        w
                        for w in weekly_plan["daily_workouts"]
                        if w.get("type") in ("easy", "long", "medium_long")
                        and not _is_prescriptive(w)
                        and w.get("distance", 0) > 0
                    ]
                    fixed_km = sum(
                        w.get("distance", 0)
                        for w in weekly_plan["daily_workouts"]
                        if w not in flexible and w.get("distance", 0) > 0
                    )
                    flexible_km = sum(w["distance"] for w in flexible)
                    target_flexible = max(0.0, ceiling - fixed_km)
                    if flexible and flexible_km > 0 and target_flexible < flexible_km:
                        # At ≤ 3 runs drain the easy runs first, holding the
                        # long run: it is the week's anchor, the weekly builder
                        # just enforced its cross-week progression floor, and
                        # scaling both proportionally pushed the long run back
                        # below that floor (measured: 10.6 → 8.9 across a build
                        # week — the progression fault the floor exists to
                        # prevent). Only when the easy budget alone cannot
                        # absorb the overage do both flexible sessions scale
                        # together, exactly as ``workout_scaler.scale_down``'s
                        # ``protect_long`` branch behaves. At 4+ runs the
                        # original proportional scaling stands: protecting the
                        # long run there let loading-week longs compound past
                        # the contract cap and the envelope's published band
                        # (a 19 km "long run" for a 10K).
                        easy_ws = [w for w in flexible if w.get("type") == "easy"]
                        easy_km = sum(w["distance"] for w in easy_ws)
                        easy_floor_km = sum(
                            w["distance"] * FLEXIBLE_TRIM_FLOOR_RATIO for w in easy_ws
                        )
                        overage = flexible_km - target_flexible
                        if (
                            max_runs_per_week <= 3
                            and easy_ws
                            and overage <= (easy_km - easy_floor_km)
                        ):
                            scale_easy = (easy_km - overage) / easy_km
                            for w in easy_ws:
                                scaled = w["distance"] * scale_easy
                                floor = w["distance"] * FLEXIBLE_TRIM_FLOOR_RATIO
                                _set_distance(w, max(floor, scaled), pace_zones)
                        else:
                            scale = target_flexible / flexible_km
                            for w in flexible:
                                scaled = w["distance"] * scale
                                # The cap may shrink a session; it may not delete
                                # one. When the week's *prescriptive* content
                                # already exceeds the ceiling this target lands at
                                # zero, and scaling to it left the runner a 0.0 km
                                # "easy" card on the calendar while the week still
                                # jumped 23 % — the worst of both.
                                #
                                # A ratio, not an absolute floor. An absolute
                                # ``MIN_VIABLE_RUN_KM`` floor also stopped the cap
                                # trimming *ordinary* weeks, because a low-base
                                # high-frequency plan already sits at 2.5 km a run:
                                # it let a trail plan sit at 12.04 %/week against
                                # the 10 % the cap allows. A ratio can never reach
                                # zero, so it fixes the deletion without disabling
                                # the cap.
                                floor = w["distance"] * FLEXIBLE_TRIM_FLOOR_RATIO
                                _set_distance(w, max(floor, scaled), pace_zones)
                    # If rounding still leaves a tiny overage, trim from the
                    # largest flexible workout to respect the 10% cap — stopping
                    # at the floor rather than shaving a session away.
                    new_total_exact = sum(
                        w.get("distance", 0) for w in weekly_plan["daily_workouts"]
                    )
                    if new_total_exact > ceiling + 0.01 and flexible:
                        largest = max(flexible, key=lambda w: w.get("distance", 0))
                        trim = new_total_exact - ceiling
                        current = largest.get("distance", 0)
                        trim_floor = current * FLEXIBLE_TRIM_FLOOR_RATIO
                        _set_distance(
                            largest,
                            max(trim_floor, current - trim),
                            pace_zones,
                        )
                    new_total = round(
                        sum(
                            w.get("distance", 0) for w in weekly_plan["daily_workouts"]
                        ),
                        1,
                    )
                    # The easy-first drain preserves the long run — which can
                    # push its *share* of the now-smaller week past the
                    # frequency ceiling (a 5.6 km week with long 3.8 = 0.68
                    # against 0.65; a 3-run marathon week drained to 0.56
                    # against 0.55). Re-solve the share here so no pass leaves
                    # the envelope breached: the long run gives back what its
                    # share requires, bounded by the same trim floor.
                    from app.core.training.periodization.long_run_calculator import (
                        get_weekly_long_run_ratio_cap as _share_cap,
                    )

                    share_ceiling = _share_cap(phase="base", max_runs=max_runs_per_week)
                    lw = next(
                        (
                            w
                            for w in weekly_plan["daily_workouts"]
                            if w.get("type") == "long" and (w.get("distance") or 0) > 0
                        ),
                        None,
                    )
                    if lw is not None:
                        rest_km2 = round(
                            sum(
                                w.get("distance", 0)
                                for w in weekly_plan["daily_workouts"]
                                if w.get("type") not in ("rest", "recovery", "long")
                            ),
                            1,
                        )
                        share_max = (
                            int(share_ceiling * rest_km2 / (1 - share_ceiling) * 10)
                            / 10
                            if share_ceiling < 1
                            else rest_km2
                        )
                        if (lw.get("distance") or 0) > share_max + 0.05:
                            _set_distance(
                                lw,
                                max(
                                    lw["distance"] * FLEXIBLE_TRIM_FLOOR_RATIO,
                                    share_max,
                                ),
                                pace_zones,
                            )
                            new_total = round(
                                sum(
                                    w.get("distance", 0)
                                    for w in weekly_plan["daily_workouts"]
                                ),
                                1,
                            )
                    weekly_plan["total_km"] = new_total
                    # This pass is the 10% invariant being *enforced*, not dead
                    # code: it fires whenever the assembled week overshoots the
                    # delivered high-water mark (measured on the plan matrix —
                    # see the reachability gate above for the model-level fix).
                    # Most clips are sub-km rounding recoveries, so they log at
                    # DEBUG like the weekly builder's own verdict; the material
                    # signal is the per-week shortfall warning below, which
                    # compares delivered volume against the reachable target.
                    logger.debug(
                        "10%% weekly cap enforced: week %s trimmed to %.1f km "
                        "against a %.1f km ceiling (%.1f km assembled)",
                        week,
                        new_total,
                        ceiling,
                        actual_km,
                    )

            # The 10% cap above shrinks flexible workouts — including the
            # long run — after the weekly builder fitted key quality sessions
            # against the original long run. Re-fit them here, before this
            # week's total becomes the next week's high-water baseline, so a
            # quality day never rivals the final long run. (The later
            # smoothing passes only rescale recovery/taper weeks, which carry
            # no key quality overlays.)
            from app.contexts.plan.generators.workout_scaler import (
                reclamp_quality_to_long_run as _reclamp_quality,
            )

            _reclamp_quality(weekly_plan["daily_workouts"])
            weekly_plan["total_km"] = round(
                sum(w.get("distance", 0) or 0 for w in weekly_plan["daily_workouts"]),
                1,
            )

            # Trail weeks can lose a small amount when the final quality/long
            # relationship is clamped. Return that released volume to the
            # non-prescriptive aerobic slots while respecting both the weekly
            # ramp ceiling and the long-run anchor. Without this transfer, the
            # same 30 km trail target delivered 31.7 km at four runs but only
            # 30.7 km at five — offering another day reduced the prescription.
            if (
                trail_profile is not None
                and backyard_profile is None
                and not is_recovery
            ):
                refill_ceiling = (
                    actual_high_water * mileage_progression.WEEK_OVER_WEEK_CAP
                    if actual_high_water > 0
                    else week_km
                )
                refill_target = min(week_km, refill_ceiling)
                deficit = refill_target - weekly_plan["total_km"]
                long_distance = max(
                    (
                        w.get("distance", 0) or 0
                        for w in weekly_plan["daily_workouts"]
                        if w.get("type") == "long"
                    ),
                    default=0.0,
                )
                receivers = [
                    w
                    for w in weekly_plan["daily_workouts"]
                    if w.get("type") in ("easy", "medium_long")
                    and not _is_prescriptive(w)
                    and 0 < (w.get("distance") or 0) < long_distance
                ]
                headrooms = [long_distance - w["distance"] for w in receivers]
                total_headroom = sum(headrooms)
                if deficit > 0.05 and total_headroom > 0:
                    for workout, headroom in zip(receivers, headrooms):
                        addition = min(headroom, deficit * headroom / total_headroom)
                        _set_distance(
                            workout, workout["distance"] + addition, pace_zones
                        )
                    weekly_plan["total_km"] = round(
                        sum(
                            w.get("distance", 0) or 0
                            for w in weekly_plan["daily_workouts"]
                        ),
                        1,
                    )

            # Week-level scaling above can move a workout across the 3 km
            # display boundary; refresh duration hints from final distances.
            for w in weekly_plan["daily_workouts"]:
                w.pop("duration_min", None)
            attach_duration_hints(weekly_plan["daily_workouts"], pace_zones)

            if not is_recovery and weekly_plan["total_km"] > actual_high_water:
                actual_high_water = weekly_plan["total_km"]

            if not is_recovery:
                long_w = next(
                    (
                        w
                        for w in weekly_plan["daily_workouts"]
                        if w.get("type") == "long" and (w.get("distance", 0) or 0) > 0
                    ),
                    None,
                )
                if long_w is not None:
                    prev_long_run_km = long_w["distance"]

            training_plan.append(weekly_plan)

        _smooth_recovery_dips(training_plan, pace_zones)
        _smooth_taper(
            training_plan,
            target_distance,
            weeks,
            pace_zones,
            trail_profile=trail_profile,
        )
        _sweep_trivial_sessions(training_plan, pace_zones)
        if backyard_profile is not None:
            _install_backyard_race_day(
                training_plan, backyard_profile, pace_zones, max_runs=max_runs_per_week
            )
        else:
            _install_race_day(
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

        # Stamp each week's modelled target onto the week dict (audit G2).
        # The periodisation model deliberately budgets race week as a taper
        # week *excluding* the race — but the rendered week's ``total_km``
        # includes the race card, so any surface comparing target vs delivered
        # saw a phantom ~2x overshoot on the most psychologically loaded week
        # (a marathon taper target of 24 km against 49 km rendered). The race
        # week's stamped target is therefore the final race-week card total,
        # so every reader of ``weekly_target_km`` compares like with like.
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

        # Recompute every derived field and validation verdict from the fully
        # mutated output, then run the same structural guard over what will be
        # persisted/exported.  No intermediate builder verdict survives here.
        issues = finalize_plan(training_plan, final_targets)

        delivered_peak = max(
            (
                week.get("training_km", 0) or 0
                for week in training_plan
                if not week.get("is_recovery") and not week.get("is_race_week")
            ),
            default=0.0,
        )
        if current_km > 0 and delivered_peak < current_km * 0.90:
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

        # Plan-level safety net: catch a week that composed into something
        # unrunnable before it ever reaches the runner. Fatal issues fail the
        # generation loudly; softer inconsistencies are logged for telemetry.
        # The weekly builder's own ``validate_week_plan`` verdicts — stored on
        # each week as ``validation`` and previously only logged at DEBUG — are
        # aggregated here so a plan that shipped with model-consistency
        # failures is visible in one line next to the structural warnings,
        # instead of lost in per-week debug noise (audit G9).
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
                "Plan generation produced an unusable week: "
                + "; ".join(issues["fatal"]),
                user_message=(
                    "We couldn't build a sound plan from these inputs. Try a "
                    "slightly higher current mileage or a longer training window."
                ),
            )

        return training_plan


# Race day sits on the last day of the final week. The week runs Mon..Sun
# (day 1..7), and the scheduler anchors the long run on day 6 — so the race
# lands on the Sunday that every plan was implicitly counting down to.
RACE_DAY_NUMBER = 7

# Bounds on the day-before-race shakeout. Its job is to keep the legs open,
# not to add fitness — nothing gained the day before a race survives to the
# start line, and anything longer costs freshness. The floor keeps it a real
# run rather than a token one on low-volume plans.
RACE_WEEK_SHAKEOUT_MAX_KM = 4.0
RACE_WEEK_SHAKEOUT_MIN_KM = 2.0

# Race week keeps a shakeout plus at most one other session.  Selection now
# happens before sizing, so this freshness rule no longer causes the later
# trivial-session sweep to discard most of the pre-race budget by accident.
RACE_WEEK_MAX_PRERACE_RUNS = 2


def _build_shakeout(
    day: int, distance_km: float, pace_zones: Optional[Dict]
) -> Dict[str, Any]:
    """The day-before-race shakeout: a few easy km with strides."""
    workout = workout_builders.generate_easy_run(
        day, distance_km, distance_km, pace_zones
    )
    workout["is_shakeout"] = True
    workout["description"] = (
        f"Shakeout — {distance_km:g} km very easy, finishing with 4 × 100 m "
        "strides. Just enough to keep the legs open and burn off nerves. "
        "Everything you feel today is taper legs, not lost fitness."
    )
    workout["steps"] = workout_steps.build_shakeout_steps(distance_km, pace_zones)
    workout["coaching_rationale"] = (
        "The day before is about staying loose, not proving anything. Strides "
        "remind your legs what fast feels like without costing you a thing."
    )
    return workout


def _install_race_day(
    training_plan: List[Dict[str, Any]],
    target_distance: float,
    pace_zones: Optional[Dict],
    trail_profile: Optional[TrailProfile] = None,
    max_runs: int = RACE_WEEK_MAX_PRERACE_RUNS + 1,
) -> None:
    """Replace the final week's long run with the goal race (in place).

    A plan built backwards from a race used to stop one session short of it:
    the last week ended on a taper long run and the runner was left to infer
    where the race went. This pass closes the plan on the event itself.

    Three things happen, in order:

    1. The final week's long run becomes a short shakeout. A near-race-distance
       long run one or two days before the race is not a taper, it is a second
       race — but going fully sedentary is not the answer either, so the day
       keeps a few easy kilometres with strides to hold the legs open. This
       also keeps race week at the runner's requested number of running days.
    2. Everything still standing before race day is scaled to
       ``RACE_WEEK_PRERACE_SHARE`` of the realized peak. The taper curve sized
       race week as though its long run were still the anchor; with the race
       installed the rest of the week is shakeout, and holding it at the taper
       total would send the runner to the start line with a normal training
       week in their legs.
    3. The race is installed on :data:`RACE_DAY_NUMBER`, displacing whatever
       easy run the scheduler had put there.

    The race is never rescaled afterwards — its distance is set by the event,
    not by a weekly budget — so this runs after every smoothing pass.
    """
    from app.contexts.plan.generators.weekly_plan_builder import attach_duration_hints
    from app.contexts.plan.generators.workout_scaler import scale_down as _scale_down
    from app.contexts.plan.generators.workout_scaler import (
        set_distance as _set_distance,
    )
    from app.core.training.tuning import (
        RACE_WEEK_MIN_PRERACE_KM,
        RACE_WEEK_PRERACE_SHARE,
    )

    if not training_plan or target_distance <= 0:
        return
    final_week = training_plan[-1]
    workouts = final_week.get("daily_workouts") or []

    # Realized peak across every loading week — the same anchor _smooth_taper
    # uses, so race week is sized against volume the runner actually ran.
    realized_peak = max(
        (
            w.get("total_km", 0) or 0
            for w in training_plan[:-1]
            if not w.get("is_recovery")
        ),
        default=final_week.get("total_km", 0) or 0,
    )

    pre_race_target = max(
        RACE_WEEK_MIN_PRERACE_KM, round(realized_peak * RACE_WEEK_PRERACE_SHARE, 1)
    )

    # The race consumes one of the week's running slots rather than adding an
    # extra one, so race week keeps the runner's requested training frequency.
    # When the scheduler had already put a run on race day the race simply
    # takes it, and the freed long-run day becomes the day-before shakeout.
    # When race day was rest, the race is the extra run and the long-run day
    # rests instead — a marathon plan's race week reading easy / easy / tempo /
    # race, with the Saturday off.
    #
    # Displaced days are rewritten in place rather than dropped: every week in
    # a generated plan carries seven day entries, and removing one left race
    # week with a hole where Saturday should be.
    shakeout_km = max(
        RACE_WEEK_SHAKEOUT_MIN_KM,
        min(RACE_WEEK_SHAKEOUT_MAX_KM, round(pre_race_target * 0.25, 1)),
    )
    kept: List[Dict[str, Any]] = []
    for w in workouts:
        if w.get("type") == "long":
            kept.append(_build_shakeout(w["day"], shakeout_km, pace_zones))
        elif w.get("day") == RACE_DAY_NUMBER:
            kept.append(workout_builders.generate_rest_day(w["day"]))
        elif w.get("type") in RUNNING_CARD_TYPES and (w.get("distance") or 0) <= 0:
            # A drained running card is rest, not a session. The
            # sub-threshold conversion below only sees positive distances,
            # so without this branch a 0.0 km "easy" card survives onto the
            # race-week calendar. (``duration_min`` here is a display hint
            # attached to *short* cards — a 0.0 km card gets a 1-minute one —
            # so it marks the junk, it cannot protect it.)
            kept.append(workout_builders.generate_rest_day(w["day"]))
        else:
            kept.append(w)

    # Choose the sessions that survive before sizing them.  The previous order
    # scaled every card and then discarded the thin results, silently throwing
    # away most of the pre-race budget.
    prerace_cap = max(
        1,
        min(
            RACE_WEEK_MAX_PRERACE_RUNS,
            max_runs - 1,
            max(1, int(pre_race_target // RACE_WEEK_SHAKEOUT_MIN_KM)),
        ),
    )
    running = [
        w
        for w in kept
        if w.get("type") not in ("rest", "recovery") and (w.get("distance", 0) or 0) > 0
    ]

    def _keep_priority(w: Dict[str, Any]) -> tuple[int, float]:
        if w.get("is_shakeout"):
            return (0, 0.0)
        if w.get("type") in ("tempo", "interval", "hill"):
            return (1, -(w.get("distance") or 0))
        return (2, -(w.get("distance") or 0))

    running.sort(key=_keep_priority)
    for w in running[prerace_cap:]:
        idx = kept.index(w)
        kept[idx] = workout_builders.generate_rest_day(w["day"])

    # Scale only the days *other than* the shakeout onto the remaining budget —
    # the shakeout is a fixed, deliberately tiny dose and must not absorb the
    # week's drawdown.
    others = [w for w in kept if not w.get("is_shakeout")]
    _scale_down(
        others,
        max(0.0, pre_race_target - shakeout_km),
        pace_zones=pace_zones,
        protect_long=False,
    )

    # A selected taper sharpener must remain an executable quality session.
    # Earlier long-run-relative clamping can leave it at 1-2 km; race week has
    # a six-kilometre pre-race floor, so a 2.5 km sharpener plus the shakeout
    # fits without violating the taper budget.
    for w in kept:
        if (
            w.get("type") in ("tempo", "interval", "hill")
            and 0 < (w.get("distance") or 0) < MIN_VIABLE_QUALITY_KM
        ):
            _set_distance(w, MIN_VIABLE_QUALITY_KM, pace_zones)

    # Convert sub-threshold easy runs to rest — scaling can crush them to a
    # fraction of a kilometre, which isn't worth lacing up for — and drained
    # (0.0 km) cards to rest unconditionally: a card with no distance is not
    # a session, and it was never counted as prerace running. But never
    # eliminate ALL pre-race running: low-volume short-distance plans may
    # have only one tiny run before the race, and rest-only → race is worse
    # than a short shakeout jog.
    prerace_running = sum(
        1
        for w in kept
        if w.get("type") not in ("rest", "recovery") and (w.get("distance") or 0) > 0
    )
    for i, w in enumerate(kept):
        dist = w.get("distance") or 0
        if w.get("type") != "easy" or w.get("is_shakeout"):
            continue
        drained = dist <= 0
        thin = 0 < dist < RACE_WEEK_SHAKEOUT_MIN_KM
        if thin and prerace_cap >= 2:
            # Selection already guaranteed room for this second session. Keep
            # it at the same coherent floor as the shakeout instead of deleting
            # it after sizing and collapsing a nominal 25%-of-peak race week to
            # one token jog.
            _set_distance(w, RACE_WEEK_SHAKEOUT_MIN_KM, pace_zones)
            continue
        if drained or (thin and prerace_running > 1):
            kept[i] = workout_builders.generate_rest_day(w["day"])
            if thin:
                prerace_running -= 1

    # Guarantee the minimum contract after every conversion.  If the second
    # retained stimulus is deliberately short, grow the shakeout (still capped
    # at four kilometres) so race week contains at least a shakeout plus one
    # minimum coherent session's worth of running.
    desired_floor = min(
        pre_race_target,
        RACE_WEEK_SHAKEOUT_MIN_KM * (2 if prerace_cap >= 2 else 1),
    )
    current_prerace = sum(
        w.get("distance", 0) or 0
        for w in kept
        if w.get("type") not in ("rest", "recovery")
    )
    if current_prerace < desired_floor - 0.05:
        shakeout_index = next(
            (i for i, w in enumerate(kept) if w.get("is_shakeout")), None
        )
        if shakeout_index is not None:
            shakeout = kept[shakeout_index]
            grown = min(
                RACE_WEEK_SHAKEOUT_MAX_KM,
                (shakeout.get("distance") or 0) + desired_floor - current_prerace,
            )
            kept[shakeout_index] = _build_shakeout(
                shakeout["day"], round(grown, 1), pace_zones
            )

    race = workout_builders.generate_race_day(
        RACE_DAY_NUMBER,
        target_distance,
        pace_zones,
        is_trail=trail_profile is not None,
    )
    race["coaching_rationale"] = (
        "Everything in this plan was built for today. Trust the taper — "
        "fresh legs always feel a little restless on the start line."
    )

    workouts = sorted(
        [w for w in kept if w.get("day") != RACE_DAY_NUMBER] + [race],
        key=lambda w: w.get("day", 0),
    )
    for w in workouts:
        w.pop("duration_min", None)
    attach_duration_hints(workouts, pace_zones)

    final_week["daily_workouts"] = workouts
    final_week["total_km"] = round(sum(w.get("distance", 0) or 0 for w in workouts), 1)
    final_week["is_race_week"] = True


# A backyard starts on a Saturday morning and runs into Sunday and beyond, so
# the event sits on day 6 rather than day 7 — the plan's last day belongs to
# the race, not to the day after it.
BACKYARD_RACE_DAY_NUMBER = 6


def _install_backyard_race_day(
    training_plan: List[Dict[str, Any]],
    profile: "BackyardProfile",
    pace_zones: Optional[Dict],
    max_runs: int = RACE_WEEK_MAX_PRERACE_RUNS + 1,
) -> None:
    """Close a backyard plan on the event itself (in place).

    Same intent as :func:`_install_race_day` — a plan built backwards from a
    race should end on it — with the calendar shifted a day: the race takes
    Saturday, Sunday is left as rest because for most goals the runner
    is still out on the course, and the shakeout moves to Friday.

    The race is installed after every smoothing pass and never rescaled: its
    size is the runner's goal, not the week's budget.
    """
    from app.contexts.plan.generators.weekly_plan_builder import attach_duration_hints
    from app.contexts.plan.generators.workout_scaler import scale_down as _scale_down
    from app.core.training.tuning import (
        RACE_WEEK_MIN_PRERACE_KM,
        RACE_WEEK_PRERACE_SHARE,
    )

    if not training_plan:
        return
    final_week = training_plan[-1]
    workouts = final_week.get("daily_workouts") or []

    realized_peak = max(
        (
            w.get("total_km", 0) or 0
            for w in training_plan[:-1]
            if not w.get("is_recovery")
        ),
        default=final_week.get("total_km", 0) or 0,
    )
    pre_race_target = max(
        RACE_WEEK_MIN_PRERACE_KM, round(realized_peak * RACE_WEEK_PRERACE_SHARE, 1)
    )
    shakeout_day = BACKYARD_RACE_DAY_NUMBER - 1
    shakeout_km = max(
        RACE_WEEK_SHAKEOUT_MIN_KM,
        min(RACE_WEEK_SHAKEOUT_MAX_KM, round(pre_race_target * 0.25, 1)),
    )

    kept: List[Dict[str, Any]] = []
    for w in workouts:
        day = w.get("day")
        if day == BACKYARD_RACE_DAY_NUMBER:
            continue  # the race takes this day
        if day == shakeout_day:
            kept.append(_build_shakeout(shakeout_day, shakeout_km, pace_zones))
        elif w.get("type") in RUNNING_CARD_TYPES and (w.get("distance") or 0) <= 0:
            # Same rule as the road race week: a drained card is rest.
            kept.append(workout_builders.generate_rest_day(day))
        elif day is not None and day > BACKYARD_RACE_DAY_NUMBER:
            # Still on the course, or sleeping it off. Either way, not training.
            kept.append(workout_builders.generate_rest_day(day))
        else:
            kept.append(w)

    others = [w for w in kept if not w.get("is_shakeout")]
    _scale_down(
        others,
        max(0.0, pre_race_target - shakeout_km),
        pace_zones=pace_zones,
        protect_long=False,
    )
    # Scaling can crush a pre-race session to 0.0 km; render the drained card
    # as the rest day it effectively is (same rule as the road race week).
    kept = [
        workout_builders.generate_rest_day(w.get("day"))
        if w.get("type") in RUNNING_CARD_TYPES and (w.get("distance") or 0) <= 0
        else w
        for w in kept
    ]

    # Frequency budget: the race consumes one of the week's running slots, so
    # at most max_runs - 1 sessions may precede it — shakeout first, then the
    # hardest of what is left. Without this, a low-frequency backyard runner
    # got a race week with more running days than they asked for all block.
    prerace_cap = max(0, min(RACE_WEEK_MAX_PRERACE_RUNS, max_runs - 1))
    running = [
        w
        for w in kept
        if w.get("type") not in ("rest", "recovery") and (w.get("distance", 0) or 0) > 0
    ]
    if len(running) > prerace_cap:

        def _keep_priority(w: Dict[str, Any]) -> int:
            if w.get("is_shakeout"):
                return 0
            if w.get("type") in ("tempo", "interval", "hill"):
                return 1
            return 2

        running.sort(key=_keep_priority)
        for w in running[prerace_cap:]:
            idx = kept.index(w)
            kept[idx] = workout_builders.generate_rest_day(w["day"])

    race = workout_builders.generate_backyard_race_day(
        BACKYARD_RACE_DAY_NUMBER, profile, pace_zones
    )
    race["coaching_rationale"] = (
        "Every simulation in this plan was a rehearsal for the next few hours "
        "— and then for all the hours after those. Start slow enough that the "
        "first loop feels like a mistake."
    )

    workouts = sorted(kept + [race], key=lambda w: w.get("day", 0))
    for w in workouts:
        w.pop("duration_min", None)
    attach_duration_hints(workouts, pace_zones)

    final_week["daily_workouts"] = workouts
    final_week["total_km"] = round(sum(w.get("distance", 0) or 0 for w in workouts), 1)
    final_week["is_race_week"] = True


def _smooth_taper(
    training_plan: List[Dict[str, Any]],
    target_distance: float,
    weeks: int,
    pace_zones: Optional[Dict],
    trail_profile: Optional[TrailProfile] = None,
) -> None:
    """Re-anchor the taper to the *realized* peak so it always descends (in place).

    The taper curve is computed inside ``calculate_weekly_progression`` from the
    progression's high-water mark. But on capped plans (low base / low frequency)
    the week-level 10% pass scales the loading weeks *down* below that high-water
    target, so a taper scaled from the unrealized peak lands too high relative to
    the weeks the runner actually ran — race week sitting at ~70% of the displayed
    peak instead of the intended ~50-55%. This pass rescales each taper week to
    ``taper_curve_fraction × realized_peak`` (the max loading-week total actually
    delivered), draining the excess from the flexible (easy/long) runs. Weeks
    already at or below target are untouched, so well-resourced plans are
    unaffected.
    """
    from app.contexts.plan.generators.weekly_plan_builder import attach_duration_hints
    from app.contexts.plan.generators.workout_scaler import scale_down as _scale_down
    from app.core.training.periodization.mileage_progression import _get_taper_curve
    from app.core.training.periodization.phase_calculator import calculate_phases

    phases = calculate_phases(weeks, target_distance, trail_profile=trail_profile)
    taper_weeks = phases.get("taper", 0)
    if taper_weeks <= 0 or taper_weeks >= len(training_plan):
        return

    loading = training_plan[: len(training_plan) - taper_weeks]
    realized_peak = max(
        (w["total_km"] for w in loading if not w.get("is_recovery")),
        default=0.0,
    )
    if realized_peak <= 0:
        return

    from app.contexts.plan.generators.workout_scaler import (
        reclamp_quality_to_long_run as _reclamp_quality,
    )

    curve = _get_taper_curve(taper_weeks, target_distance, trail_profile=trail_profile)
    taper_plans = training_plan[len(training_plan) - taper_weeks :]
    for i, weekly_plan in enumerate(taper_plans):
        fraction = curve[min(i, len(curve) - 1)]
        target = round(realized_peak * fraction, 1)
        if weekly_plan["total_km"] > target + 0.05:
            workouts = weekly_plan["daily_workouts"]
            for w in workouts:
                w.pop("duration_min", None)
            _scale_down(workouts, target, pace_zones=pace_zones, protect_long=False)
            _reclamp_quality(workouts)
            weekly_plan["total_km"] = round(
                sum(w.get("distance", 0) for w in workouts), 1
            )
            for w in workouts:
                w.pop("duration_min", None)
            attach_duration_hints(workouts, pace_zones)


def _smooth_recovery_dips(
    training_plan: List[Dict[str, Any]],
    pace_zones: Optional[Dict],
) -> None:
    """Keep deload weeks a genuine dip below the surrounding load (in place).

    A recovery week's target is ``RECOVERY_WEEK_RATIO`` of the progression's
    high-water mark. On low-frequency plans for a high base the loading weeks
    fall short of that high-water mark (a 2-3 run week can't physically hold the
    volume), so a deload anchored to the unrealized high-water can land *above*
    the loading weeks around it — a recovery week harder than the work weeks,
    which reads as a broken curve. This pass shrinks any recovery week back to
    ``RECOVERY_WEEK_RATIO`` of the loading week that precedes it, draining the
    excess from its flexible (easy/long) runs. Loading weeks are never touched.
    """
    from app.contexts.plan.generators.weekly_plan_builder import attach_duration_hints
    from app.contexts.plan.generators.workout_scaler import scale_down as _scale_down

    prev_load_total: Optional[float] = None
    for weekly_plan in training_plan:
        if weekly_plan.get("is_recovery"):
            if prev_load_total is not None:
                target = round(
                    prev_load_total * mileage_progression.RECOVERY_WEEK_RATIO, 1
                )
                if weekly_plan["total_km"] > target + 0.05:
                    workouts = weekly_plan["daily_workouts"]
                    # See the note in ``_smooth_taper``: ``scale_down`` skips
                    # workouts carrying a display-only ``duration_min`` hint, so
                    # they must be cleared before the drawdown is distributed.
                    for w in workouts:
                        w.pop("duration_min", None)
                    _scale_down(workouts, target, pace_zones=pace_zones)
                    weekly_plan["total_km"] = round(
                        sum(w.get("distance", 0) for w in workouts), 1
                    )
                    for w in workouts:
                        w.pop("duration_min", None)
                    attach_duration_hints(workouts, pace_zones)
        else:
            prev_load_total = weekly_plan["total_km"]


def _sweep_trivial_sessions(
    training_plan: List[Dict[str, Any]],
    pace_zones: Optional[Dict],
) -> None:
    """Render sub-viable running cards as the sessions they effectively are.

    Three ways a week can end up carrying a card no runner should execute:

    - a **zero**-distance running card — scaling passes can drain a flexible
      session to 0.0 km while the card stays typed ``easy``, so the calendar
      shows an easy run with no distance on it (observed on 5K/10K race weeks
      and, off the schema's guarded path, on a build week). Rendered as rest:
      it was never a run.
    - a **token quality** session — the taper and deload smoothing draws weeks
      down proportionally, and a 2.2 km "tempo" cannot hold warm-up, work, and
      cool-down. Rebuilt as an *easy* run at the same distance: the session
      was already jogging duration, and relabelling keeps the runner's
      frequency intact.
    - a **token easy** run — worst case observed: a 0.3 km easy card in a 10K
      peak week. Rendered as rest, but only when it is not even coherent
      (under a kilometre) *and* the week's median running dose shows the week
      can sustain real sessions — the crushed card is a scaling artifact, not
      the plan's honest shape. A 1.5 km jog in a small week is small-but-real
      and stays: converting it erodes frequency and deflates the ramp
      baseline for no coaching gain.

    The race week itself is skipped: its pre-race days are sized by
    :func:`_install_race_day`, which applies the same rules to its own cards.
    Long runs are never converted — the week's long anchor is load-bearing
    for the plan's invariants, and a sub-viable long run does not occur on the
    grid (the long-run rebuild path resizes it rather than shrinking it to a
    token).

    A week is never left without a runnable session: converting the last one
    would trade a trivial card for a fatal structure-guard failure.
    """
    for weekly_plan in training_plan[:-1]:
        workouts = weekly_plan.get("daily_workouts") or []
        running = [
            w
            for w in workouts
            if w.get("type") in RUNNING_CARD_TYPES and (w.get("distance") or 0) > 0
        ]
        doses = sorted((w.get("distance") or 0) for w in running)
        median_dose = doses[len(doses) // 2] if doses else 0.0
        shedding_week = weekly_plan.get("phase") == "taper" or weekly_plan.get(
            "is_recovery"
        )
        changed = False
        for i, w in enumerate(workouts):
            wtype = w.get("type")
            if wtype not in RUNNING_CARD_TYPES:
                continue
            distance = w.get("distance") or 0
            if wtype in ("tempo", "interval", "hill"):
                if distance < 0:
                    continue
                if distance == 0:
                    # A drained quality card is not a stimulus and not a run.
                    workouts[i] = workout_builders.generate_rest_day(w.get("day"))
                    changed = True
                    continue
                if distance >= MIN_VIABLE_QUALITY_KM:
                    continue
                if not shedding_week:
                    # A loading week keeps its intensity stimulus, however
                    # small: on a micro plan the token session is the plan's
                    # *only* quality work, and relabelling it as easy strips
                    # the plan of intensity entirely.
                    continue
                # A token quality session in a taper/deload week was already
                # jogging duration: relabel it as the easy run it effectively
                # was. Intensity is being shed by design.
                workouts[i] = workout_builders.generate_easy_run(
                    w.get("day"), distance, distance, pace_zones
                )
                changed = True
                continue
            if distance > 0 and distance >= MIN_COHERENT_RUN_KM:
                continue
            if distance > 0 and (
                median_dose < MIN_VIABLE_QUALITY_KM or len(running) <= 1
            ):
                # Not junk: either a borderline-but-real jog in a week that
                # cannot sustain bigger doses, or the week's only run. Both
                # stay — converting them trades a small card for frequency
                # erosion and a deflated ramp baseline.
                continue
            workouts[i] = workout_builders.generate_rest_day(w.get("day"))
            running = [r for r in running if r is not w]
            changed = True
        if changed:
            # The rebuild swaps in fresh cards, so the week's display hints
            # must be refreshed from the final distances — a downgraded
            # token tempo is now an easy run under the 3 km hint threshold.
            for w in workouts:
                w.pop("duration_min", None)
            attach_duration_hints(workouts, pace_zones)
            weekly_plan["daily_workouts"] = workouts
            weekly_plan["total_km"] = round(
                sum(w.get("distance", 0) or 0 for w in workouts), 1
            )
