"""Nutrition service for meal plan management."""

import json
import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models import TrainingPlan
from app.core.nutrition_engine import NutritionEngine
from app.schemas import parse_target_distance

logger = logging.getLogger(__name__)


class NutritionService:
    """Service for managing nutrition plans."""

    def __init__(self, db: Session, nutrition_engine: NutritionEngine | None = None):
        self.db = db
        self.nutrition_engine = nutrition_engine or NutritionEngine()

    def get_nutrition_plan(self, plan_id: str) -> dict[str, Any] | None:
        """Get nutrition plan for a training plan."""
        training_plan = (
            self.db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
        )
        if not training_plan or not training_plan.nutrition_plan_data:
            return None

        return json.loads(training_plan.nutrition_plan_data)

    def randomize_meals(self, plan_id: str) -> tuple[TrainingPlan, dict[str, Any]] | None:
        """
        Generate new randomized meal options for a training plan.

        Args:
            plan_id: Training plan ID

        Returns:
            Tuple of (TrainingPlan, new_nutrition_plan) or None if not found
        """
        training_plan = (
            self.db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
        )
        if not training_plan:
            return None

        # Use current time for random seed to ensure different results
        random_seed = int(time.time() * 1000000) % 100000000
        logger.info(f"Randomizing meals with seed: {random_seed}")

        # Create new nutrition engine with random seed
        nutrition_engine = NutritionEngine(random_seed=random_seed)

        # Store old meals for logging comparison
        old_meals = (
            json.loads(training_plan.nutrition_plan_data)
            if training_plan.nutrition_plan_data
            else None
        )

        # Generate new meal plan (convert string from DB to float)
        new_nutrition_plan = nutrition_engine.generate_weekly_meal_plan(
            training_plan.current_weekly_km,
            parse_target_distance(training_plan.target_distance),
        )

        # Log comparison
        if old_meals and isinstance(old_meals, dict) and isinstance(new_nutrition_plan, dict):
            old_meal_options = old_meals.get("meal_options", {})
            new_meal_options = new_nutrition_plan.get("meal_options", {})
            if isinstance(old_meal_options, dict) and isinstance(new_meal_options, dict):
                old_breakfast = [
                    m["name"]
                    for m in old_meal_options.get("breakfast", [])
                    if isinstance(m, dict) and "name" in m
                ]
                new_breakfast = [
                    m["name"]
                    for m in new_meal_options.get("breakfast", [])
                    if isinstance(m, dict) and "name" in m
                ]
                logger.info(f"Old breakfast options: {old_breakfast}")
                logger.info(f"New breakfast options: {new_breakfast}")

        # Update the plan
        training_plan.nutrition_plan_data = json.dumps(new_nutrition_plan)
        self.db.commit()

        logger.info(f"Randomized meals for plan {plan_id}")
        return training_plan, new_nutrition_plan

    def generate_nutrition_plan(
        self, current_km: float, target_distance: float
    ) -> dict[str, Any]:
        """Generate a new nutrition plan."""
        return self.nutrition_engine.generate_weekly_meal_plan(
            current_km, target_distance
        )

    def calculate_nutrition_needs(
        self,
        weekly_km: float,
        target_distance: float,
        body_weight: float = 70,
    ) -> dict[str, float]:
        """Calculate daily nutrition needs based on training load."""
        return self.nutrition_engine.calculate_nutrition_needs(
            weekly_km, target_distance, body_weight
        )
