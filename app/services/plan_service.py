"""Plan generation and management service."""

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import DailyWorkout, TrainingPlan, User, WeeklyPlan
from app.core.nutrition_engine import NutritionEngine
from app.core.plan_generator import TrainingPlanGenerator
from app.schemas import parse_target_distance

logger = logging.getLogger(__name__)


class PlanService:
    """Service for managing training plans."""

    def __init__(
        self,
        db: Session,
        plan_generator: TrainingPlanGenerator | None = None,
        nutrition_engine: NutritionEngine | None = None,
    ):
        self.db = db
        self.plan_generator = plan_generator or TrainingPlanGenerator()
        self.nutrition_engine = nutrition_engine or NutritionEngine()

    def create_plan(
        self,
        current_km: float,
        target_distance: float,
        weeks: int,
    ) -> tuple[TrainingPlan, list[dict[str, Any]]]:
        """
        Create a new training plan with nutrition guidance.

        Args:
            current_km: Current weekly mileage in km
            target_distance: Target race distance
            weeks: Training duration in weeks

        Returns:
            Tuple of (TrainingPlan, plan_data)
        """
        # Generate training plan
        plan_data = self.plan_generator.generate_plan(
            current_km, target_distance, weeks
        )

        # Create user
        user = User()
        self.db.add(user)
        self.db.flush()

        # Create training plan
        training_plan = TrainingPlan(
            user_id=user.id,
            current_weekly_km=current_km,
            target_distance=target_distance,
            weeks_duration=weeks,
            plan_data=json.dumps(plan_data),
        )
        self.db.add(training_plan)
        self.db.flush()

        # Save weekly plans and daily workouts
        self._save_weekly_plans(training_plan.id, plan_data)

        # Generate and save nutrition plan
        nutrition_plan = self.nutrition_engine.generate_weekly_meal_plan(
            current_km, target_distance
        )
        training_plan.nutrition_plan_data = json.dumps(nutrition_plan)

        self.db.commit()

        logger.info(f"Created training plan {training_plan.id}")
        return training_plan, plan_data

    def _save_weekly_plans(
        self, training_plan_id: str, plan_data: list[dict[str, Any]]
    ) -> None:
        """Save weekly plans and daily workouts to database."""
        weekly_plans = []
        daily_workouts = []

        for week_data in plan_data:
            week_id = str(uuid.uuid4())
            weekly_plans.append({
                'id': week_id,
                'training_plan_id': training_plan_id,
                'week_number': week_data['week'],
                'total_km': week_data['total_km'],
                'workout_types': json.dumps(week_data.get('workout_distribution', {}))
            })

            for workout in week_data.get('daily_workouts', []):
                daily_workouts.append({
                    'id': str(uuid.uuid4()),
                    'weekly_plan_id': week_id,
                    'day_of_week': workout['day'],
                    'workout_type': workout['type'],
                    'distance_km': workout.get('distance', 0),
                    'intensity': workout.get('intensity', 'low'),
                    'notes': workout.get('notes', ''),
                })

        self.db.bulk_insert_mappings(WeeklyPlan, weekly_plans)
        self.db.bulk_insert_mappings(DailyWorkout, daily_workouts)
        self.db.commit()

    def get_plan(self, plan_id: str) -> TrainingPlan | None:
        """Get a training plan by ID."""
        return self.db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()

    def get_plan_data(self, plan_id: str) -> tuple[TrainingPlan, list[dict]] | None:
        """Get a training plan with parsed plan data."""
        training_plan = self.get_plan(plan_id)
        if not training_plan:
            return None

        plan_data = json.loads(training_plan.plan_data)
        return training_plan, plan_data

    def ensure_nutrition_plan(self, training_plan: TrainingPlan) -> dict[str, Any]:
        """Ensure nutrition plan exists, generating if needed."""
        if not training_plan.nutrition_plan_data:
            nutrition_plan = self.nutrition_engine.generate_weekly_meal_plan(
                training_plan.current_weekly_km,
                parse_target_distance(training_plan.target_distance),
            )
            training_plan.nutrition_plan_data = json.dumps(nutrition_plan)
            self.db.commit()
            return nutrition_plan

        return json.loads(training_plan.nutrition_plan_data)

    def update_plan_data(
        self, plan_id: str, plan_data: list[dict[str, Any]]
    ) -> TrainingPlan | None:
        """Update plan data for a training plan."""
        training_plan = self.get_plan(plan_id)
        if not training_plan:
            return None

        training_plan.plan_data = json.dumps(plan_data)
        self.db.commit()

        logger.info(f"Updated training plan {plan_id}")
        return training_plan
