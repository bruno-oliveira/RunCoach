"""
Performance Training Plan Generator

Generates speed-focused training plans for experienced runners targeting race time improvements.
Uses pace zones and periodization to balance intensity and recovery.
"""

import math
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


class PerformancePlanGenerator:
    """Generates performance-focused training plans with pace-based zones."""

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

    def calculate_training_zones(self, goal_pace: float, max_hr: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
        """
        Calculate 5 training zones based on goal pace and optionally max heart rate.

        Args:
            goal_pace: Goal race pace in min/km
            max_hr: Maximum heart rate in BPM (optional)

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

        zones = {
            'zone_1_recovery': {
                'pace': goal_pace + 1.5,  # Very easy
                'pace_range': (goal_pace + 1.3, goal_pace + 1.8),
                'hr_range': '60-70%',
                'description': 'Easy recovery - conversational',
                'color': '#4ade80'  # green
            },
            'zone_2_aerobic': {
                'pace': goal_pace + 0.9,  # Easy
                'pace_range': (goal_pace + 0.7, goal_pace + 1.1),
                'hr_range': '70-80%',
                'description': 'Aerobic base building',
                'color': '#60a5fa'  # blue
            },
            'zone_3_tempo': {
                'pace': goal_pace + 0.3,  # Threshold
                'pace_range': (goal_pace + 0.2, goal_pace + 0.4),
                'hr_range': '80-88%',
                'description': 'Lactate threshold / tempo',
                'color': '#fbbf24'  # yellow
            },
            'zone_4_vo2max': {
                'pace': goal_pace - 0.2,  # Hard
                'pace_range': (goal_pace - 0.3, goal_pace - 0.1),
                'hr_range': '88-95%',
                'description': 'VO2 max / hard intervals',
                'color': '#fb923c'  # orange
            },
            'zone_5_race': {
                'pace': goal_pace,  # Goal pace
                'pace_range': (goal_pace - 0.1, goal_pace + 0.1),
                'hr_range': '95-100%',
                'description': 'Goal race pace',
                'color': '#ef4444'  # red
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

    def _format_pace(self, pace_min_per_km: float) -> str:
        """
        Format pace as MM:SS/km.

        Args:
            pace_min_per_km: Pace in decimal minutes per km

        Returns:
            Formatted string like "5:30/km"
        """
        minutes = int(pace_min_per_km)
        seconds = int((pace_min_per_km - minutes) * 60)
        return f"{minutes}:{seconds:02d}/km"

    def _format_pace_range(self, pace_range: tuple) -> str:
        """Format a pace range."""
        return f"{self._format_pace(pace_range[0])} - {self._format_pace(pace_range[1])}"

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
            taper_weeks = weeks - base_weeks - build_weeks - sharpen_weeks
        elif weeks <= 12:
            base_weeks = max(3, int(weeks * 0.33))
            build_weeks = max(3, int(weeks * 0.33))
            sharpen_weeks = max(2, int(weeks * 0.20))
            taper_weeks = weeks - base_weeks - build_weeks - sharpen_weeks
        else:
            base_weeks = max(4, int(weeks * 0.35))
            build_weeks = max(4, int(weeks * 0.35))
            sharpen_weeks = max(2, int(weeks * 0.18))
            taper_weeks = weeks - base_weeks - build_weeks - sharpen_weeks

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

        return {
            'type': 'tempo',
            'zone': 'zone_3',
            'target_pace': target_pace,
            'target_pace_formatted': self._format_pace(target_pace),
            'description': f"{total_km:.0f}km tempo: {warmup_km}km warmup, {tempo_km:.0f}km at {self._format_pace(target_pace)}, {cooldown_km}km cooldown",
            'distance': total_km,
            'quality': True
        }

    def _generate_vo2max_workout(self, zones: Dict, distance_km: float, week: int, phase: str) -> Dict:
        """Generate a VO2 max interval workout."""
        target_pace = zones['zone_4_vo2max']['pace']

        # Interval distance and reps vary by phase
        if phase == 'base':
            interval_m = 800
            reps = 4
        elif phase == 'build':
            interval_m = 1000
            reps = 6
        elif phase == 'sharpen':
            interval_m = 1200
            reps = 5
        else:  # taper
            interval_m = 600
            reps = 4

        interval_km = interval_m / 1000
        recovery_time = int(interval_km * 2)  # 2 min recovery per km
        total_interval_km = interval_km * reps
        warmup_km = 2
        cooldown_km = 2
        total_km = warmup_km + total_interval_km + cooldown_km

        return {
            'type': 'vo2max',
            'zone': 'zone_4',
            'target_pace': target_pace,
            'target_pace_formatted': self._format_pace(target_pace),
            'description': f"{total_km:.0f}km intervals: {warmup_km}km warmup, {reps}x{interval_m}m at {self._format_pace(target_pace)} ({recovery_time}min recovery), {cooldown_km}km cooldown",
            'distance': total_km,
            'quality': True
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

        return {
            'type': 'race_pace',
            'zone': 'zone_5',
            'target_pace': target_pace,
            'target_pace_formatted': self._format_pace(target_pace),
            'description': f"{total_km:.0f}km race pace: {warmup_km}km warmup, {race_km:.0f}km at {self._format_pace(target_pace)}, {cooldown_km}km cooldown",
            'distance': total_km,
            'quality': True
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

        return {
            'type': 'fartlek',
            'zone': 'mixed',
            'target_pace': tempo_pace,
            'target_pace_formatted': f"{self._format_pace(tempo_pace)} - {self._format_pace(hard_pace)}",
            'description': f"{total_km}km fartlek: {surges} surges of 1-3min at {self._format_pace(hard_pace)}, easy running between",
            'distance': total_km,
            'quality': True
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
            description = f"{long_run_km:.0f}km long run: {easy_km:.0f}km easy at {self._format_pace(easy_pace)}, last {race_pace_km:.0f}km at {self._format_pace(race_pace)}"
        else:
            description = f"{long_run_km:.0f}km long run at {self._format_pace(easy_pace)}"

        return {
            'type': 'long',
            'zone': 'zone_1',
            'target_pace': easy_pace,
            'target_pace_formatted': self._format_pace(easy_pace),
            'description': description,
            'distance': long_run_km,
            'quality': False
        }

    def _generate_easy_run(self, zones: Dict, distance_km: float) -> Dict:
        """Generate an easy recovery run."""
        easy_pace = zones['zone_1_recovery']['pace']

        return {
            'type': 'easy',
            'zone': 'zone_1',
            'target_pace': easy_pace,
            'target_pace_formatted': self._format_pace(easy_pace),
            'description': f"{distance_km:.0f}km easy at {self._format_pace(easy_pace)}",
            'distance': distance_km,
            'quality': False
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

        # Taper: reduce volume but maintain quality
        if phase == 'taper':
            weekly_km *= 0.75

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
        quality_days = [2, 5] if runs_per_week >= 4 else [2]
        quality_types = ['tempo', 'vo2max', 'race_pace', 'fartlek']

        for i, day in enumerate(quality_days[:quality_workouts_needed]):
            workout_type = quality_types[i % len(quality_types)]
            if workout_type == 'tempo':
                generator = lambda wt=workout_type: self._generate_tempo_workout(zones, target_distance, week_number, phase)
            elif workout_type == 'vo2max':
                generator = lambda wt=workout_type: self._generate_vo2max_workout(zones, target_distance, week_number, phase)
            elif workout_type == 'race_pace':
                generator = lambda wt=workout_type: self._generate_race_pace_workout(zones, target_distance, week_number, phase)
            else:  # fartlek
                generator = lambda wt=workout_type: self._generate_fartlek_workout(zones, target_distance, week_number, phase)

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

        # Calculate training zones
        zones = self.calculate_training_zones(goal_pace, max_heart_rate)

        # Calculate phases
        phases = self._calculate_phases(weeks)

        # Generate weekly plans
        weekly_plans = []
        for week_num in range(1, weeks + 1):
            phase = self._get_phase_for_week(week_num, phases)
            weekly_plan = self._generate_weekly_plan(
                week_num,
                phase,
                phases,
                zones,
                current_weekly_km,
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
