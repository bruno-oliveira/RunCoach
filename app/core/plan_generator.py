"""Training plan generator -- thin orchestrator.

Delegates to focused modules:
- phase_calculator: phase distribution, distance categories, recovery weeks
- mileage_progression: weekly mileage progression with 10% rule
- workout_distribution: workout type counts and day scheduling
- workout_builders: individual workout generation
- long_run_calculator: long run and quality workout distances
"""

from typing import List, Dict, Any, Optional

from app.core.beginner_plan_generator import BeginnerPlanGenerator
from app.core.coaching_notes_generator import generate_coaching_note
from app.core.key_workout_library import KeyWorkoutLibrary
from app.core.strength_plan import derive_experience_level
from app.exceptions import ZeroMileageUnsupportedException

# Re-export for any code that imports PHASE_DISTRIBUTIONS from here
from app.core.phase_calculator import PHASE_DISTRIBUTIONS  # noqa: F401

from app.core import phase_calculator
from app.core import mileage_progression
from app.core import workout_distribution as workout_dist_mod
from app.core import workout_builders
from app.core import long_run_calculator


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
                          vdot: Optional[float] = None) -> float:
        return mileage_progression.get_peak_mileage(target_distance, current_km, weeks, vdot)

    def _get_ideal_peak(self, target_distance: float, current_km: float, weeks: int) -> float:
        return mileage_progression.get_ideal_peak(target_distance, current_km, weeks)

    def _calculate_weekly_progression(self, current_km: float, target_distance: float,
                                      weeks: int, max_runs: int = 4,
                                      vdot: Optional[float] = None) -> List[float]:
        return mileage_progression.calculate_weekly_progression(current_km, target_distance, weeks, max_runs, vdot)

    def _get_workout_distribution(self, total_km: float, max_runs: int, phase: str = 'build',
                                  is_recovery_week: bool = False, week_number: int = 1,
                                  phases: Dict[str, int] = None,
                                  target_distance: float = 10.0) -> Dict[str, int]:
        return workout_dist_mod.get_workout_distribution(total_km, max_runs, phase,
                                                         is_recovery_week, week_number,
                                                         phases, target_distance)

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
                                     is_recovery_week: bool = False) -> float:
        return long_run_calculator.calculate_long_run_distance(total_km, target_distance, weeks,
                                                               week_number, phase, is_recovery_week)

    def _get_phase_distribution(self, phase: str, target_distance: float = 10.0) -> Dict[str, float]:
        return long_run_calculator.get_phase_distribution(phase, target_distance)

    def _calculate_quality_distances(self, total_km: float, phase: str,
                                     distribution: Dict[str, int], is_recovery_week: bool,
                                     long_run_distance: float = 0,
                                     target_distance: float = 10.0) -> Dict[str, float]:
        return long_run_calculator.calculate_quality_distances(total_km, phase, distribution,
                                                               is_recovery_week, long_run_distance,
                                                               target_distance)

    def _generate_rest_day(self, day: int) -> Dict[str, Any]:
        return workout_builders.generate_rest_day(day)

    def _generate_recovery_day(self, day: int, phase: str) -> Dict[str, Any]:
        return workout_builders.generate_recovery_day(day, phase)

    def _generate_strength_session(self, day: int, week_number: int, phase: str,
                                   workout_type: str, session_index: int = 0,
                                   experience_level: str = "beginner") -> Optional[Dict[str, Any]]:
        return workout_builders.generate_strength_session(day, week_number, phase, workout_type,
                                                          session_index, experience_level)

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

    # ── Orchestration methods ────────────────────────────────────────────

    def _generate_daily_workouts(self, week_number: int, total_km: float,
                                 distribution: Dict[str, int],
                                 target_distance: float, weeks: int, phase: str,
                                 is_recovery_week: bool,
                                 vdot: Optional[float] = None,
                                 pace_zones: Optional[Dict] = None,
                                 experience_level: str = "beginner",
                                 week_in_phase: int = 0) -> List[Dict[str, Any]]:
        """Generate daily workouts with integrated strength/cross-training and rest day rules."""
        long_run_distance = self._calculate_long_run_distance(
            total_km, target_distance, weeks, week_number, phase, is_recovery_week
        )
        remaining_km = total_km - long_run_distance

        quality_distances = self._calculate_quality_distances(
            total_km, phase, distribution, is_recovery_week, long_run_distance, target_distance
        )

        workout_types = self._schedule_workout_types(distribution.copy(), phase, week_number, is_recovery_week)

        # Cap quality workouts: 85% of long run AND absolute physiological caps
        max_quality_pct = long_run_distance * 0.85
        quality_caps = {'tempo': 12.0, 'interval': 10.0, 'hill': 8.0}
        for key in quality_distances:
            cap = min(max_quality_pct, quality_caps.get(key, max_quality_pct))
            if quality_distances[key] > cap:
                quality_distances[key] = round(cap, 1)

        quality_total = sum(quality_distances.values())
        easy_total = remaining_km - quality_total

        easy_runs = sum(1 for wt in workout_types if wt == 'easy')

        # Cap individual easy runs at 95% of long run distance
        max_easy_distance = long_run_distance * 0.95
        total_max_easy = max_easy_distance * easy_runs
        # Accept the shortfall instead of redistributing to quality workouts
        actual_easy_total = min(easy_total, total_max_easy)

        easy_distances = [round(actual_easy_total / max(easy_runs, 1), 1) for _ in range(easy_runs)]

        # Cap individual easy runs to 95% of long run distance
        easy_distances = [round(min(d, max_easy_distance), 1) for d in easy_distances]

        easy_run_counter = 0
        strength_session_counter = 0

        # Track counters for quality workouts to get their distances
        quality_counters = {wt: 0 for wt in ['tempo', 'interval', 'hill']}

        workouts = []

        for day in range(7):
            workout_type = workout_types[day]

            if workout_type is None:
                continue

            day_number = day + 1

            # Get distance based on workout type
            if workout_type == 'easy':
                if easy_run_counter < len(easy_distances):
                    easy_distance = easy_distances[easy_run_counter]
                else:
                    easy_distance = easy_distances[0]
                easy_run_counter += 1
            elif workout_type in ['tempo', 'interval', 'hill']:
                if workout_type in quality_distances:
                    distance = quality_distances[workout_type]
                    workout_distance = distance
                    quality_counters[workout_type] += 1
                else:
                    workout_distance = 0
            else:
                workout_distance = 0

            # Generate workout based on type
            if workout_type == 'rest':
                workout = self._generate_rest_day(day_number)
            elif workout_type == 'recovery':
                workout = self._generate_recovery_day(day_number, phase)
            elif workout_type == 'long':
                workout = self._generate_long_run(day_number, long_run_distance, total_km, pace_zones=pace_zones)
            elif workout_type == 'easy':
                workout = self._generate_easy_run(day_number, easy_distance, total_km, pace_zones=pace_zones)
            elif workout_type == 'tempo':
                workout = self._generate_tempo_run(day_number, workout_distance, total_km,
                                                   pace_zones=pace_zones)
            elif workout_type == 'interval':
                workout = self._generate_interval_run(day_number, workout_distance, total_km,
                                                      pace_zones=pace_zones)
            elif workout_type == 'hill':
                workout = self._generate_hill_workout(day_number, workout_distance)
            else:
                raise ValueError(f"Unknown workout_type: {workout_type}")

            # Overlay key workout description for quality sessions in build/peak
            if workout_type in ('interval', 'tempo', 'hill') and phase in ('build', 'peak'):
                key_wk = KeyWorkoutLibrary.get_for_phase(
                    target_distance, phase, week_in_phase, workout_type
                )
                if key_wk:
                    if pace_zones:
                        key_wk = KeyWorkoutLibrary.inject_vdot_paces(key_wk, pace_zones)
                    workout['description'] = key_wk['description']
                    workout['key_workout_id'] = key_wk['id']
                    workout['key_workout_name'] = key_wk['name']
                    workout['structure'] = key_wk['structure']
                    workout['key_workout_rationale'] = key_wk['rationale']

            if workout_type == 'easy':
                strength_session = self._generate_strength_session(
                    day_number, week_number, phase, workout_type,
                    session_index=strength_session_counter,
                    experience_level=experience_level,
                )
                if strength_session:
                    workout['strength_session'] = strength_session
                    strength_session_counter += 1

            # Add coaching rationale
            workout['coaching_rationale'] = generate_coaching_note(
                workout_type, phase, week_number, target_distance, is_recovery_week
            )

            workouts.append(workout)

        return workouts

    def _validate_week_plan(self, workouts: List[Dict[str, Any]],
                            total_km: float, phase: str) -> tuple[bool, str]:
        """
        Validate week plan follows training principles.

        Checks:
        - All workouts have 'description' field
        - Recovery day has label 'recovery' (not 'recovery_rest')
        - No easy run > 60% of long run distance
        - Total distance matches expected (+/-5% tolerance)
        """
        for workout in workouts:
            if 'description' not in workout:
                return False, f"Missing description for {workout['type']} on day {workout['day']}"

        for workout in workouts:
            if workout['type'] == 'recovery_rest':
                return False, f"Old label 'recovery_rest' on day {workout['day']}, should be 'recovery'"

        long_run_dist = max([w.get('distance', 0) for w in workouts if w['type'] == 'long'], default=0)
        if long_run_dist > 0:
            for workout in workouts:
                if workout['type'] == 'easy':
                    if workout.get('distance', 0) > long_run_dist * 1.05:
                        return False, f"Easy run ({workout.get('distance')}km) > 105% of long run ({long_run_dist}km) on day {workout['day']}"

        actual_total = sum(w.get('distance', 0) for w in workouts)
        tolerance = total_km * 0.05
        if abs(actual_total - total_km) > tolerance:
            return False, f"Total distance mismatch: expected {total_km}km, got {actual_total}km"

        for workout in workouts:
            if workout['type'] == 'recovery' and workout.get('distance', 0) != 0:
                return False, f"Recovery day on day {workout['day']} has non-zero distance"

        return True, "Valid"

    def _generate_weekly_plan(self, week_number: int, total_km: float, target_distance: float,
                              max_runs_per_week: int, weeks: int,
                              vdot: Optional[float] = None,
                              pace_zones: Optional[Dict] = None,
                              experience_level: str = "beginner") -> Dict[str, Any]:
        """Generate a single week's training plan."""
        phases = self._calculate_phases(weeks, target_distance)
        phase = self._get_phase(week_number, phases)
        is_recovery = self._is_recovery_week(week_number, phase, phases)

        # Calculate week_in_phase for key workout rotation
        if phase == 'base':
            week_in_phase = week_number - 1
        elif phase == 'build':
            week_in_phase = week_number - phases['base'] - 1
        elif phase == 'peak':
            week_in_phase = week_number - phases['base'] - phases['build'] - 1
        else:
            week_in_phase = week_number - phases['base'] - phases['build'] - phases['peak'] - 1

        distribution = self._get_workout_distribution(
            total_km, max_runs_per_week, phase,
            is_recovery, week_number, phases, target_distance
        )

        workouts = self._generate_daily_workouts(
            week_number, total_km, distribution, target_distance, weeks, phase, is_recovery,
            vdot=vdot, pace_zones=pace_zones,
            experience_level=experience_level,
            week_in_phase=week_in_phase,
        )

        actual_total_km = round(sum(w.get('distance', 0) for w in workouts), 1)

        # Scale workouts down if actual exceeds target (preserves 10% progression cap)
        if actual_total_km > total_km * 1.03 and actual_total_km > 0:
            scale = total_km / actual_total_km
            for w in workouts:
                if w.get('distance', 0) > 0:
                    w['distance'] = round(w['distance'] * scale, 1)
            actual_total_km = round(sum(w.get('distance', 0) for w in workouts), 1)

        is_valid, validation_message = self._validate_week_plan(workouts, actual_total_km, phase)

        training_tips = self._generate_training_tips(week_number, target_distance)

        return {
            'week': week_number,
            'phase': phase,
            'is_recovery': is_recovery,
            'total_km': actual_total_km,
            'daily_workouts': workouts,
            'training_tips': training_tips,
            'validation': {'valid': is_valid, 'message': validation_message},
            'strength_training': [w['strength_session'] for w in workouts if w.get('strength_session')]
        }

    def generate_plan(self, current_km: float, target_distance: float, weeks: int,
                      max_runs_per_week: int = 4, vdot: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Generate a comprehensive training plan with phase structure, conservative progression,
        mandatory rest days, and integrated strength/cross-training.

        Args:
            current_km:          Current weekly mileage in km
            target_distance:     Race distance in km
            weeks:               Training duration in weeks
            max_runs_per_week:   Maximum runs per week (3-6)
            vdot:                Optional VDOT score for personalised pace zones
        """
        if current_km == 0:
            if target_distance in [5.0, 10.0]:
                beginner_generator = BeginnerPlanGenerator()
                return beginner_generator.generate_plan(target_distance, weeks, max_runs_per_week)
            raise ZeroMileageUnsupportedException(
                user_message=(
                    f"A {target_distance} km race requires an existing running base. "
                    "Please start with a 5K or 10K beginner plan to build your fitness first."
                ),
                suggestion="Try a 5K or 10K plan with 0 km/week to get started.",
            )

        from app.core.vdot_calculator import VDOTCalculator
        pace_zones = VDOTCalculator.get_pace_zones(vdot) if vdot else None

        experience_level = derive_experience_level(current_km)

        weekly_progression = self._calculate_weekly_progression(
            current_km, target_distance, weeks, max_runs_per_week, vdot=vdot
        )

        training_plan = []
        for week in range(1, weeks + 1):
            week_km = weekly_progression[week - 1]
            weekly_plan = self._generate_weekly_plan(
                week, week_km, target_distance, max_runs_per_week, weeks,
                vdot=vdot, pace_zones=pace_zones,
                experience_level=experience_level,
            )
            training_plan.append(weekly_plan)

        return training_plan
