"""
Performance Training Plan Generator

Generates speed-focused training plans for experienced runners targeting
race time improvements.  Delegates to shared core modules for periodization
and mileage progression, then layers performance-specific pace zones and
segment-based workout structure.
"""

from typing import List, Dict, Any, Optional

from app.core.coaching.coaching_notes_generator import generate_coaching_note
from app.core.training import phase_calculator
from app.core.training import mileage_progression
from app.core.training.key_workout_library import (
    KeyWorkoutLibrary,
    overlay_key_workout as _overlay_key_workout_shared,
)
from app.core.training.quality_caps import enforce_week_caps
from app.core.training.training_constants import calculate_week_in_phase
from app.core.training.vdot_calculator import VDOTCalculator
from app.utils import format_pace as _shared_format_pace

from .performance_workout_builders import (
    _regenerate_description,
    generate_easy_run,
    generate_fartlek_workout,
    generate_long_run,
    generate_race_pace_workout,
    generate_tempo_workout,
    generate_vo2max_workout,
    reconcile_workout_after_cap,
)


# Performance-specific phase metadata (quality_percent drives how many
# quality sessions appear each week; descriptions shown in the UI).
_PHASE_METADATA = {
    'base':  {'quality_percent': 30, 'description': 'Build aerobic foundation'},
    'build': {'quality_percent': 50, 'description': 'Add intensity and volume'},
    'peak':  {'quality_percent': 60, 'description': 'Peak intensity and sharpness'},
    'taper': {'quality_percent': 40, 'description': 'Reduce volume, maintain sharpness'},
}

# Map performance workout types to KeyWorkoutLibrary types for overlay.
# Fartlek has no library equivalent and stays formulaic.
_LIBRARY_TYPE_MAP = {
    'vo2max': 'interval',
    'tempo': 'tempo',
    'race_pace': 'tempo',
}

# Map performance workout types to coaching-note types (the coaching notes
# generator uses regular plan type names).
_COACHING_TYPE_MAP = {
    'vo2max': 'interval',
    'race_pace': 'tempo',
    'fartlek': 'interval',
}


