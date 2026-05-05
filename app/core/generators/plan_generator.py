"""Training plan generator -- thin orchestrator.

Delegates to focused modules:
- phase_calculator: phase distribution, distance categories, recovery weeks
- mileage_progression: weekly mileage progression with 10% rule
- workout_distribution: workout type counts and day scheduling
- workout_builders: individual workout generation
- long_run_calculator: long run and quality workout distances
- weekly_plan_builder: single-week plan assembly, scaling, validation
"""

from typing import List, Dict, Any, Optional

from app.core.generators.beginner_plan_generator import BeginnerPlanGenerator
from app.core.generators.weekly_plan_builder import (
    build_weekly_plan,
    apply_quality_caps,
    allocate_easy_distances,
    build_workout_for_type,
    overlay_key_workout,
    generate_daily_workouts,
)
from app.core.generators.plan_validator import validate_week_plan
from app.core.training.key_workout_library import KeyWorkoutLibrary
from app.core.training.strength_plan import derive_experience_level
from app.core.training import workout_steps as _steps_mod
from app.core.training.vdot_calculator import VDOTCalculator
from app.core.training.quality_caps import (
    MAX_QUALITY_VS_LONG_RUN,
    MAX_EASY_VS_LONG_RUN,
    get_quality_caps as _get_quality_caps,
)
from app.core.training.training_constants import get_hard_ceiling, calculate_week_in_phase
from app.exceptions import ZeroMileageUnsupportedException

# Re-export for any code that imports PHASE_DISTRIBUTIONS from here
from app.core.training.phase_calculator import PHASE_DISTRIBUTIONS  # noqa: F401

from app.core.training import phase_calculator
from app.core.training import mileage_progression
from app.core.training import workout_distribution as workout_dist_mod
from app.core.training import workout_builders
from app.core.training import long_run_calculator


