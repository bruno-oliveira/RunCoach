"""
Performance Training Plan Generator

Generates speed-focused training plans for experienced runners targeting race time improvements.
Uses pace zones and periodization to balance intensity and recovery.
"""

from typing import List, Dict, Any, Optional

from app.core.training.vdot_calculator import VDOTCalculator
from app.utils import format_pace as _shared_format_pace

from .performance_workout_builders import (
    generate_easy_run,
    generate_fartlek_workout,
    generate_long_run,
    generate_race_pace_workout,
    generate_tempo_workout,
    generate_vo2max_workout,
)


class PerformancePlanGenerator:
    """Generates performance-focused training plans with pace-based zones."""

    PHASE_QUALITY_PRIORITY = {
        'base':    ['tempo', 'fartlek'],
        'build':   ['tempo', 'vo2max'],
        'sharpen': ['vo2max', 'race_pace'],
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
    # Phase & progression helpers
    # ------------------------------------------------------------------

    def _calculate_phases(self, weeks: int) -> Dict[str, Dict[str, Any]]:
        if weeks < 6:
            weeks = 6

        if weeks <= 8:
            base_weeks = max(2, weeks // 3)
            build_weeks = max(2, weeks // 3)
            sharpen_weeks = max(1, weeks // 4)
            taper_weeks = max(0, weeks - base_weeks - build_weeks - sharpen_weeks)
        elif weeks <= 12:
            base_weeks = max(3, int(weeks * 0.33))
            build_weeks = max(3, int(weeks * 0.33))
            sharpen_weeks = max(2, int(weeks * 0.20))
            taper_weeks = max(0, weeks - base_weeks - build_weeks - sharpen_weeks)
        else:
            base_weeks = max(4, int(weeks * 0.35))
            build_weeks = max(4, int(weeks * 0.35))
            sharpen_weeks = max(2, int(weeks * 0.18))
            taper_weeks = max(0, weeks - base_weeks - build_weeks - sharpen_weeks)

        return {
            'base': {'weeks': base_weeks, 'quality_percent': 30, 'description': 'Build aerobic foundation'},
            'build': {'weeks': build_weeks, 'quality_percent': 50, 'description': 'Add intensity and volume'},
            'sharpen': {'weeks': sharpen_weeks, 'quality_percent': 60, 'description': 'Peak intensity and sharpness'},
            'taper': {'weeks': taper_weeks, 'quality_percent': 40, 'description': 'Reduce volume, maintain sharpness'},
        }

    def _get_phase_for_week(self, week_number: int, phases: Dict[str, Dict[str, Any]]) -> str:
        week_count = 0
        for phase_name in ['base', 'build', 'sharpen', 'taper']:
            week_count += phases[phase_name]['weeks']
            if week_number <= week_count:
                return phase_name
        return 'taper'

    def _calculate_weekly_km_progression(self, current_weekly_km: float, weeks: int, phases: Dict) -> List[float]:
        peak_km = min(current_weekly_km * 1.5, current_weekly_km + 30)
        progression = []

        base_target = peak_km * 0.80
        base_weeks = phases['base']['weeks']
        for i in range(base_weeks):
            t = (i + 1) / base_weeks
            progression.append(round(current_weekly_km + (base_target - current_weekly_km) * t, 1))

        build_weeks = phases['build']['weeks']
        for i in range(build_weeks):
            t = (i + 1) / build_weeks
            progression.append(round(base_target + (peak_km - base_target) * t, 1))

        for _ in range(phases['sharpen']['weeks']):
            progression.append(round(peak_km * 0.95, 1))

        taper_weeks = phases['taper']['weeks']
        for i in range(taper_weeks):
            t = i / max(taper_weeks - 1, 1)
            factor = 0.80 - (0.15 * t)
            progression.append(round(peak_km * factor, 1))

        return progression

    # ------------------------------------------------------------------
    # Weekly plan assembly
    # ------------------------------------------------------------------

    def _generate_weekly_plan(
        self, week_number: int, phase: str, phases: Dict, zones: Dict,
        weekly_km: float, target_distance: float, runs_per_week: int,
    ) -> Dict[str, Any]:
        quality_percent = phases[phase]['quality_percent']
        quality_workouts_needed = max(1, int(runs_per_week * quality_percent / 100))

        daily_workouts = []
        total_assigned_km = 0

        workout_schedule = []

        workout_schedule.append({
            'day': 7,
            'workout_generator': lambda: generate_long_run(zones, weekly_km, week_number, phase, target_distance)
        })

        quality_days = [2, 5] if runs_per_week >= 4 else [2]
        quality_types = self.PHASE_QUALITY_PRIORITY.get(phase, ['tempo', 'vo2max'])

        _generators = {
            'tempo': lambda: generate_tempo_workout(zones, target_distance, week_number, phase),
            'vo2max': lambda: generate_vo2max_workout(zones, target_distance, week_number, phase),
            'race_pace': lambda: generate_race_pace_workout(zones, target_distance, week_number, phase),
            'fartlek': lambda: generate_fartlek_workout(zones, target_distance, week_number, phase),
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

        remaining_km = weekly_km - total_assigned_km
        scheduled_days = {w['day'] for w in daily_workouts}
        available_days = [d for d in [1, 3, 4, 6] if d not in scheduled_days]

        easy_runs_needed = runs_per_week - len(daily_workouts)
        if easy_runs_needed > 0 and remaining_km > 0:
            easy_run_km = remaining_km / easy_runs_needed
            for i in range(easy_runs_needed):
                if i < len(available_days):
                    workout = generate_easy_run(zones, easy_run_km)
                    workout['day'] = available_days[i]
                    daily_workouts.append(workout)

        daily_workouts.sort(key=lambda x: x['day'])
        actual_total_km = sum(w['distance'] for w in daily_workouts)

        return {
            'week': week_number,
            'phase': phase,
            'phase_description': phases[phase]['description'],
            'total_km': round(actual_total_km, 1),
            'quality_workouts': sum(1 for w in daily_workouts if w.get('quality', False)),
            'daily_workouts': daily_workouts,
        }

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

        phases = self._calculate_phases(weeks)

        vdot_zones = None
        if current_pace:
            implied_seconds = int(current_pace * target_distance * 60)
            vdot = VDOTCalculator.calculate_vdot(target_distance, implied_seconds)
            if vdot:
                vdot_zones = VDOTCalculator.get_pace_zones(vdot)

        zones = self.calculate_training_zones(goal_pace, max_heart_rate, vdot_zones=vdot_zones)
        km_progression = self._calculate_weekly_km_progression(current_weekly_km, weeks, phases)

        weekly_plans = []
        for week_num in range(1, weeks + 1):
            phase = self._get_phase_for_week(week_num, phases)
            weekly_plan = self._generate_weekly_plan(
                week_num, phase, phases, zones,
                km_progression[week_num - 1], target_distance, runs_per_week,
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
            'phases': phases,
            'weekly_plans': weekly_plans,
            'summary': {
                'total_weeks': weeks,
                'total_km': round(total_km, 1),
                'avg_weekly_km': round(total_km / weeks, 1),
                'total_quality_workouts': total_quality_workouts,
                'improvement_target': f"{improvement * 100:.1f}%",
            },
        }
