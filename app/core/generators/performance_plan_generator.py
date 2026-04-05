"""
Performance Training Plan Generator

Generates speed-focused training plans for experienced runners targeting race time improvements.
Uses pace zones and periodization to balance intensity and recovery.
"""

import math
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from app.core.training.vdot_calculator import VDOTCalculator
from app.utils import format_pace as _shared_format_pace


class PerformancePlanGenerator:
    """Generates performance-focused training plans with pace-based zones."""

    # Phase-appropriate quality workout types (avoids race-pace work in base, etc.)
    PHASE_QUALITY_PRIORITY = {
        'base':    ['tempo', 'fartlek'],
        'build':   ['tempo', 'vo2max'],
        'sharpen': ['vo2max', 'race_pace'],
        'taper':   ['race_pace', 'tempo'],
    }

    def __init__(self):
        """Initialize the performance plan generator."""
        self.workout_types = {
            'tempo': {
                'zone': 'zone_3',
                'description': 'Tempo run at lactate threshold',
                'quality': True
            },
            'vo2max': {
                'zone': 'zone_4',
                'description': 'VO2 max intervals',
                'quality': True
            },
            'race_pace': {
                'zone': 'zone_5',
                'description': 'Race pace efforts',
                'quality': True
            },
            'fartlek': {
                'zone': 'mixed',
                'description': 'Variable pace play',
                'quality': True
            },
            'long': {
                'zone': 'zone_1',
                'description': 'Long aerobic run',
                'quality': False
            },
            'easy': {
                'zone': 'zone_1',
                'description': 'Easy recovery run',
                'quality': False
            },
            'recovery': {
                'zone': 'zone_1',
                'description': 'Very easy recovery',
                'quality': False
            },
            'rest': {
                'zone': None,
                'description': 'Rest day',
                'quality': False
            }
        }

    def calculate_training_zones(self, goal_pace: float, max_hr: Optional[int] = None,
                                  vdot_zones: Optional[Dict] = None) -> Dict[str, Dict[str, Any]]:
        """
        Calculate 5 training zones based on goal pace and optionally max heart rate.
        When vdot_zones is provided, use Daniels' physiology-grounded paces instead of
        fixed offsets from goal pace.

        Args:
            goal_pace: Goal race pace in min/km
            max_hr: Maximum heart rate in BPM (optional)
            vdot_zones: Pre-computed VDOT pace zones from VDOTCalculator (optional)

        Returns:
            Dictionary of training zones with pace, HR percentage, and BPM ranges
        """
        # Define HR percentage ranges for each zone (simple % of max HR method)
        hr_percentages = {
            'zone_1_recovery': (0.60, 0.70),
            'zone_2_aerobic': (0.70, 0.80),
            'zone_3_tempo': (0.80, 0.88),
            'zone_4_vo2max': (0.88, 0.95),
            'zone_5_race': (0.95, 1.00)
        }

        if vdot_zones:
            # Use Daniels' physiology-grounded paces
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
                    'description': 'Easy recovery - conversational',
                    'color': '#4ade80'
                },
                'zone_2_aerobic': {
                    'pace': e_fast,
                    'pace_range': (e_fast, m_pace),
                    'hr_range': '70-80%',
                    'description': 'Aerobic base building',
                    'color': '#60a5fa'
                },
                'zone_3_tempo': {
                    'pace': t_pace,
                    'pace_range': (t_pace - 0.1, t_pace + 0.1),
                    'hr_range': '80-88%',
                    'description': 'Lactate threshold / tempo',
                    'color': '#fbbf24'
                },
                'zone_4_vo2max': {
                    'pace': i_pace,
                    'pace_range': (i_pace - 0.1, i_pace + 0.1),
                    'hr_range': '88-95%',
                    'description': 'VO2 max / hard intervals',
                    'color': '#fb923c'
                },
                'zone_5_race': {
                    'pace': goal_pace,
                    'pace_range': (goal_pace - 0.1, goal_pace + 0.1),
                    'hr_range': '95-100%',
                    'description': 'Goal race pace',
                    'color': '#ef4444'
                }
            }
        else:
            # Fallback: fixed offsets from goal pace
            zones = {
                'zone_1_recovery': {
                    'pace': goal_pace + 1.5,  # Very easy
                    'pace_range': (goal_pace + 1.3, goal_pace + 1.8),
                    'hr_range': '60-70%',
                    'description': 'Easy recovery - conversational',
                    'color': '#4ade80'
                },
                'zone_2_aerobic': {
                    'pace': goal_pace + 0.9,  # Easy
                    'pace_range': (goal_pace + 0.7, goal_pace + 1.1),
                    'hr_range': '70-80%',
                    'description': 'Aerobic base building',
                    'color': '#60a5fa'
                },
                'zone_3_tempo': {
                    'pace': goal_pace + 0.3,  # Threshold
                    'pace_range': (goal_pace + 0.2, goal_pace + 0.4),
                    'hr_range': '80-88%',
                    'description': 'Lactate threshold / tempo',
                    'color': '#fbbf24'
                },
                'zone_4_vo2max': {
                    'pace': goal_pace - 0.2,  # Hard
                    'pace_range': (goal_pace - 0.3, goal_pace - 0.1),
                    'hr_range': '88-95%',
                    'description': 'VO2 max / hard intervals',
                    'color': '#fb923c'
                },
                'zone_5_race': {
                    'pace': goal_pace,  # Goal pace
                    'pace_range': (goal_pace - 0.1, goal_pace + 0.1),
                    'hr_range': '95-100%',
                    'description': 'Goal race pace',
                    'color': '#ef4444'
                }
            }

        # Add BPM ranges if max_hr is provided
        if max_hr:
            for zone_name, zone_data in zones.items():
                if zone_name in hr_percentages:
                    lower_pct, upper_pct = hr_percentages[zone_name]
                    lower_bpm = int(max_hr * lower_pct)
                    upper_bpm = int(max_hr * upper_pct)
                    zone_data['hr_bpm_range'] = f"{lower_bpm}-{upper_bpm} BPM"

        return zones

    def _estimate_duration_min(self, segments: list) -> int:
        """
        Estimate total workout duration from segments.

        Args:
            segments: List of segment dicts, each with distance_km and pace_raw.

        Returns:
            Estimated total duration in minutes (rounded).
        """
        total = 0
        for seg in segments:
            total += seg['distance_km'] * seg.get('pace_raw', 6.0)
        return round(total)

    def _calculate_phases(self, weeks: int) -> Dict[str, Dict[str, Any]]:
        """
        Calculate training phases with quality workout percentages.

        Args:
            weeks: Total weeks in the plan

        Returns:
            Dict with phase info including duration and quality percentage
        """
        if weeks < 6:
            weeks = 6  # Minimum for performance training

        # Phase distribution
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

        phases = {
            'base': {
                'weeks': base_weeks,
                'quality_percent': 30,  # 30% quality workouts
                'description': 'Build aerobic foundation'
            },
            'build': {
                'weeks': build_weeks,
                'quality_percent': 50,  # 50% quality workouts
                'description': 'Add intensity and volume'
            },
            'sharpen': {
                'weeks': sharpen_weeks,
                'quality_percent': 60,  # 60% quality workouts
                'description': 'Peak intensity and sharpness'
            },
            'taper': {
                'weeks': taper_weeks,
                'quality_percent': 40,  # Maintain intensity, reduce volume
                'description': 'Reduce volume, maintain sharpness'
            }
        }

        return phases

    def _get_phase_for_week(self, week_number: int, phases: Dict[str, Dict[str, Any]]) -> str:
        """Determine which phase a given week falls into."""
        week_count = 0
        for phase_name in ['base', 'build', 'sharpen', 'taper']:
            week_count += phases[phase_name]['weeks']
            if week_number <= week_count:
                return phase_name
        return 'taper'

    def _calculate_weekly_km_progression(self, current_weekly_km: float, weeks: int, phases: Dict) -> List[float]:
        """Ramp from current → peak in base/build, hold in sharpen, taper down.

        Peak = min(current * 1.5, current + 30) — performance plans assume fit runners.
        """
        peak_km = min(current_weekly_km * 1.5, current_weekly_km + 30)
        progression = []

        # Base: linear build to 80% of peak
        base_target = peak_km * 0.80
        base_weeks = phases['base']['weeks']
        for i in range(base_weeks):
            t = (i + 1) / base_weeks
            progression.append(round(current_weekly_km + (base_target - current_weekly_km) * t, 1))

        # Build: linear build from 80% to 100% of peak
        build_weeks = phases['build']['weeks']
        for i in range(build_weeks):
            t = (i + 1) / build_weeks
            progression.append(round(base_target + (peak_km - base_target) * t, 1))

        # Sharpen: hold at ~95% of peak
        for _ in range(phases['sharpen']['weeks']):
            progression.append(round(peak_km * 0.95, 1))

        # Taper: step down 80% → 65%
        taper_weeks = phases['taper']['weeks']
        for i in range(taper_weeks):
            t = i / max(taper_weeks - 1, 1)
            factor = 0.80 - (0.15 * t)
            progression.append(round(peak_km * factor, 1))

        return progression

    def _generate_tempo_workout(self, zones: Dict, distance_km: float, week: int, phase: str) -> Dict:
        """Generate a tempo workout."""
        target_pace = zones['zone_3_tempo']['pace']

        # Tempo duration varies by phase
        if phase == 'base':
            tempo_km = min(6, distance_km * 0.6)
        elif phase == 'build':
            tempo_km = min(10, distance_km * 0.8)
        elif phase == 'sharpen':
            tempo_km = min(12, distance_km)
        else:  # taper
            tempo_km = min(5, distance_km * 0.5)

        warmup_km = 2
        cooldown_km = 2
        total_km = warmup_km + tempo_km + cooldown_km

        warmup_pace = zones['zone_1_recovery']['pace']
        segments = [
            {
                'name': 'Warm-up',
                'distance_km': warmup_km,
                'pace_formatted': _shared_format_pace(warmup_pace),
                'pace_raw': warmup_pace,
                'zone': 'zone_1',
                'zone_label': 'Zone 1',
                'type': 'warmup',
            },
            {
                'name': 'Tempo',
                'distance_km': round(tempo_km, 1),
                'pace_formatted': _shared_format_pace(target_pace),
                'pace_raw': target_pace,
                'zone': 'zone_3',
                'zone_label': 'Zone 3',
                'type': 'main',
            },
            {
                'name': 'Cool-down',
                'distance_km': cooldown_km,
                'pace_formatted': _shared_format_pace(warmup_pace),
                'pace_raw': warmup_pace,
                'zone': 'zone_1',
                'zone_label': 'Zone 1',
                'type': 'cooldown',
            },
        ]

        return {
            'type': 'tempo',
            'zone': 'zone_3',
            'target_pace': target_pace,
            'target_pace_formatted': _shared_format_pace(target_pace),
            'description': f"{total_km:.0f}km tempo: {warmup_km}km warmup, {tempo_km:.0f}km at {_shared_format_pace(target_pace)}, {cooldown_km}km cooldown",
            'distance': total_km,
            'quality': True,
            'segments': segments,
            'total_duration_est_min': self._estimate_duration_min(segments),
        }

    def _generate_vo2max_workout(self, zones: Dict, distance_km: float, week: int, phase: str) -> Dict:
        """Generate a VO2 max interval workout."""
        target_pace = zones['zone_4_vo2max']['pace']

        # Interval distance scales by race distance AND phase.
        # 5K: shorter/faster reps; Marathon: longer sustained reps.
        if distance_km <= 5:
            base_intervals = {'base': 400, 'build': 500, 'sharpen': 600, 'taper': 400}
        elif distance_km <= 10:
            base_intervals = {'base': 600, 'build': 800, 'sharpen': 1000, 'taper': 600}
        elif distance_km <= 30:   # Half marathon and trail
            base_intervals = {'base': 800, 'build': 1000, 'sharpen': 1200, 'taper': 600}
        else:                     # Marathon
            base_intervals = {'base': 1000, 'build': 1200, 'sharpen': 1600, 'taper': 800}

        interval_m = base_intervals.get(phase, 800)
        reps_map = {'base': 4, 'build': 6, 'sharpen': 5, 'taper': 4}
        reps = reps_map.get(phase, 4)

        interval_km = interval_m / 1000
        recovery_time = int(interval_km * 2)  # 2 min recovery per km
        total_interval_km = interval_km * reps
        warmup_km = 2
        cooldown_km = 2
        total_km = warmup_km + total_interval_km + cooldown_km

        warmup_pace = zones['zone_1_recovery']['pace']
        segments = [
            {
                'name': 'Warm-up',
                'distance_km': warmup_km,
                'pace_formatted': _shared_format_pace(warmup_pace),
                'pace_raw': warmup_pace,
                'zone': 'zone_1',
                'zone_label': 'Zone 1',
                'type': 'warmup',
            },
            {
                'name': 'Intervals',
                'distance_km': round(total_interval_km, 1),
                'pace_formatted': _shared_format_pace(target_pace),
                'pace_raw': target_pace,
                'zone': 'zone_4',
                'zone_label': 'Zone 4',
                'type': 'main',
                'intervals': {
                    'reps': reps,
                    'interval_m': interval_m,
                    'recovery_min': recovery_time,
                },
            },
            {
                'name': 'Cool-down',
                'distance_km': cooldown_km,
                'pace_formatted': _shared_format_pace(warmup_pace),
                'pace_raw': warmup_pace,
                'zone': 'zone_1',
                'zone_label': 'Zone 1',
                'type': 'cooldown',
            },
        ]

        return {
            'type': 'vo2max',
            'zone': 'zone_4',
            'target_pace': target_pace,
            'target_pace_formatted': _shared_format_pace(target_pace),
            'description': f"{total_km:.0f}km intervals: {warmup_km}km warmup, {reps}x{interval_m}m at {_shared_format_pace(target_pace)} ({recovery_time}min recovery), {cooldown_km}km cooldown",
            'distance': total_km,
            'quality': True,
            'segments': segments,
            'total_duration_est_min': self._estimate_duration_min(segments),
        }

    def _generate_race_pace_workout(self, zones: Dict, distance_km: float, week: int, phase: str) -> Dict:
        """Generate a race pace workout."""
        target_pace = zones['zone_5_race']['pace']

        # Race pace duration varies by phase and distance
        if phase == 'base':
            race_km = min(4, distance_km * 0.4)
        elif phase == 'build':
            race_km = min(8, distance_km * 0.6)
        elif phase == 'sharpen':
            race_km = min(12, distance_km * 0.8)
        else:  # taper
            race_km = min(3, distance_km * 0.3)

        warmup_km = 2
        cooldown_km = 2
        total_km = warmup_km + race_km + cooldown_km

        warmup_pace = zones['zone_1_recovery']['pace']
        segments = [
            {
                'name': 'Warm-up',
                'distance_km': warmup_km,
                'pace_formatted': _shared_format_pace(warmup_pace),
                'pace_raw': warmup_pace,
                'zone': 'zone_1',
                'zone_label': 'Zone 1',
                'type': 'warmup',
            },
            {
                'name': 'Race Pace',
                'distance_km': round(race_km, 1),
                'pace_formatted': _shared_format_pace(target_pace),
                'pace_raw': target_pace,
                'zone': 'zone_5',
                'zone_label': 'Zone 5',
                'type': 'main',
            },
            {
                'name': 'Cool-down',
                'distance_km': cooldown_km,
                'pace_formatted': _shared_format_pace(warmup_pace),
                'pace_raw': warmup_pace,
                'zone': 'zone_1',
                'zone_label': 'Zone 1',
                'type': 'cooldown',
            },
        ]

        return {
            'type': 'race_pace',
            'zone': 'zone_5',
            'target_pace': target_pace,
            'target_pace_formatted': _shared_format_pace(target_pace),
            'description': f"{total_km:.0f}km race pace: {warmup_km}km warmup, {race_km:.0f}km at {_shared_format_pace(target_pace)}, {cooldown_km}km cooldown",
            'distance': total_km,
            'quality': True,
            'segments': segments,
            'total_duration_est_min': self._estimate_duration_min(segments),
        }

    def _generate_fartlek_workout(self, zones: Dict, distance_km: float, week: int, phase: str) -> Dict:
        """Generate a fartlek (speed play) workout."""
        tempo_pace = zones['zone_3_tempo']['pace']
        hard_pace = zones['zone_4_vo2max']['pace']

        if phase == 'base':
            total_km = 8
            surges = 6
        elif phase == 'build':
            total_km = 10
            surges = 8
        elif phase == 'sharpen':
            total_km = 12
            surges = 10
        else:  # taper
            total_km = 6
            surges = 4

        warmup_km = 2
        cooldown_km = 2
        main_km = max(1, total_km - warmup_km - cooldown_km)
        warmup_pace = zones['zone_1_recovery']['pace']
        # Average pace for fartlek main section (blend of tempo and hard)
        fartlek_avg_pace = (tempo_pace + hard_pace) / 2

        segments = [
            {
                'name': 'Warm-up',
                'distance_km': warmup_km,
                'pace_formatted': _shared_format_pace(warmup_pace),
                'pace_raw': warmup_pace,
                'zone': 'zone_1',
                'zone_label': 'Zone 1',
                'type': 'warmup',
            },
            {
                'name': 'Fartlek',
                'distance_km': round(main_km, 1),
                'pace_formatted': f"{_shared_format_pace(tempo_pace)} - {_shared_format_pace(hard_pace)}",
                'pace_raw': fartlek_avg_pace,
                'zone': 'mixed',
                'zone_label': 'Mixed Zones',
                'type': 'main',
                'intervals': {
                    'reps': surges,
                    'interval_m': '1-3min surges',
                    'recovery_min': None,
                },
            },
            {
                'name': 'Cool-down',
                'distance_km': cooldown_km,
                'pace_formatted': _shared_format_pace(warmup_pace),
                'pace_raw': warmup_pace,
                'zone': 'zone_1',
                'zone_label': 'Zone 1',
                'type': 'cooldown',
            },
        ]

        return {
            'type': 'fartlek',
            'zone': 'mixed',
            'target_pace': tempo_pace,
            'target_pace_formatted': f"{_shared_format_pace(tempo_pace)} - {_shared_format_pace(hard_pace)}",
            'description': f"{total_km}km fartlek: {surges} surges of 1-3min at {_shared_format_pace(hard_pace)}, easy running between",
            'distance': total_km,
            'quality': True,
            'segments': segments,
            'total_duration_est_min': self._estimate_duration_min(segments),
        }

    def _generate_long_run(self, zones: Dict, weekly_km: float, week: int, phase: str, distance_km: float) -> Dict:
        """Generate a long run with optional race pace finish."""
        easy_pace = zones['zone_1_recovery']['pace']
        race_pace = zones['zone_5_race']['pace']

        # Long run is 25-35% of weekly volume
        long_run_km = weekly_km * 0.30

        # Cap based on race distance
        if distance_km <= 10:
            long_run_km = min(long_run_km, 15)
        elif distance_km <= 21.1:
            long_run_km = min(long_run_km, 22)
        else:
            long_run_km = min(long_run_km, 32)

        # Add race pace finish in build and sharpen phases
        if phase in ['build', 'sharpen'] and long_run_km >= 12:
            race_pace_km = min(4, distance_km * 0.3)
            easy_km = long_run_km - race_pace_km
            description = f"{long_run_km:.0f}km long run: {easy_km:.0f}km easy at {_shared_format_pace(easy_pace)}, last {race_pace_km:.0f}km at {_shared_format_pace(race_pace)}"
            segments = [
                {
                    'name': 'Easy',
                    'distance_km': round(easy_km, 1),
                    'pace_formatted': _shared_format_pace(easy_pace),
                    'pace_raw': easy_pace,
                    'zone': 'zone_1',
                    'zone_label': 'Zone 1',
                    'type': 'main',
                },
                {
                    'name': 'Race Pace Finish',
                    'distance_km': round(race_pace_km, 1),
                    'pace_formatted': _shared_format_pace(race_pace),
                    'pace_raw': race_pace,
                    'zone': 'zone_5',
                    'zone_label': 'Zone 5',
                    'type': 'main',
                },
            ]
        else:
            description = f"{long_run_km:.0f}km long run at {_shared_format_pace(easy_pace)}"
            segments = [
                {
                    'name': 'Easy Long Run',
                    'distance_km': round(long_run_km, 1),
                    'pace_formatted': _shared_format_pace(easy_pace),
                    'pace_raw': easy_pace,
                    'zone': 'zone_1',
                    'zone_label': 'Zone 1',
                    'type': 'main',
                },
            ]

        return {
            'type': 'long',
            'zone': 'zone_1',
            'target_pace': easy_pace,
            'target_pace_formatted': _shared_format_pace(easy_pace),
            'description': description,
            'distance': long_run_km,
            'quality': False,
            'segments': segments,
            'total_duration_est_min': self._estimate_duration_min(segments),
        }

    def _generate_easy_run(self, zones: Dict, distance_km: float) -> Dict:
        """Generate an easy recovery run."""
        easy_pace = zones['zone_1_recovery']['pace']

        segments = [
            {
                'name': 'Easy Run',
                'distance_km': round(distance_km, 1),
                'pace_formatted': _shared_format_pace(easy_pace),
                'pace_raw': easy_pace,
                'zone': 'zone_1',
                'zone_label': 'Zone 1',
                'type': 'main',
            },
        ]

        return {
            'type': 'easy',
            'zone': 'zone_1',
            'target_pace': easy_pace,
            'target_pace_formatted': _shared_format_pace(easy_pace),
            'description': f"{distance_km:.0f}km easy at {_shared_format_pace(easy_pace)}",
            'distance': distance_km,
            'quality': False,
            'segments': segments,
            'total_duration_est_min': self._estimate_duration_min(segments),
        }

    def _generate_weekly_plan(
        self,
        week_number: int,
        phase: str,
        phases: Dict,
        zones: Dict,
        weekly_km: float,
        target_distance: float,
        runs_per_week: int
    ) -> Dict[str, Any]:
        """
        Generate a single week's training plan.

        Args:
            week_number: Week number (1-indexed)
            phase: Current training phase
            phases: Phase configuration
            zones: Training zones
            weekly_km: Target weekly mileage
            target_distance: Race distance
            runs_per_week: Number of runs per week

        Returns:
            Weekly plan dictionary
        """
        quality_percent = phases[phase]['quality_percent']
        quality_workouts_needed = max(1, int(runs_per_week * quality_percent / 100))

        daily_workouts = []
        total_assigned_km = 0

        # Determine workout distribution (quality workouts spread through week)
        workout_schedule = []

        # Always include a long run on Sunday (day 7)
        workout_schedule.append({
            'day': 7,
            'workout_generator': lambda: self._generate_long_run(zones, weekly_km, week_number, phase, target_distance)
        })

        # Add quality workouts on Tuesday and Thursday/Friday
        # Use phase-appropriate workout types, rotating by week number within each phase
        quality_days = [2, 5] if runs_per_week >= 4 else [2]
        quality_types = self.PHASE_QUALITY_PRIORITY.get(phase, ['tempo', 'vo2max'])

        _generators = {
            'tempo': lambda: self._generate_tempo_workout(zones, target_distance, week_number, phase),
            'vo2max': lambda: self._generate_vo2max_workout(zones, target_distance, week_number, phase),
            'race_pace': lambda: self._generate_race_pace_workout(zones, target_distance, week_number, phase),
            'fartlek': lambda: self._generate_fartlek_workout(zones, target_distance, week_number, phase),
        }

        for i, day in enumerate(quality_days[:quality_workouts_needed]):
            workout_type = quality_types[(week_number - 1 + i) % len(quality_types)]
            generator = _generators.get(workout_type, _generators['fartlek'])
            workout_schedule.append({'day': day, 'workout_generator': generator})

        # Generate the scheduled workouts
        for item in workout_schedule:
            workout = item['workout_generator']()
            workout['day'] = item['day']
            daily_workouts.append(workout)
            total_assigned_km += workout['distance']

        # Fill remaining days with easy runs
        remaining_km = weekly_km - total_assigned_km
        scheduled_days = {w['day'] for w in daily_workouts}
        available_days = [d for d in [1, 3, 4, 6] if d not in scheduled_days]

        easy_runs_needed = runs_per_week - len(daily_workouts)
        if easy_runs_needed > 0 and remaining_km > 0:
            easy_run_km = remaining_km / easy_runs_needed
            for i in range(easy_runs_needed):
                if i < len(available_days):
                    workout = self._generate_easy_run(zones, easy_run_km)
                    workout['day'] = available_days[i]
                    daily_workouts.append(workout)

        # Sort by day
        daily_workouts.sort(key=lambda x: x['day'])

        # Calculate actual total
        actual_total_km = sum(w['distance'] for w in daily_workouts)

        return {
            'week': week_number,
            'phase': phase,
            'phase_description': phases[phase]['description'],
            'total_km': round(actual_total_km, 1),
            'quality_workouts': sum(1 for w in daily_workouts if w.get('quality', False)),
            'daily_workouts': daily_workouts
        }

    def generate_plan(
        self,
        target_distance: float,
        current_pace: float,
        goal_pace: float,
        weeks: int,
        current_weekly_km: float,
        runs_per_week: int = 5,
        max_heart_rate: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate a complete performance training plan.

        Args:
            target_distance: Race distance in km
            current_pace: Current pace in min/km
            goal_pace: Goal race pace in min/km
            weeks: Duration of the plan
            current_weekly_km: Current weekly mileage
            runs_per_week: Number of runs per week (3-6)
            max_heart_rate: Maximum heart rate in BPM (optional)

        Returns:
            Complete training plan with zones and weekly workouts
        """
        # Validate inputs
        if goal_pace >= current_pace:
            raise ValueError("Goal pace must be faster than current pace")

        improvement = (current_pace - goal_pace) / current_pace
        if improvement > 0.15:
            raise ValueError("Goal pace improvement >15% is not realistic")

        if weeks < 6:
            weeks = 6
        if weeks > 16:
            weeks = 16

        # Calculate phases first (needed for progression)
        phases = self._calculate_phases(weeks)

        # Compute VDOT-grounded zones when current_pace is available
        vdot_zones = None
        if current_pace:
            implied_seconds = int(current_pace * target_distance * 60)
            vdot = VDOTCalculator.calculate_vdot(target_distance, implied_seconds)
            if vdot:
                vdot_zones = VDOTCalculator.get_pace_zones(vdot)

        # Calculate training zones (VDOT-grounded when possible, offset-based fallback)
        zones = self.calculate_training_zones(goal_pace, max_heart_rate, vdot_zones=vdot_zones)

        # Calculate weekly km progression (ramps through base/build, peaks in sharpen, tapers)
        km_progression = self._calculate_weekly_km_progression(current_weekly_km, weeks, phases)

        # Generate weekly plans
        weekly_plans = []
        for week_num in range(1, weeks + 1):
            phase = self._get_phase_for_week(week_num, phases)
            weekly_plan = self._generate_weekly_plan(
                week_num,
                phase,
                phases,
                zones,
                km_progression[week_num - 1],
                target_distance,
                runs_per_week
            )
            weekly_plans.append(weekly_plan)

        # Calculate plan summary
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
                'improvement_target': f"{improvement * 100:.1f}%"
            }
        }
