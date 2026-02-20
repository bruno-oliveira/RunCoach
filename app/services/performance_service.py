"""Performance training plan service."""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import RunLog, TrainingPlan, User, WeeklyPlan, DailyWorkout
from app.core.performance_plan_generator import PerformancePlanGenerator
from app.core.nutrition_engine import NutritionEngine

logger = logging.getLogger(__name__)


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
            # Use 98th percentile to avoid outliers
            hr_values = sorted([r.max_heart_rate for r in runs])
            percentile_98_idx = int(len(hr_values) * 0.98)
            max_hr = hr_values[percentile_98_idx]

            return {
                'max_hr': max_hr,
                'confidence': 'high',
                'source': 'run_data',
                'message': f'Calculated from {len(runs)} runs with heart rate data (98th percentile)'
            }

        # Strategy 2: Age-based formula (medium confidence)
        user = self.db.query(User).filter(User.id == user_id).first()
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
            week_key = run.date.isocalendar()[1]  # ISO week number
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
            plan_data=json.dumps(plan_data['weekly_plans'])
        )

        training_plan.start_date = datetime.now(timezone.utc).replace(tzinfo=None)

        self.db.add(training_plan)
        self.db.flush()

        # Save weekly plans and daily workouts
        self._save_weekly_plans(training_plan.id, plan_data['weekly_plans'])

        # Generate and save nutrition plan
        nutrition_plan = self.nutrition_engine.generate_weekly_meal_plan(
            current_weekly_km, target_distance
        )
        training_plan.nutrition_plan_data = json.dumps(nutrition_plan)

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
                'workout_types': json.dumps({
                    'quality_workouts': week_data.get('quality_workouts', 0),
                    'phase': week_data.get('phase', '')
                })
            })

            for workout in week_data.get('daily_workouts', []):
                daily_workout_records.append({
                    'id': str(uuid.uuid4()),
                    'weekly_plan_id': week_id,
                    'day_of_week': workout['day'],
                    'workout_type': workout['type'],
                    'distance_km': workout.get('distance', 0),
                    'intensity': workout.get('zone', 'zone_1'),
                    'notes': workout.get('description', ''),
                })

        self.db.bulk_insert_mappings(WeeklyPlan, weekly_plan_records)
        self.db.bulk_insert_mappings(DailyWorkout, daily_workout_records)
        self.db.commit()

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
        training_plan = self.get_plan(plan_id)
        if not training_plan:
            return None

        plan_data = json.loads(training_plan.plan_data)

        # Reconstruct full plan data with zones (include max_hr if available)
        zones = self.performance_generator.calculate_training_zones(
            training_plan.goal_pace,
            training_plan.max_heart_rate
        )

        full_data = {
            'weekly_plans': plan_data,
            'training_zones': zones,
            'target_distance': float(training_plan.target_distance),
            'current_pace': training_plan.current_pace,
            'goal_pace': training_plan.goal_pace,
            'weeks': training_plan.weeks_duration,
            'max_heart_rate': training_plan.max_heart_rate,
        }

        return training_plan, full_data

    def get_todays_workout(self, plan: TrainingPlan) -> Dict[str, Any]:
        """
        Determine today's workout from the training plan.

        Args:
            plan: The training plan to check.

        Returns:
            Dictionary with status and workout details if applicable.
        """
        start = plan.start_date or plan.created_at
        today = datetime.now(timezone.utc).replace(tzinfo=None).date()
        days_elapsed = (today - start.date()).days

        if days_elapsed < 0:
            return {"status": "not_started"}

        week = days_elapsed // 7 + 1
        day_of_week = days_elapsed % 7 + 1  # 1=Mon, 7=Sun (ISO style)

        # Parse plan data
        plan_data = json.loads(plan.plan_data)

        if week > len(plan_data):
            return {"status": "completed"}

        # Find the matching week
        week_data = None
        for w in plan_data:
            if w.get('week') == week:
                week_data = w
                break

        if not week_data:
            return {"status": "rest_day", "week": week, "day": day_of_week}

        # Find workout matching day_of_week
        workout = None
        for w in week_data.get('daily_workouts', []):
            if w.get('day') == day_of_week:
                workout = w
                break

        if not workout:
            return {"status": "rest_day", "week": week, "day": day_of_week}

        # Check if a RunLog already exists for today
        already_logged = False
        if plan.user_id:
            today_start = datetime(today.year, today.month, today.day)
            today_end = today_start + timedelta(days=1)
            existing = (
                self.db.query(RunLog)
                .filter(
                    RunLog.user_id == plan.user_id,
                    RunLog.date >= today_start,
                    RunLog.date < today_end,
                )
                .first()
            )
            already_logged = existing is not None

        return {
            "status": "workout",
            "week": week,
            "day": day_of_week,
            "workout": workout,
            "already_logged": already_logged,
        }

    def get_plan_progress(self, plan: TrainingPlan) -> Dict[str, Any]:
        """
        Calculate progress metrics for a training plan.

        Args:
            plan: The training plan to analyze.

        Returns:
            Dictionary with progress stats including weekly km, pace, completion, etc.
        """
        plan_data = json.loads(plan.plan_data)
        start = plan.start_date or plan.created_at
        start_date = start.date()
        total_weeks = len(plan_data)
        end_date = start_date + timedelta(days=total_weeks * 7)

        # Planned weekly km
        planned_weekly_km = [w.get('total_km', 0) for w in plan_data]

        # Planned workout count
        planned_count = sum(
            len(w.get('daily_workouts', [])) for w in plan_data
        )

        # Query all RunLogs within plan date range
        plan_start_dt = datetime(start_date.year, start_date.month, start_date.day)
        plan_end_dt = datetime(end_date.year, end_date.month, end_date.day)

        runs = []
        if plan.user_id:
            runs = (
                self.db.query(RunLog)
                .filter(
                    RunLog.user_id == plan.user_id,
                    RunLog.date >= plan_start_dt,
                    RunLog.date < plan_end_dt,
                )
                .order_by(RunLog.date.asc())
                .all()
            )

        # Compute actual weekly km and pace by week
        actual_weekly_km = [0.0] * total_weeks
        pace_by_week_data: Dict[int, list] = {}

        for run in runs:
            run_date = run.date.date() if isinstance(run.date, datetime) else run.date
            days_from_start = (run_date - start_date).days
            if days_from_start < 0:
                continue
            week_idx = days_from_start // 7
            if week_idx >= total_weeks:
                continue
            actual_weekly_km[week_idx] += run.distance_km or 0

            if run.avg_pace_min_km:
                if week_idx not in pace_by_week_data:
                    pace_by_week_data[week_idx] = []
                pace_by_week_data[week_idx].append(run.avg_pace_min_km)

        # Round actual weekly km
        actual_weekly_km = [round(km, 1) for km in actual_weekly_km]

        # Build pace_by_week list
        pace_by_week = []
        for week_idx in sorted(pace_by_week_data.keys()):
            paces = pace_by_week_data[week_idx]
            avg_pace = round(sum(paces) / len(paces), 2)
            pace_by_week.append({
                'week_label': f'W{week_idx + 1}',
                'avg_pace': avg_pace,
            })

        # Completed count and total km
        completed_count = len(runs)
        total_km_logged = round(sum(r.distance_km or 0 for r in runs), 1)

        # Completion percentage
        completion_pct = round(completed_count / planned_count * 100) if planned_count > 0 else 0

        # Streak days: consecutive days backward from today with a run log
        today = datetime.now(timezone.utc).replace(tzinfo=None).date()
        streak_days = 0
        if runs:
            run_dates = set()
            for r in runs:
                rd = r.date.date() if isinstance(r.date, datetime) else r.date
                run_dates.add(rd)

            check_date = today
            while check_date in run_dates:
                streak_days += 1
                check_date -= timedelta(days=1)

        return {
            'planned_weekly_km': planned_weekly_km,
            'actual_weekly_km': actual_weekly_km,
            'pace_by_week': pace_by_week,
            'completed_count': completed_count,
            'planned_count': planned_count,
            'completion_pct': completion_pct,
            'streak_days': streak_days,
            'total_km_logged': total_km_logged,
        }
