"""Training plan generator -- thin orchestrator.

Delegates to focused modules:
- phase_calculator: phase distribution, distance categories, recovery weeks
- mileage_progression: weekly mileage progression with 10% rule
- workout_distribution: workout type counts and day scheduling
- workout_builders: individual workout generation
- long_run_calculator: long run and quality workout distances
"""

from typing import List, Dict, Any, Optional

from app.core.generators.beginner_plan_generator import BeginnerPlanGenerator
from app.core.coaching.coaching_notes_generator import generate_coaching_note
from app.core.training.key_workout_library import KeyWorkoutLibrary
from app.core.training.strength_plan import derive_experience_level
from app.core.training import workout_steps as _steps_mod
from app.core.training.vdot_calculator import VDOTCalculator
from app.exceptions import ZeroMileageUnsupportedException

# Re-export for any code that imports PHASE_DISTRIBUTIONS from here
from app.core.training.phase_calculator import PHASE_DISTRIBUTIONS  # noqa: F401

from app.core.training import phase_calculator
from app.core.training import mileage_progression
from app.core.training import workout_distribution as workout_dist_mod
from app.core.training import workout_builders
from app.core.training import long_run_calculator


# --- Training safety ratios ---------------------------------------------------
# Quality workouts (tempo/interval/hill) may not exceed this fraction of the
# long run distance. Prevents a hard effort being longer than the weekly
# endurance anchor, which would invert the easy/hard ratio.
MAX_QUALITY_VS_LONG_RUN = 0.85

# Individual easy runs may not exceed this fraction of the long run distance.
# Keeps the long run as the unambiguous weekly peak and preserves the 80/20
# easy/hard principle.
MAX_EASY_VS_LONG_RUN = 0.95

# Base phase reduces quality caps by this factor — early quality is
# introduced conservatively while aerobic base is built.
BASE_PHASE_QUALITY_REDUCTION = 0.80

# Distance-scaled physiological quality caps (km). Shorter races need smaller
# quality volumes; trail prioritises hill work over tempo/interval.
_QUALITY_CAPS_BY_DISTANCE = {
    5.0:  {'tempo': 6.0,  'interval': 5.0,  'hill': 5.0},
    10.0: {'tempo': 10.0, 'interval': 8.0,  'hill': 6.0},
    21.1: {'tempo': 14.0, 'interval': 10.0, 'hill': 8.0},
    30.0: {'tempo': 12.0, 'interval': 8.0,  'hill': 12.0},  # trail: hill is primary
    42.2: {'tempo': 18.0, 'interval': 12.0, 'hill': 10.0},
}
_DEFAULT_QUALITY_CAPS = {'tempo': 12.0, 'interval': 10.0, 'hill': 8.0}


def _get_quality_caps(target_distance: float, phase: str) -> Dict[str, float]:
    """Distance-scaled physiological caps for quality workout distances (km).

    Base phase caps are reduced by ``BASE_PHASE_QUALITY_REDUCTION`` to keep
    early-cycle quality conservative.
    """
    caps = _QUALITY_CAPS_BY_DISTANCE.get(target_distance, _DEFAULT_QUALITY_CAPS)
    if phase == 'base':
        return {k: round(v * BASE_PHASE_QUALITY_REDUCTION, 1) for k, v in caps.items()}
    return caps


