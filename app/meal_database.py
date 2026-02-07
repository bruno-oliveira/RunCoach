"""Meal database for nutrition planning.

Loads meal data from external JSON file for easier maintenance.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Path to meal data directory
MEALS_DATA_DIR = Path(__file__).parent / "data"

# Individual meal type files
MEAL_TYPE_FILES = {
    "breakfast": "meals_breakfast.json",
    "lunch": "meals_lunch.json",
    "dinner": "meals_dinner.json",
    "snack": "meals_snack.json",
    "post_workout": "meals_post_workout.json",
}


class MealDatabase:
    """Database of healthy, protein and fiber-focused meals for runners."""

    def __init__(self, data_dir: Path | None = None):
        """
        Initialize the meal database.

        Args:
            data_dir: Optional path to meals data directory. Defaults to data/.
        """
        self.data_dir = data_dir or MEALS_DATA_DIR
        self.meals = self._load_meals()

    def _load_meals(self) -> list[dict[str, Any]]:
        """Load meals from dedicated JSON files."""
        meals = []
        for meal_type, filename in MEAL_TYPE_FILES.items():
            file_path = self.data_dir / filename
            try:
                with open(file_path, "r") as f:
                    type_meals = json.load(f)
                    meals.extend(type_meals)
                    logger.info(f"Loaded {len(type_meals)} {meal_type} meals from {file_path}")
            except FileNotFoundError:
                logger.warning(f"Meals file not found: {file_path}")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing meals file {file_path}: {e}")
        
        logger.info(f"Loaded {len(meals)} total meals")
        return meals

    def get_meals_by_type(self, meal_type: str) -> list[dict[str, Any]]:
        """Get all meals of a specific type."""
        return [meal for meal in self.meals if meal["meal_type"] == meal_type]

    def get_high_protein_meals(self, min_protein: float = 20) -> list[dict[str, Any]]:
        """Get meals with high protein content."""
        return [meal for meal in self.meals if meal["protein"] >= min_protein]

    def get_high_fiber_meals(self, min_fiber: float = 8) -> list[dict[str, Any]]:
        """Get meals with high fiber content."""
        return [meal for meal in self.meals if meal["fiber"] >= min_fiber]

    def get_meal_by_name(self, name: str) -> dict[str, Any] | None:
        """Get a specific meal by name."""
        for meal in self.meals:
            if meal["name"] == name:
                return meal
        return None

    def get_meals_by_tags(
        self, tags: list[str], match_all: bool = False
    ) -> list[dict[str, Any]]:
        """
        Get meals matching dietary tags.

        Args:
            tags: List of dietary tags to match
            match_all: If True, meal must have all tags. If False, any tag matches.
        """
        matching_meals = []
        for meal in self.meals:
            meal_tags = meal.get("dietary_tags", [])
            if match_all:
                if all(tag in meal_tags for tag in tags):
                    matching_meals.append(meal)
            else:
                if any(tag in meal_tags for tag in tags):
                    matching_meals.append(meal)
        return matching_meals

    def get_daily_meal_plan(
        self,
        target_calories: float = 2000,
        target_protein: float = 120,
        target_fiber: float = 30,
    ) -> dict[str, list[dict[str, Any]]]:
        """Generate a balanced daily meal plan."""
        meal_plan = {
            "breakfast": [],
            "lunch": [],
            "dinner": [],
            "snack": [],
            "post_workout": [],
        }

        for meal_type in meal_plan:
            available_meals = self.get_meals_by_type(meal_type)
            if available_meals:
                # Prioritize high protein and fiber meals
                scored_meals = []
                for meal in available_meals:
                    score = 0
                    if meal["protein"] >= 20:
                        score += 2
                    if meal["fiber"] >= 8:
                        score += 2
                    if meal["protein"] >= 15:
                        score += 1
                    if meal["fiber"] >= 5:
                        score += 1
                    scored_meals.append((score, meal))

                scored_meals.sort(key=lambda x: x[0], reverse=True)
                if scored_meals:
                    meal_plan[meal_type].append(scored_meals[0][1])

        return meal_plan

    def get_meal_count(self) -> dict[str, int]:
        """Get count of meals by type."""
        counts = {}
        for meal in self.meals:
            meal_type = meal["meal_type"]
            counts[meal_type] = counts.get(meal_type, 0) + 1
        return counts

    def search_meals(self, query: str) -> list[dict[str, Any]]:
        """Search meals by name or description."""
        query = query.lower()
        return [
            meal
            for meal in self.meals
            if query in meal["name"].lower()
            or query in meal.get("description", "").lower()
        ]


@lru_cache(maxsize=1)
def get_meal_database() -> MealDatabase:
    """Get singleton MealDatabase instance (cached)."""
    return MealDatabase()