class PerformancePlanGenerator:
    """Generates performance-focused training plans with pace-based zones.

    Delegates to the same core modules as TrainingPlanGenerator:
    - phase_calculator: distance-aware phase distribution with recovery weeks
    - mileage_progression: 10% rule enforcement with VDOT-adjusted peak
    - key_workout_library: curated race-specific workouts (build/peak phases)

    Adds performance-specific value:
    - 5-zone pace-based training zones (with optional HR)
    - Segment-based workout structure for zone visualization
    """

    PHASE_QUALITY_PRIORITY = {
        'base':    ['tempo', 'fartlek'],
        'build':   ['tempo', 'vo2max'],
        'peak':    ['vo2max', 'race_pace'],
        'taper':   ['race_pace', 'tempo'],
    }

    def __init__(self):
        self.workout_types = {
            'tempo': {'zone': 'zone_3', 'description': 'Tempo run at lactate threshold', 'quality': True},
            'vo2max': {'zone': 'zone_4', 'description': 'VO2 max intervals', 'quality': True},
            'race_pace': {'zone': 'zone_5', 'description': 'Race pace efforts', 'quality': True},
            'fartlek': {'zone': 'mixed', 'description': 'Variable pace play', 'quality': True},
            'long': {'zone': 'zone_1', 'description': 'Long aerobic run', 'quality': False},
            'easy': {'zone': 'zone_1', 'description': 'Easy recovery run', 'quality': False},
            'recovery': {'zone': 'zone_1', 'description': 'Very easy recovery', 'quality': False},
            'rest': {'zone': None, 'description': 'Rest day', 'quality': False},
        }

    def calculate_training_zones(self, goal_pace: float, max_hr: Optional[int] = None,
                                  vdot_zones: Optional[Dict] = None) -> Dict[str, Dict[str, Any]]:
        """Calculate 5 training zones based on goal pace and optionally max heart rate."""
        hr_percentages = {
            'zone_1_recovery': (0.60, 0.70),
            'zone_2_aerobic': (0.70, 0.80),
            'zone_3_tempo': (0.80, 0.88),
            'zone_4_vo2max': (0.88, 0.95),
            'zone_5_race': (0.95, 1.00)
        }

        if vdot_zones:
            e_slow = vdot_zones['E']['pace_min_km_slow']
            e_fast = vdot_zones['E']['pace_min_km_fast']
            t_pace = vdot_zones['T']['pace_min_km']
            i_pace = vdot_zones['I']['pace_min_km']
            m_pace = vdot_zones['M']['pace_min_km']
            zones = {
                'zone_1_recovery': {
                    'pace': e_slow,
                    'pace_range': (e_slow, e_fast),
                    'hr_range': '60-70%',
                    'description': 'Recovery: truly easy, conversational pace',
                    'color': '#4ade80',
                },
                'zone_2_aerobic': {
                    'pace': e_fast,
                    'pace_range': (e_fast, t_pace),
                    'hr_range': '70-80%',
                    'description': 'Aerobic: moderate effort, can still hold a conversation',
                    'color': '#60a5fa',
                },
                'zone_3_tempo': {
                    'pace': t_pace,
                    'pace_range': (t_pace, t_pace * 0.97),
                    'hr_range': '80-88%',
                    'description': 'Tempo: comfortably hard, sustainable for 20-40 min',
                    'color': '#facc15',
                },
                'zone_4_vo2max': {
                    'pace': i_pace,
                    'pace_range': (i_pace, i_pace * 0.95),
                    'hr_range': '88-95%',
                    'description': 'VO2max: hard effort, 3-5 min intervals',
                    'color': '#f97316',
                },
                'zone_5_race': {
                    'pace': goal_pace,
                    'pace_range': (goal_pace, goal_pace * 0.98),
                    'hr_range': '95-100%',
                    'description': 'Race pace: target effort for race day',
                    'color': '#ef4444',
                },
            }
        else:
            zones = {
                'zone_1_recovery': {
                    'pace': goal_pace * 1.30,
                    'pace_range': (goal_pace * 1.35, goal_pace * 1.25),
                    'hr_range': '60-70%',
                    'description': 'Recovery: truly easy, conversational pace',
                    'color': '#4ade80',
                },
                'zone_2_aerobic': {
                    'pace': goal_pace * 1.15,
                    'pace_range': (goal_pace * 1.25, goal_pace * 1.10),
                    'hr_range': '70-80%',
                    'description': 'Aerobic: moderate effort, can still hold a conversation',
                    'color': '#60a5fa',
                },
                'zone_3_tempo': {
                    'pace': goal_pace * 1.05,
                    'pace_range': (goal_pace * 1.10, goal_pace * 1.02),
                    'hr_range': '80-88%',
                    'description': 'Tempo: comfortably hard, sustainable for 20-40 min',
                    'color': '#facc15',
                },
                'zone_4_vo2max': {
                    'pace': goal_pace * 0.95,
                    'pace_range': (goal_pace * 1.00, goal_pace * 0.92),
                    'hr_range': '88-95%',
                    'description': 'VO2max: hard effort, 3-5 min intervals',
                    'color': '#f97316',
                },
                'zone_5_race': {
                    'pace': goal_pace,
                    'pace_range': (goal_pace * 1.02, goal_pace * 0.98),
                    'hr_range': '95-100%',
                    'description': 'Race pace: target effort for race day',
                    'color': '#ef4444',
                },
            }

        # Add BPM ranges if max_hr provided
        if max_hr:
            for zone_name, (low_pct, high_pct) in hr_percentages.items():
                low_bpm = int(max_hr * low_pct)
                high_bpm = int(max_hr * high_pct)
                zones[zone_name]['hr_bpm_range'] = f"{low_bpm}-{high_bpm} BPM"

        return zones

    # ------------------------------------------------------------------
    # Key workout overlay
    # ------------------------------------------------------------------

    @staticmethod
    def _overlay_key_workout(workout: Dict[str, Any], phase: str,
                             target_distance: float, week_in_phase: int,
                             vdot_zones: Optional[Dict]) -> None:
        """Attach key workout details for quality sessions in build/peak."""
        library_type = _LIBRARY_TYPE_MAP.get(workout['type'])
        if not library_type:
            return
        _overlay_key_workout_shared(
            workout, library_type, phase,
            target_distance=target_distance,
            week_in_phase=week_in_phase,
            pace_zones=vdot_zones,
        )

    # ------------------------------------------------------------------
    # Weekly plan assembly
    # ------------------------------------------------------------------

    def _generate_weekly_plan(
        self, week_number: int, phase: str, phases_rich: Dict, zones: Dict,
        weekly_km: float, target_distance: float, runs_per_week: int,
        is_recovery: bool, vdot_zones: Optional[Dict] = None,
        week_in_phase: int = 0,
    ) -> Dict[str, Any]:
        quality_percent = phases_rich[phase]['quality_percent']

        if is_recovery:
            # Recovery weeks: at most 1 light quality session
            quality_workouts_needed = 1 if runs_per_week >= 4 else 0
        else:
            quality_workouts_needed = max(1, int(runs_per_week * quality_percent / 100))

        daily_workouts = []
        total_assigned_km = 0

        workout_schedule = []

        # Long run on Saturday (day 6)
        workout_schedule.append({
            'day': 6,
            'workout_generator': lambda: generate_long_run(zones, weekly_km, week_number, phase, target_distance)
        })

        # Quality workouts on Tuesday (day 2) and Friday (day 5)
        if quality_workouts_needed > 0:
            quality_days = [2, 4] if runs_per_week >= 4 else [2]
            quality_types = self.PHASE_QUALITY_PRIORITY.get(phase, ['tempo', 'vo2max'])

            _generators = {
                'tempo': lambda: generate_tempo_workout(zones, weekly_km, week_number, phase),
                'vo2max': lambda: generate_vo2max_workout(zones, weekly_km, week_number, phase),
                'race_pace': lambda: generate_race_pace_workout(zones, weekly_km, week_number, phase),
                'fartlek': lambda: generate_fartlek_workout(zones, weekly_km, week_number, phase),
            }

            for i, day in enumerate(quality_days[:quality_workouts_needed]):
                workout_type = quality_types[(week_number - 1 + i) % len(quality_types)]
                generator = _generators.get(workout_type, _generators['fartlek'])
                workout_schedule.append({'day': day, 'workout_generator': generator})

        for item in workout_schedule:
            workout = item['workout_generator']()
            workout['day'] = item['day']
            daily_workouts.append(workout)
            total_assigned_km += workout['distance']

        # Apply quality caps against the long run, then sync segments
        enforce_week_caps(daily_workouts, target_distance, phase)
        for w in daily_workouts:
            reconcile_workout_after_cap(w)
        total_assigned_km = sum(w['distance'] for w in daily_workouts)

        # Fill remaining days with easy runs
        remaining_km = weekly_km - total_assigned_km
        scheduled_days = {w['day'] for w in daily_workouts}
        available_days = [d for d in [1, 3, 5, 7] if d not in scheduled_days]

        # Sort available days by spacing quality (prefer days with rest on both sides)
        def _spacing_score(day: int) -> int:
            return (1 if (day - 1) not in scheduled_days else 0) + \
                   (1 if (day + 1) not in scheduled_days else 0)
        available_days.sort(key=_spacing_score, reverse=True)

        easy_runs_needed = runs_per_week - len(daily_workouts)
        if easy_runs_needed > 0 and remaining_km > 0:
            easy_run_km = remaining_km / easy_runs_needed
            long_runs = [w for w in daily_workouts if w['type'] == 'long']
            long_dist = long_runs[0]['distance'] if long_runs else 0
            min_easy_km = max(3.0, long_dist * 0.20) if long_dist > 0 else 3.0
            easy_run_km = max(easy_run_km, min_easy_km)

            def _would_create_three_consecutive(day: int, current_scheduled: set) -> bool:
                test = current_scheduled | {day}
                for d in range(1, 6):
                    if d in test and (d + 1) in test and (d + 2) in test:
                        return True
                return False

            for i in range(easy_runs_needed):
                safe_days = [d for d in available_days if not _would_create_three_consecutive(d, scheduled_days)]
                if not safe_days:
                    safe_days = available_days
                if safe_days:
                    chosen = safe_days[0]
                    workout = generate_easy_run(zones, easy_run_km)
                    workout['day'] = chosen
                    daily_workouts.append(workout)
                    scheduled_days.add(chosen)
                    available_days.remove(chosen)

        # Fill unscheduled days with rest
        scheduled_days = {w['day'] for w in daily_workouts}
        for d in range(1, 8):
            if d not in scheduled_days:
                daily_workouts.append({
                    'day': d,
                    'type': 'rest',
                    'distance': 0,
                    'description': 'Rest day',
                    'intensity': 'rest',
                })

        daily_workouts.sort(key=lambda x: x['day'])

        # Overlay key workouts and coaching rationale
        for workout in daily_workouts:
            if workout.get('quality', False):
                self._overlay_key_workout(
                    workout, phase, target_distance, week_in_phase, vdot_zones,
                )
                _regenerate_description(workout)
            coaching_type = _COACHING_TYPE_MAP.get(workout['type'], workout['type'])
            workout['coaching_rationale'] = generate_coaching_note(
                coaching_type, phase, week_number, target_distance, is_recovery,
            )

        actual_total_km = sum(w['distance'] for w in daily_workouts)
        is_valid, validation_msg = self._validate_week_plan(daily_workouts, actual_total_km, weekly_km)

        return {
            'week': week_number,
            'phase': phase,
            'phase_description': phases_rich[phase]['description'],
            'is_recovery': is_recovery,
            'total_km': round(actual_total_km, 1),
            'quality_workouts': sum(1 for w in daily_workouts if w.get('quality', False)),
            'daily_workouts': daily_workouts,
            'validation': {'valid': is_valid, 'message': validation_msg},
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_week_plan(workouts: List[Dict], total_km: float,
                            target_km: float) -> tuple:
        """Validate a week's workouts follow training principles."""
        long_runs = [w for w in workouts if w['type'] == 'long']
        long_dist = long_runs[0]['distance'] if long_runs else 0

        for workout in workouts:
            if workout.get('quality', False) and workout['distance'] > long_dist * 1.1:
                return False, (f"Quality workout {workout['type']} ({workout['distance']:.1f}km) "
                               f"exceeds long run ({long_dist:.1f}km)")

            if workout['type'] == 'easy' and 0 < workout['distance'] < 2.0:
                return False, f"Easy run too short ({workout['distance']:.1f}km)"

        tolerance = target_km * 0.15
        if total_km < target_km - tolerance:
            return False, f"Volume shortfall: target {target_km:.1f}km, got {total_km:.1f}km"

        return True, "Valid"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate_plan(
        self,
        target_distance: float,
        current_pace: float,
        goal_pace: float,
        weeks: int,
        current_weekly_km: float,
        runs_per_week: int = 5,
        max_heart_rate: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate a complete performance training plan."""
        if goal_pace >= current_pace:
            raise ValueError("Goal pace must be faster than current pace")

        improvement = (current_pace - goal_pace) / current_pace
        if improvement > 0.15:
            raise ValueError("Goal pace improvement >15% is not realistic")

        weeks = max(6, min(16, weeks))

        # --- Shared modules: phase calculation & mileage progression ---
        phase_durations = phase_calculator.calculate_phases(weeks, target_distance)
        phases_rich = {
            phase: {'weeks': phase_durations[phase], **_PHASE_METADATA[phase]}
            for phase in phase_durations
        }

        # --- VDOT & pace zones ---
        vdot = None
        vdot_zones = None
        if current_pace:
            implied_seconds = int(current_pace * target_distance * 60)
            vdot = VDOTCalculator.calculate_vdot(target_distance, implied_seconds)
            if vdot:
                vdot_zones = VDOTCalculator.get_pace_zones(vdot)

        zones = self.calculate_training_zones(goal_pace, max_heart_rate, vdot_zones=vdot_zones)

        # Shared mileage progression (10% rule, recovery weeks, VDOT-adjusted peak)
        km_progression = mileage_progression.calculate_weekly_progression(
            current_weekly_km, target_distance, weeks, runs_per_week, vdot=vdot,
        )

        weekly_plans = []
        for week_num in range(1, weeks + 1):
            phase = phase_calculator.get_phase(week_num, phase_durations)
            is_recovery = phase_calculator.is_recovery_week(week_num, phase, phase_durations)

            week_in_phase = calculate_week_in_phase(week_num, phase, phase_durations)

            weekly_plan = self._generate_weekly_plan(
                week_num, phase, phases_rich, zones,
                km_progression[week_num - 1], target_distance, runs_per_week,
                is_recovery, vdot_zones=vdot_zones, week_in_phase=week_in_phase,
            )
            weekly_plans.append(weekly_plan)

        total_km = sum(week['total_km'] for week in weekly_plans)
        total_quality_workouts = sum(week['quality_workouts'] for week in weekly_plans)

        return {
            'target_distance': target_distance,
            'current_pace': current_pace,
            'goal_pace': goal_pace,
            'weeks': weeks,
            'runs_per_week': runs_per_week,
            'training_zones': zones,
            'phases': phases_rich,
            'vdot': vdot,
            'weekly_plans': weekly_plans,
            'summary': {
                'total_weeks': weeks,
                'total_km': round(total_km, 1),
                'avg_weekly_km': round(total_km / weeks, 1),
                'total_quality_workouts': total_quality_workouts,
                'improvement_target': f"{improvement * 100:.1f}%",
            },
        }
