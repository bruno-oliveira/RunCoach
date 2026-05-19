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

from typing import List, Dict, Any, Optional

from app.contexts.plan.generators.beginner_plan_generator import BeginnerPlanGenerator
from app.contexts.plan.generators.weekly_plan_builder import build_weekly_plan
from app.core.training.strength_plan import derive_experience_level
from app.core.training.trail_profile import (
    TrailProfile,
    classify_trail,
)
from app.core.training.vdot_calculator import VDOTCalculator
from app.core.training import mileage_progression
from app.exceptions import ZeroMileageUnsupportedException

# Re-export for any code that imports PHASE_DISTRIBUTIONS from here
from app.core.training.phase_calculator import PHASE_DISTRIBUTIONS  # noqa: F401


class TrainingPlanGenerator:
    def generate_plan(self, current_km: float, target_distance: float, weeks: int,
                      max_runs_per_week: int = 4, vdot: Optional[float] = None,
                      profile: Optional[Dict[str, Any]] = None,
                      terrain: Optional[str] = None,
                      trail_profile: Optional[TrailProfile] = None) -> List[Dict[str, Any]]:
        """Generate a comprehensive training plan.

        Trail/ultra plans pass ``trail_profile``; legacy callsites that pass
        ``target_distance=30.0`` (with optional ``terrain``) get a default
        profile constructed here so back-compat is preserved.
        """
        # Back-compat: synthesize a TrailProfile for legacy 30 km callers.
        if trail_profile is None and target_distance == 30.0:
            elev = 200.0 if terrain == "flat" else 1000.0
            trail_profile = classify_trail(target_distance, elev)
        if current_km == 0:
            if target_distance in [5.0, 10.0]:
                beginner_generator = BeginnerPlanGenerator()
                return beginner_generator.generate_plan(target_distance, weeks, max_runs_per_week)
            raise ZeroMileageUnsupportedException(
                f"A {target_distance} km race requires an existing running base. "
                "Please start with a 5K or 10K beginner plan to build your fitness first.",
                suggestion="Try a 5K or 10K plan with 0 km/week to get started.",
            )

        if profile:
            if profile.get("current_vdot") and not vdot:
                vdot = profile["current_vdot"]
            actual_km = profile.get("avg_weekly_km", 0)
            if actual_km > current_km:
                current_km = actual_km

        pace_zones = VDOTCalculator.get_pace_zones(vdot) if vdot else None

        experience_level = derive_experience_level(current_km)

        weekly_progression = mileage_progression.calculate_weekly_progression(
            current_km, target_distance, weeks, max_runs_per_week, vdot, profile,
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
        for week in range(1, weeks + 1):
            week_km = weekly_progression[week - 1]
            weekly_plan = build_weekly_plan(
                week, week_km, target_distance, max_runs_per_week, weeks,
                vdot=vdot, pace_zones=pace_zones,
                experience_level=experience_level,
                terrain=downstream_terrain,
                trail_profile=trail_profile,
                profile=profile,
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
                _set_distance, _is_prescriptive, attach_duration_hints,
            )
            is_recovery = weekly_plan.get('is_recovery', False)
            actual_km = weekly_plan['total_km']
            if not is_recovery and actual_high_water > 0:
                ceiling = actual_high_water * mileage_progression.WEEK_OVER_WEEK_CAP
                if actual_km > ceiling and actual_km > 0:
                    flexible = [
                        w for w in weekly_plan['daily_workouts']
                        if w.get('type') in ('easy', 'long')
                        and not _is_prescriptive(w)
                        and w.get('distance', 0) > 0
                    ]
                    fixed_km = sum(
                        w.get('distance', 0)
                        for w in weekly_plan['daily_workouts']
                        if w not in flexible and w.get('distance', 0) > 0
                    )
                    flexible_km = sum(w['distance'] for w in flexible)
                    target_flexible = max(0.0, ceiling - fixed_km)
                    if flexible and flexible_km > 0 and target_flexible < flexible_km:
                        scale = target_flexible / flexible_km
                        for w in flexible:
                            _set_distance(w, w['distance'] * scale, pace_zones)
                    # If rounding still leaves a tiny overage, trim from the
                    # largest flexible workout to respect the 10% cap.
                    new_total_exact = sum(
                        w.get('distance', 0) for w in weekly_plan['daily_workouts']
                    )
                    if new_total_exact > ceiling + 0.01 and flexible:
                        largest = max(flexible, key=lambda w: w.get('distance', 0))
                        trim = new_total_exact - ceiling
                        _set_distance(largest, max(0.1, largest.get('distance', 0) - trim), pace_zones)
                    new_total = round(
                        sum(w.get('distance', 0) for w in weekly_plan['daily_workouts']), 1,
                    )
                    weekly_plan['total_km'] = new_total

            # Week-level scaling above can move a workout across the 3 km
            # display boundary; refresh duration hints from final distances.
            for w in weekly_plan['daily_workouts']:
                w.pop('duration_min', None)
            attach_duration_hints(weekly_plan['daily_workouts'], pace_zones)

            if not is_recovery and weekly_plan['total_km'] > actual_high_water:
                actual_high_water = weekly_plan['total_km']

            training_plan.append(weekly_plan)

        return training_plan
