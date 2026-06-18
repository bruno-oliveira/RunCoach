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

from typing import Any, Dict, List, Optional

from app.contexts.plan.generators.beginner_plan_generator import BeginnerPlanGenerator
from app.contexts.plan.generators.weekly_plan_builder import build_weekly_plan
from app.core.training import mileage_progression

# Re-export for any code that imports PHASE_DISTRIBUTIONS from here
from app.core.training.phase_calculator import PHASE_DISTRIBUTIONS  # noqa: F401
from app.core.training.strength_plan import derive_experience_level
from app.core.training.trail_profile import (
    TRAIL_SENTINEL_KM,
    TrailProfile,
    classify_trail,
)
from app.core.training.vdot_calculator import VDOTCalculator
from app.exceptions import ZeroMileageUnsupportedException


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
    ) -> List[Dict[str, Any]]:
        """Generate a comprehensive training plan.

        Trail/ultra plans pass ``trail_profile``; legacy callsites that pass
        ``target_distance=30.0`` (with optional ``terrain``) get a default
        profile constructed here so back-compat is preserved.

        ``intensive_weekend_enabled`` opts a trail plan into an Intensive
        Training Weekend block on its final peak week (off by default).
        """
        # Back-compat: synthesize a TrailProfile for legacy 30 km callers.
        if trail_profile is None and target_distance == TRAIL_SENTINEL_KM:
            elev = 200.0 if terrain == "flat" else 1000.0
            trail_profile = classify_trail(target_distance, elev)
        if current_km == 0:
            if target_distance in [5.0, 10.0]:
                beginner_generator = BeginnerPlanGenerator()
                return beginner_generator.generate_plan(
                    target_distance, weeks, max_runs_per_week
                )
            raise ZeroMileageUnsupportedException(
                f"A {target_distance} km race requires an existing running base. "
                "Please start with a 5K or 10K beginner plan to build your fitness first.",
                suggestion="Try a 5K or 10K plan with 0 km/week to get started.",
            )

        pace_zones = VDOTCalculator.get_pace_zones(vdot) if vdot else None

        experience_level = derive_experience_level(current_km)

        weekly_progression = mileage_progression.calculate_weekly_progression(
            current_km,
            target_distance,
            weeks,
            max_runs_per_week,
            vdot,
            trail_profile=trail_profile,
        )

        # Downstream weekly_plan_builder still keys off the legacy ``terrain``
        # string; expose the elevation_class so flat/rolling/hilly/mountainous
        # all dispatch correctly without a wider signature change.
        downstream_terrain = (
            terrain
            if terrain is not None
            else (trail_profile.elevation_class if trail_profile is not None else None)
        )

        training_plan = []
        actual_high_water = current_km
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
                        if w.get("type") in ("easy", "long")
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
                        scale = target_flexible / flexible_km
                        for w in flexible:
                            _set_distance(w, w["distance"] * scale, pace_zones)
                    # If rounding still leaves a tiny overage, trim from the
                    # largest flexible workout to respect the 10% cap.
                    new_total_exact = sum(
                        w.get("distance", 0) for w in weekly_plan["daily_workouts"]
                    )
                    if new_total_exact > ceiling + 0.01 and flexible:
                        largest = max(flexible, key=lambda w: w.get("distance", 0))
                        trim = new_total_exact - ceiling
                        _set_distance(
                            largest,
                            max(0.1, largest.get("distance", 0) - trim),
                            pace_zones,
                        )
                    new_total = round(
                        sum(
                            w.get("distance", 0) for w in weekly_plan["daily_workouts"]
                        ),
                        1,
                    )
                    weekly_plan["total_km"] = new_total

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

        return training_plan


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
    from app.core.training.mileage_progression import _get_taper_curve
    from app.core.training.phase_calculator import calculate_phases

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

    curve = _get_taper_curve(taper_weeks, target_distance, trail_profile=trail_profile)
    taper_plans = training_plan[len(training_plan) - taper_weeks :]
    for i, weekly_plan in enumerate(taper_plans):
        fraction = curve[min(i, len(curve) - 1)]
        target = round(realized_peak * fraction, 1)
        if weekly_plan["total_km"] > target + 0.05:
            workouts = weekly_plan["daily_workouts"]
            # Taper the long run down in proportion too (protect_long=False) so a
            # deliberately light race-week isn't left with a dominant long run
            # while its easy runs collapse to the floor.
            _scale_down(workouts, target, pace_zones=pace_zones, protect_long=False)
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
                    _scale_down(workouts, target, pace_zones=pace_zones)
                    weekly_plan["total_km"] = round(
                        sum(w.get("distance", 0) for w in workouts), 1
                    )
                    for w in workouts:
                        w.pop("duration_min", None)
                    attach_duration_hints(workouts, pace_zones)
        else:
            prev_load_total = weekly_plan["total_km"]