class TrainingPlanGenerator:
    def __init__(self):
        self.workout_types = {
            'easy': {'intensity': 'low', 'description': 'Easy recovery run'},
            'tempo': {'intensity': 'medium', 'description': 'Tempo run at threshold pace'},
            'interval': {'intensity': 'high', 'description': 'High-intensity intervals'},
            'long': {'intensity': 'medium', 'description': 'Long distance run'},
            'hill': {'intensity': 'high', 'description': 'Hill repeats and strength training'},
            'rest': {'intensity': 'rest', 'description': 'Rest day'},
            'strength': {'intensity': 'low', 'description': 'Strength training'}
        }

    # ── Delegating methods (preserve backward-compatible API) ────────────

    def _get_distance_category(self, target_distance: float) -> str:
        return phase_calculator.get_distance_category(target_distance)

    def _calculate_phases(self, weeks: int, target_distance: float = 10.0) -> Dict[str, int]:
        return phase_calculator.calculate_phases(weeks, target_distance)

    def _get_phase(self, week_number: int, phases: Dict[str, int]) -> str:
        return phase_calculator.get_phase(week_number, phases)

    def _is_recovery_week(self, week_number: int, phase: str, phases: Optional[Dict[str, int]] = None) -> bool:
        return phase_calculator.is_recovery_week(week_number, phase, phases)

    def _get_peak_mileage(self, target_distance: float, current_km: float, weeks: int,
                          vdot: Optional[float] = None,
                          profile: Optional[Dict[str, Any]] = None) -> float:
        return mileage_progression.get_peak_mileage(target_distance, current_km, weeks, vdot, profile)

    def _get_ideal_peak(self, target_distance: float, current_km: float, weeks: int) -> float:
        return mileage_progression.get_ideal_peak(target_distance, current_km, weeks)

    def _calculate_weekly_progression(self, current_km: float, target_distance: float,
                                      weeks: int, max_runs: int = 4,
                                      vdot: Optional[float] = None,
                                      profile: Optional[Dict[str, Any]] = None) -> List[float]:
        return mileage_progression.calculate_weekly_progression(
            current_km, target_distance, weeks, max_runs, vdot, profile,
        )

    def _get_workout_distribution(self, total_km: float, max_runs: int, phase: str = 'build',
                                  is_recovery_week: bool = False, week_number: int = 1,
                                  phases: Dict[str, int] = None,
                                  target_distance: float = 10.0,
                                  terrain: Optional[str] = None,
                                  profile: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
        return workout_dist_mod.get_workout_distribution(total_km, max_runs, phase,
                                                         is_recovery_week, week_number,
                                                         phases, target_distance,
                                                         terrain=terrain, profile=profile)

    def _get_workout_distribution_simple(self, total_km: float, max_runs: int) -> Dict[str, int]:
        return workout_dist_mod.get_workout_distribution_simple(total_km, max_runs)

    def _schedule_workout_types(self, distribution: Dict[str, int], phase: str,
                                week_number: int, is_recovery_week: bool) -> List[Optional[str]]:
        return workout_dist_mod.schedule_workout_types(distribution, phase, week_number, is_recovery_week)

    def _get_long_run_ratio_range(self, phase: str, target_distance: float,
                                  weeks: int) -> tuple[float, float]:
        return long_run_calculator.get_long_run_ratio_range(phase, target_distance, weeks)

    def _calculate_long_run_ratio(self, phase: str, week_number: int, phases: Dict[str, int],
                                  target_distance: float, is_recovery_week: bool,
                                  total_weeks: int) -> float:
        return long_run_calculator.calculate_long_run_ratio(phase, week_number, phases,
                                                            target_distance, is_recovery_week,
                                                            total_weeks)

    def _calculate_long_run_distance(self, total_km: float, target_distance: float,
                                     weeks: int = 12, week_number: int = 1,
                                     phase: str = 'build',
                                     is_recovery_week: bool = False,
                                     experience_level: str = 'intermediate',
                                     profile: Optional[Dict[str, Any]] = None) -> float:
        return long_run_calculator.calculate_long_run_distance(
            total_km, target_distance, weeks, week_number, phase,
            is_recovery_week, experience_level, profile)

    def _get_phase_distribution(self, phase: str, target_distance: float = 10.0,
                                terrain: Optional[str] = None) -> Dict[str, float]:
        return long_run_calculator.get_phase_distribution(phase, target_distance, terrain=terrain)

    def _calculate_quality_distances(self, total_km: float, phase: str,
                                     distribution: Dict[str, int], is_recovery_week: bool,
                                     long_run_distance: float = 0,
                                     target_distance: float = 10.0,
                                     terrain: Optional[str] = None) -> Dict[str, float]:
        return long_run_calculator.calculate_quality_distances(total_km, phase, distribution,
                                                               is_recovery_week, long_run_distance,
                                                               target_distance, terrain=terrain)

    def _generate_rest_day(self, day: int) -> Dict[str, Any]:
        return workout_builders.generate_rest_day(day)

    def _generate_recovery_day(self, day: int, phase: str) -> Dict[str, Any]:
        return workout_builders.generate_recovery_day(day, phase)

    def _generate_strength_session(self, day: int, week_number: int, phase: str,
                                   workout_type: str, session_index: int = 0,
                                   experience_level: str = "beginner",
                                   target_distance: float = 0.0) -> Optional[Dict[str, Any]]:
        return workout_builders.generate_strength_session(day, week_number, phase, workout_type,
                                                          session_index, experience_level,
                                                          target_distance)

    def _generate_long_run(self, day: int, distance: float, total_km: float,
                           pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
        return workout_builders.generate_long_run(day, distance, total_km, pace_zones)

    def _generate_easy_run(self, day: int, distance: float, total_km: float,
                           pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
        return workout_builders.generate_easy_run(day, distance, total_km, pace_zones)

    def _generate_tempo_run(self, day: int, distance: float, total_km: float,
                            pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
        return workout_builders.generate_tempo_run(day, distance, total_km, pace_zones)

    def _generate_interval_run(self, day: int, distance: float, total_km: float,
                               pace_zones: Optional[Dict] = None) -> Dict[str, Any]:
        return workout_builders.generate_interval_run(day, distance, total_km, pace_zones)

    def _generate_hill_workout(self, day: int, distance: float = 0) -> Dict[str, Any]:
        return workout_builders.generate_hill_workout(day, distance)

    def _generate_training_tips(self, week_number: int, target_distance: float) -> List[str]:
        return workout_builders.generate_training_tips(week_number, target_distance)

    # ── Delegating methods to extracted modules ─────────────────────────

    @staticmethod
    def _apply_quality_caps(quality_distances: Dict[str, float],
                            long_run_distance: float,
                            target_distance: float,
                            phase: str) -> Dict[str, float]:
        return apply_quality_caps(quality_distances, long_run_distance, target_distance, phase)

    @staticmethod
    def _allocate_easy_distances(remaining_km: float,
                                 quality_total: float,
                                 long_run_distance: float,
                                 easy_runs: int) -> List[float]:
        return allocate_easy_distances(remaining_km, quality_total, long_run_distance, easy_runs)

    def _build_workout_for_type(self, workout_type: str, day_number: int,
                                distance: float, total_km: float,
                                phase: str,
                                pace_zones: Optional[Dict]) -> Dict[str, Any]:
        return build_workout_for_type(workout_type, day_number, distance, total_km, phase, pace_zones)

    @staticmethod
    def _overlay_key_workout(workout: Dict[str, Any], workout_type: str,
                             phase: str, target_distance: float,
                             week_in_phase: int,
                             terrain: Optional[str],
                             pace_zones: Optional[Dict]) -> None:
        return overlay_key_workout(workout, workout_type, phase, target_distance,
                                   week_in_phase, terrain, pace_zones)

    def _generate_daily_workouts(self, week_number: int, total_km: float,
                                 distribution: Dict[str, int],
                                 target_distance: float, weeks: int, phase: str,
                                 is_recovery_week: bool,
                                 vdot: Optional[float] = None,
                                 pace_zones: Optional[Dict] = None,
                                 experience_level: str = "beginner",
                                 week_in_phase: int = 0,
                                 terrain: Optional[str] = None,
                                 profile: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return generate_daily_workouts(
            week_number, total_km, distribution, target_distance, weeks, phase,
            is_recovery_week, vdot=vdot, pace_zones=pace_zones,
            experience_level=experience_level, week_in_phase=week_in_phase,
            terrain=terrain, profile=profile,
        )

    def _validate_week_plan(self, workouts: List[Dict[str, Any]],
                            total_km: float, target_total_km: float,
                            phase: str) -> tuple[bool, str]:
        return validate_week_plan(workouts, total_km, target_total_km, phase)

    def _generate_weekly_plan(self, week_number: int, total_km: float, target_distance: float,
                              max_runs_per_week: int, weeks: int,
                              vdot: Optional[float] = None,
                              pace_zones: Optional[Dict] = None,
                              experience_level: str = "beginner",
                              terrain: Optional[str] = None,
                              profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return build_weekly_plan(
            week_number, total_km, target_distance, max_runs_per_week, weeks,
            vdot=vdot, pace_zones=pace_zones, experience_level=experience_level,
            terrain=terrain, profile=profile,
        )

    # ── Top-level orchestration ─────────────────────────────────────────

    def generate_plan(self, current_km: float, target_distance: float, weeks: int,
                      max_runs_per_week: int = 4, vdot: Optional[float] = None,
                      profile: Optional[Dict[str, Any]] = None,
                      terrain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Generate a comprehensive training plan."""
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

        weekly_progression = self._calculate_weekly_progression(
            current_km, target_distance, weeks, max_runs_per_week, vdot=vdot, profile=profile,
        )

        training_plan = []
        actual_high_water = current_km
        for week in range(1, weeks + 1):
            week_km = weekly_progression[week - 1]
            weekly_plan = build_weekly_plan(
                week, week_km, target_distance, max_runs_per_week, weeks,
                vdot=vdot, pace_zones=pace_zones,
                experience_level=experience_level,
                terrain=terrain,
                profile=profile,
            )

            # Enforce 10% cap against actual high-water mark.
            from app.core.generators.weekly_plan_builder import _set_distance
            is_recovery = weekly_plan.get('is_recovery', False)
            actual_km = weekly_plan['total_km']
            if not is_recovery and actual_high_water > 0:
                ceiling = round(actual_high_water * 1.10, 1)
                if actual_km > ceiling and actual_km > 0:
                    scale = ceiling / actual_km
                    for w in weekly_plan['daily_workouts']:
                        if w.get('distance', 0) > 0:
                            _set_distance(w, w['distance'] * scale)
                    new_total = round(
                        sum(w.get('distance', 0) for w in weekly_plan['daily_workouts']), 1,
                    )
                    if new_total > ceiling:
                        excess = round(new_total - ceiling, 1)
                        largest = max(
                            (w for w in weekly_plan['daily_workouts'] if w.get('distance', 0) > 0),
                            key=lambda w: w['distance'],
                        )
                        _set_distance(largest, largest['distance'] - excess)
                        new_total = round(
                            sum(w.get('distance', 0) for w in weekly_plan['daily_workouts']), 1,
                        )
                    weekly_plan['total_km'] = new_total
            if not is_recovery and weekly_plan['total_km'] > actual_high_water:
                actual_high_water = weekly_plan['total_km']

            training_plan.append(weekly_plan)

        return training_plan
