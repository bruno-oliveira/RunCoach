"""Meal selection with variety scoring."""

import random
from typing import Any, Dict, Optional, Set

from app.contexts.nutrition.meal_database import get_meal_database


class MealSelector:
    """Selects meals with emphasis on variety and nutritional scoring."""

    def __init__(self, rng: random.Random):
        self.meal_db = get_meal_database()
        self._rng = rng

    def select_varied_meal(
        self,
        meal_type: str,
        nutrition_needs: Dict[str, float],
        used_meals: Set[str],
    ) -> Optional[Dict[str, Any]]:
        """Select a meal with emphasis on variety from already used meals."""
        available_meals = self.meal_db.get_meals_by_type(meal_type)

        remaining_meals = [
            meal for meal in available_meals if meal["name"] not in used_meals
        ]

        if len(remaining_meals) < 2:
            remaining_meals = available_meals

        self._rng.shuffle(remaining_meals)

        scored_meals = []
        for meal in remaining_meals:
            score = 0

            for nutrient in ["protein", "fiber"]:
                if meal[nutrient] > 0:
                    score += meal[nutrient] * (0.3 if nutrient == "protein" else 0.2)

            if meal["name"] not in used_meals:
                score += 10
            else:
                score -= 20

            score += self._rng.uniform(0, 15)

            scored_meals.append((score, meal))

        if scored_meals:
            scored_meals.sort(key=lambda x: x[0], reverse=True)
            top_meals = scored_meals[: min(8, len(scored_meals))]
            weights = [8, 7, 6, 5, 4, 3, 2, 1][: len(top_meals)]
            selected = self._rng.choices(top_meals, weights=weights)[0][1]
            return selected

        return None