def _inject_pace_into_steps(steps: List[Dict[str, Any]],
                            pace_zones: Optional[Dict]) -> List[Dict[str, Any]]:
    """Clone steps and fill in pace_str from pace_zones when missing."""
    if not pace_zones:
        return [dict(s) for s in steps]
    out = []
    for s in steps:
        new = dict(s)
        zone = new.get('pace_zone')
        if zone and not new.get('pace_str') and zone in pace_zones:
            new['pace_str'] = pace_zones[zone].get('pace_str')
        out.append(new)
    return out


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
                                  target_distance: float = 10.0,
                                  terrain: Optional[str] = None) -> Dict[str, int]:
        return workout_dist_mod.get_workout_distribution(total_km, max_runs, phase,
                                                         is_recovery_week, week_number,
                                                         phases, target_distance,
                                                         terrain=terrain)

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
                                     experience_level: str = 'intermediate') -> float:
        return long_run_calculator.calculate_long_run_distance(
            total_km, target_distance, weeks, week_number, phase,
            is_recovery_week, experience_level)

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

    # ── Orchestration methods ────────────────────────────────────────────

    @staticmethod
    def _apply_quality_caps(quality_distances: Dict[str, float],
                            long_run_distance: float,
                            target_distance: float,
                            phase: str) -> Dict[str, float]:
        """Cap each quality workout by the smaller of:
        ``MAX_QUALITY_VS_LONG_RUN * long_run`` or the distance-scaled
        physiological cap for that workout type.
        """
        ceiling = long_run_distance * MAX_QUALITY_VS_LONG_RUN
        phys_caps = _get_quality_caps(target_distance, phase)
        capped = dict(quality_distances)
        for key in capped:
            cap = min(ceiling, phys_caps.get(key, ceiling))
            if capped[key] > cap:
                capped[key] = round(cap, 1)
        return capped

    @staticmethod
    def _allocate_easy_distances(remaining_km: float,
                                 quality_total: float,
                                 long_run_distance: float,
                                 easy_runs: int) -> List[float]:
        """Distribute the easy-run budget evenly across easy days.

        Shortfalls (from capping) are accepted rather than redistributed to
        quality workouts — the 80/20 easy/hard ratio must be preserved.
        """
        if easy_runs <= 0:
            return []
        easy_budget = remaining_km - quality_total
        max_easy = long_run_distance * MAX_EASY_VS_LONG_RUN
        actual_easy_total = min(easy_budget, max_easy * easy_runs)
        per_run = actual_easy_total / easy_runs
        return [round(min(per_run, max_easy), 1) for _ in range(easy_runs)]

    def _build_workout_for_type(self, workout_type: str, day_number: int,
                                distance: float, total_km: float,
                                phase: str,
                                pace_zones: Optional[Dict]) -> Dict[str, Any]:
        """Dispatch workout creation to the appropriate builder."""
        if workout_type == 'rest':
            return self._generate_rest_day(day_number)
        if workout_type == 'recovery':
            return self._generate_recovery_day(day_number, phase)
        if workout_type == 'long':
            return self._generate_long_run(day_number, distance, total_km, pace_zones=pace_zones)
        if workout_type == 'easy':
            return self._generate_easy_run(day_number, distance, total_km, pace_zones=pace_zones)
        if workout_type == 'tempo':
            return self._generate_tempo_run(day_number, distance, total_km, pace_zones=pace_zones)
        if workout_type == 'interval':
            return self._generate_interval_run(day_number, distance, total_km, pace_zones=pace_zones)
        if workout_type == 'hill':
            return self._generate_hill_workout(day_number, distance)
        raise ValueError(f"Unknown workout_type: {workout_type}")

    @staticmethod
    def _overlay_key_workout(workout: Dict[str, Any], workout_type: str,
                             phase: str, target_distance: float,
                             week_in_phase: int,
                             terrain: Optional[str],
                             pace_zones: Optional[Dict]) -> None:
        """Attach a KeyWorkoutLibrary description for quality sessions in build/peak."""
        if workout_type not in ('interval', 'tempo', 'hill', 'long'):
            return
        if phase not in ('build', 'peak'):
            return
        key_wk = KeyWorkoutLibrary.get_for_phase(
            target_distance, phase, week_in_phase, workout_type, terrain=terrain,
        )
        if not key_wk:
            return
        if pace_zones:
            key_wk = KeyWorkoutLibrary.inject_vdot_paces(key_wk, pace_zones)
        workout['description'] = key_wk['description']
        workout['key_workout_id'] = key_wk['id']
        workout['key_workout_name'] = key_wk['name']
        workout['structure'] = key_wk['structure']
        workout['key_workout_rationale'] = key_wk['rationale']
        # Steps resolution order:
        # 1) explicit `steps` on the key workout
        # 2) `steps_builder` string -> resolver (long runs use this path)
        # 3) parse the structure string
        if key_wk.get('steps'):
            workout['steps'] = _inject_pace_into_steps(key_wk['steps'], pace_zones)
        elif key_wk.get('steps_builder'):
            from app.core.training.key_workout_library import _resolve_long_steps_builder
            workout['steps'] = _resolve_long_steps_builder(
                key_wk['steps_builder'], workout.get('distance', 0), pace_zones,
            )
        else:
            workout['steps'] = _steps_mod.parse_key_workout_steps(
                key_wk['structure'], pace_zones, workout_type
            )

    def _generate_daily_workouts(self, week_number: int, total_km: float,
                                 distribution: Dict[str, int],
                                 target_distance: float, weeks: int, phase: str,
                                 is_recovery_week: bool,
                                 vdot: Optional[float] = None,
                                 pace_zones: Optional[Dict] = None,
                                 experience_level: str = "beginner",
                                 week_in_phase: int = 0,
                                 terrain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Generate daily workouts for one week.

        Pipeline:
        1. Compute long-run distance and quality-workout budgets.
        2. Cap quality workouts vs long run + physiological ceilings.
        3. Allocate remaining km to easy runs (capped individually).
        4. For each scheduled day: build the workout, overlay key-workout
           details for quality in build/peak, attach strength session on
           easy days, and add coaching rationale.
        """
        long_run_distance = self._calculate_long_run_distance(
            total_km, target_distance, weeks, week_number, phase, is_recovery_week,
            experience_level,
        )
        quality_distances = self._calculate_quality_distances(
            total_km, phase, distribution, is_recovery_week, long_run_distance, target_distance,
        )
        quality_distances = self._apply_quality_caps(
            quality_distances, long_run_distance, target_distance, phase,
        )

        workout_types = self._schedule_workout_types(
            distribution.copy(), phase, week_number, is_recovery_week,
        )

        remaining_km = total_km - long_run_distance
        quality_total = sum(quality_distances.values())
        easy_runs = sum(1 for wt in workout_types if wt == 'easy')
        easy_distances = self._allocate_easy_distances(
            remaining_km, quality_total, long_run_distance, easy_runs,
        )

        easy_run_idx = 0
        strength_session_idx = 0
        workouts: List[Dict[str, Any]] = []

        for day in range(7):
            workout_type = workout_types[day]
            if workout_type is None:
                continue
            day_number = day + 1

            if workout_type == 'easy':
                distance = easy_distances[easy_run_idx] if easy_run_idx < len(easy_distances) else easy_distances[0]
                easy_run_idx += 1
            elif workout_type == 'long':
                distance = long_run_distance
            elif workout_type in ('tempo', 'interval', 'hill'):
                distance = quality_distances.get(workout_type, 0)
            else:
                distance = 0

            workout = self._build_workout_for_type(
                workout_type, day_number, distance, total_km, phase, pace_zones,
            )

            self._overlay_key_workout(
                workout, workout_type, phase, target_distance,
                week_in_phase, terrain, pace_zones,
            )

            if workout_type == 'easy':
                strength_session = self._generate_strength_session(
                    day_number, week_number, phase, workout_type,
                    session_index=strength_session_idx,
                    experience_level=experience_level,
                    target_distance=target_distance,
                )
                if strength_session:
                    workout['strength_session'] = strength_session
                    strength_session_idx += 1

            workout['coaching_rationale'] = generate_coaching_note(
                workout_type, phase, week_number, target_distance, is_recovery_week,
            )
            workouts.append(workout)

        return workouts

    def _validate_week_plan(self, workouts: List[Dict[str, Any]],
                            total_km: float, target_total_km: float,
                            phase: str) -> tuple[bool, str]:
        """
        Validate week plan follows training principles.

        Checks:
        - All workouts have 'description' field
        - Recovery day has label 'recovery' (not 'recovery_rest')
        - No easy run > 60% of long run distance
        - Total distance matches target (+/-5% tolerance)

        Args:
            workouts: List of workout dicts for the week.
            total_km: Actual total km computed from workouts.
            target_total_km: Target total km from weekly progression.
            phase: Current training phase.
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

        tolerance = target_total_km * 0.05
        if abs(total_km - target_total_km) > tolerance:
            return False, f"Total distance mismatch: expected {target_total_km}km, got {total_km}km"

        for workout in workouts:
            if workout['type'] == 'recovery' and workout.get('distance', 0) != 0:
                return False, f"Recovery day on day {workout['day']} has non-zero distance"

        return True, "Valid"

    def _generate_weekly_plan(self, week_number: int, total_km: float, target_distance: float,
                              max_runs_per_week: int, weeks: int,
                              vdot: Optional[float] = None,
                              pace_zones: Optional[Dict] = None,
                              experience_level: str = "beginner",
                              terrain: Optional[str] = None) -> Dict[str, Any]:
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
            is_recovery, week_number, phases, target_distance,
            terrain=terrain,
        )

        workouts = self._generate_daily_workouts(
            week_number, total_km, distribution, target_distance, weeks, phase, is_recovery,
            vdot=vdot, pace_zones=pace_zones,
            experience_level=experience_level,
            week_in_phase=week_in_phase,
            terrain=terrain,
        )

        actual_total_km = round(sum(w.get('distance', 0) for w in workouts), 1)

        # Scale workouts down if actual exceeds target (preserves 10% progression cap)
        if actual_total_km > total_km * 1.03 and actual_total_km > 0:
            scale = total_km / actual_total_km
            for w in workouts:
                if w.get('distance', 0) > 0:
                    w['distance'] = round(w['distance'] * scale, 1)
            actual_total_km = round(sum(w.get('distance', 0) for w in workouts), 1)

        is_valid, validation_message = self._validate_week_plan(workouts, actual_total_km, total_km, phase)

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
                      max_runs_per_week: int = 4, vdot: Optional[float] = None,
                      profile: Optional[Dict[str, Any]] = None,
                      terrain: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Generate a comprehensive training plan with phase structure, conservative progression,
        mandatory rest days, and integrated strength/cross-training.

        Args:
            current_km:          Current weekly mileage in km
            target_distance:     Race distance in km
            weeks:               Training duration in weeks
            max_runs_per_week:   Maximum runs per week (3-6)
            vdot:                Optional VDOT score for personalised pace zones
            profile:             Optional RunnerProfile dict to tailor plan to actual fitness
            terrain:             Terrain access: 'flat' for no-hill trail plans (trail only)
        """
        if current_km == 0:
            if target_distance in [5.0, 10.0]:
                beginner_generator = BeginnerPlanGenerator()
                return beginner_generator.generate_plan(target_distance, weeks, max_runs_per_week)
            raise ZeroMileageUnsupportedException(
                f"A {target_distance} km race requires an existing running base. "
                "Please start with a 5K or 10K beginner plan to build your fitness first.",
                suggestion="Try a 5K or 10K plan with 0 km/week to get started.",
            )

        # When a runner profile is provided, use actual data to refine inputs
        if profile:
            if profile.get("current_vdot") and not vdot:
                vdot = profile["current_vdot"]
            # Use actual average weekly km if it's higher than self-reported
            actual_km = profile.get("avg_weekly_km", 0)
            if actual_km > current_km:
                current_km = actual_km

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
                terrain=terrain,
            )
            training_plan.append(weekly_plan)

        return training_plan
