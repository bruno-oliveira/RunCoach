"""Performance training plan service."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import RunLog, TrainingPlan, User, WeeklyPlan, DailyWorkout
from app.contexts.auth.repositories import SQLAlchemyUserRepository
from app.contexts.plan.generators.performance_plan_generator import PerformancePlanGenerator
from app.contexts.nutrition.nutrition_engine import NutritionEngine
from app.contexts.runner.fitness.performance_progress import (
    get_plan_progress,
    get_plan_with_data,
    get_todays_workout,
)

logger = logging.getLogger(__name__)


def _safe_float(val, default: float = 0.0) -> float:
    """Safely parse a value to float, returning *default* on failure."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


class PerformanceService:
    """Service for performance training plans and fitness analysis."""

    def __init__(
        self,
        db: Session,
        performance_generator: PerformancePlanGenerator | None = None,
        nutrition_engine: NutritionEngine | None = None,
    ):
        """
        Initialize the performance service.

        Args:
            db: Database session
            performance_generator: Performance plan generator instance
            nutrition_engine: Nutrition engine instance
        """
        self.db = db
        self.performance_generator = performance_generator or PerformancePlanGenerator()
        self.nutrition_engine = nutrition_engine or NutritionEngine()

    def calculate_max_heart_rate(
        self,
        user_id: str,
        goal_pace: float,
        lookback_weeks: int = 8
    ) -> Dict[str, Any]:
        """
        Calculate maximum heart rate using three-tier fallback strategy.

        Args:
            user_id: User ID
            goal_pace: Goal pace in min/km (for pace-based estimation)
            lookback_weeks: How many weeks to look back for run data

        Returns:
            Dictionary with max_hr, confidence, source, and message
        """
        # Strategy 1: Use RunLog data (highest confidence)
        cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(weeks=lookback_weeks)
        runs = (
            self.db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.date >= cutoff_date,
                RunLog.max_heart_rate.isnot(None)
            )
            .order_by(RunLog.date.desc())
            .all()
        )

        if len(runs) >= 5:
            # Use 98th percentile to avoid outliers (need at least 10 for meaningful percentile)
            hr_values = sorted([r.max_heart_rate for r in runs])
            if len(hr_values) >= 10:
                percentile_98_idx = min(int(len(hr_values) * 0.98), len(hr_values) - 1)
                max_hr = hr_values[percentile_98_idx]
            else:
                # With fewer values, use second-highest to filter single outlier
                max_hr = hr_values[-2] if len(hr_values) >= 2 else hr_values[-1]

            return {
                'max_hr': max_hr,
                'confidence': 'high',
                'source': 'run_data',
                'message': f'Calculated from {len(runs)} runs with heart rate data (98th percentile)'
            }

        # Strategy 2: Age-based formula (medium confidence)
        user = SQLAlchemyUserRepository(self.db).get_by_id(user_id)
        if user and user.age:
            max_hr = 220 - user.age
            return {
                'max_hr': max_hr,
                'confidence': 'medium',
                'source': 'age_formula',
                'message': f'Estimated from age using 220 - {user.age} formula'
            }

        # Strategy 3: Pace-based estimation (low confidence)
        # Fast pace (~4:00/km) suggests younger/fitter: 185 BPM
        # Average pace (~5:30/km): 180 BPM
        # Slower pace (~7:00/km): 175 BPM
        if goal_pace <= 4.5:
            max_hr = 185
            pace_desc = "fast"
        elif goal_pace <= 6.0:
            max_hr = 180
            pace_desc = "average"
        else:
            max_hr = 175
            pace_desc = "slower"

        return {
            'max_hr': max_hr,
            'confidence': 'low',
            'source': 'pace_estimation',
            'message': f'Rough estimate based on {pace_desc} goal pace (consider testing your actual max HR)'
        }

    def calculate_fitness_from_runs(
        self,
        user_id: str,
        target_distance: float,
        lookback_weeks: int = 8
    ) -> Dict[str, Any]:
        """
        Calculate current fitness metrics from logged runs.

        Args:
            user_id: User ID
            target_distance: Target race distance in km
            lookback_weeks: How many weeks to look back

        Returns:
            Dictionary with fitness metrics or None if insufficient data
        """
        # Get recent runs
        cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(weeks=lookback_weeks)

        runs = (
            self.db.query(RunLog)
            .filter(
                RunLog.user_id == user_id,
                RunLog.date >= cutoff_date,
                RunLog.distance_km.isnot(None),
                RunLog.avg_pace_min_km.isnot(None)
            )
            .order_by(RunLog.date.desc())
            .all()
        )

        if len(runs) < 5:
            return {
                'has_sufficient_data': False,
                'total_runs': len(runs),
                'message': f'Need at least 5 logged runs in the last {lookback_weeks} weeks. You have {len(runs)}.',
            }

        # Filter runs within target distance range (±30%)
        distance_min = target_distance * 0.7
        distance_max = target_distance * 1.3

        relevant_runs = [
            r for r in runs
            if distance_min <= r.distance_km <= distance_max
        ]

        if len(relevant_runs) < 2:
            # Fall back to all runs if not enough in range
            relevant_runs = runs

        # Calculate metrics
        avg_pace = sum(r.avg_pace_min_km for r in relevant_runs) / len(relevant_runs)
        recent_pace = sum(r.avg_pace_min_km for r in relevant_runs[:3]) / min(3, len(relevant_runs))

        # Calculate weekly mileage
        weeks_data = {}
        for run in runs:
            iso = run.date.isocalendar()
            week_key = (iso[0], iso[1])  # (year, week) to avoid cross-year collisions
            if week_key not in weeks_data:
                weeks_data[week_key] = 0
            weeks_data[week_key] += run.distance_km

        avg_weekly_km = sum(weeks_data.values()) / max(len(weeks_data), 1)

        # Analyze improvement trend
        if len(relevant_runs) >= 4:
            first_half = relevant_runs[len(relevant_runs)//2:]
            second_half = relevant_runs[:len(relevant_runs)//2]
            first_half_pace = sum(r.avg_pace_min_km for r in first_half) / len(first_half)
            second_half_pace = sum(r.avg_pace_min_km for r in second_half) / len(second_half)
            improvement_trend = ((first_half_pace - second_half_pace) / first_half_pace) * 100
        else:
            improvement_trend = 0

        # Calculate current estimated finish time
        estimated_time_min = avg_pace * target_distance
        estimated_time_hours = int(estimated_time_min // 60)
        estimated_time_mins = int(estimated_time_min % 60)
        estimated_time_str = f"{estimated_time_hours}:{estimated_time_mins:02d}:00"

        return {
            'has_sufficient_data': True,
            'total_runs': len(runs),
            'relevant_runs': len(relevant_runs),
            'avg_pace': round(avg_pace, 2),
            'recent_pace': round(recent_pace, 2),
            'avg_weekly_km': round(avg_weekly_km, 1),
            'improvement_trend': round(improvement_trend, 1),
            'estimated_finish_time': estimated_time_str,
            'lookback_weeks': lookback_weeks,
        }

    def create_performance_plan(
        self,
        user: User,
        target_distance: float,
        goal_pace: float,
        weeks: int,
        current_pace: float | None = None,
        current_weekly_km: float | None = None,
        goal_time: str | None = None,
        current_time: str | None = None,
        runs_per_week: int = 5,
        auto_calculate: bool = True,
        max_heart_rate: int | None = None
    ) -> Tuple[TrainingPlan, Dict[str, Any]]:
        """
        Create a performance-focused training plan.

        Args:
            user: User creating the plan
            target_distance: Race distance in km
            goal_pace: Goal pace in min/km
            weeks: Duration of the plan
            current_pace: Current pace (optional, will auto-calculate if enabled)
            current_weekly_km: Current weekly mileage (optional)
            goal_time: Goal finish time string
            current_time: Current finish time string
            runs_per_week: Number of runs per week
            auto_calculate: Whether to auto-calculate from run logs
            max_heart_rate: Maximum heart rate in BPM (optional)

        Returns:
            Tuple of (TrainingPlan, plan_data)
        """
        # Auto-calculate fitness if not provided and auto_calculate is enabled
        if auto_calculate and (current_pace is None or current_weekly_km is None):
            fitness = self.calculate_fitness_from_runs(user.id, target_distance)
            if not fitness.get('has_sufficient_data'):
                raise ValueError(
                    f"Insufficient run data to auto-calculate fitness. {fitness.get('message', '')}"
                )
            current_pace = current_pace or fitness['avg_pace']
            current_weekly_km = current_weekly_km or fitness['avg_weekly_km']

        # Validate that we have the required values
        if current_pace is None or current_weekly_km is None:
            raise ValueError(
                "Please provide your current pace and weekly mileage, or enable auto-calculate with sufficient run history."
            )

        # Generate the performance plan
        plan_data = self.performance_generator.generate_plan(
            target_distance=target_distance,
            current_pace=current_pace,
            goal_pace=goal_pace,
            weeks=weeks,
            current_weekly_km=current_weekly_km,
            runs_per_week=runs_per_week,
            max_heart_rate=max_heart_rate
        )

        # Create training plan record
        training_plan = TrainingPlan(
            user_id=user.id,
            current_weekly_km=current_weekly_km,
            target_distance=str(target_distance),
            weeks_duration=weeks,
            plan_type='performance',
            current_pace=current_pace,
            goal_pace=goal_pace,
            current_time=current_time,
            goal_time=goal_time,
            max_runs_per_week=runs_per_week,
            max_heart_rate=max_heart_rate,
            plan_data=plan_data['weekly_plans']
        )

        self.db.add(training_plan)
        self.db.flush()

        # Save weekly plans and daily workouts
        self._save_weekly_plans(training_plan.id, plan_data['weekly_plans'])

        # Generate and save nutrition plan
        nutrition_plan = self.nutrition_engine.generate_weekly_meal_plan(
            current_weekly_km, target_distance
        )
        training_plan.nutrition_plan_data = nutrition_plan

        self.db.commit()

        logger.info(f"Created performance training plan {training_plan.id}")
        return training_plan, plan_data

    def _save_weekly_plans(
        self,
        training_plan_id: str,
        weekly_plans: list[Dict[str, Any]]
    ) -> None:
        """Save weekly plans and daily workouts to database."""
        weekly_plan_records = []
        daily_workout_records = []

        for week_data in weekly_plans:
            week_id = str(uuid.uuid4())
            weekly_plan_records.append({
                'id': week_id,
                'training_plan_id': training_plan_id,
                'week_number': week_data['week'],
                'total_km': week_data['total_km'],
                'workout_types': {
                    'quality_workouts': week_data.get('quality_workouts', 0),
                    'phase': week_data.get('phase', '')
                }
            })

            for workout in week_data.get('daily_workouts', []):
                dist = workout.get('distance', 0)
                daily_workout_records.append({
                    'id': str(uuid.uuid4()),
                    'weekly_plan_id': week_id,
                    'day_of_week': workout['day'],
                    'workout_type': workout['type'],
                    'distance_km': dist,
                    'intensity': workout.get('intensity', workout.get('zone', 'zone_1')),
                    'notes': workout.get('description', ''),
                    'coaching_rationale': workout.get('coaching_rationale'),
                    'baseline_distance_km': dist,
                })

        self.db.add_all([WeeklyPlan(**r) for r in weekly_plan_records])
        self.db.add_all([DailyWorkout(**r) for r in daily_workout_records])
        self.db.flush()

    def get_plan(self, plan_id: str) -> Optional[TrainingPlan]:
        """Get a performance training plan by ID."""
        return (
            self.db.query(TrainingPlan)
            .filter(
                TrainingPlan.id == plan_id,
                TrainingPlan.plan_type == 'performance'
            )
            .first()
        )

    def get_plan_with_data(self, plan_id: str) -> Optional[Tuple[TrainingPlan, Dict]]:
        """Get a training plan with parsed plan data."""
        return get_plan_with_data(self.db, plan_id, self.performance_generator)

    def get_todays_workout(self, plan: TrainingPlan) -> Dict[str, Any]:
        """Determine today's workout from the training plan."""
        return get_todays_workout(self.db, plan)

    def get_plan_progress(self, plan: TrainingPlan) -> Dict[str, Any]:
        """Calculate progress metrics for a training plan."""
        return get_plan_progress(self.db, plan)
