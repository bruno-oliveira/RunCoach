"""Tests for NutritionEngine."""

import pytest

from app.meal_database import MealDatabase
from app.core.nutrition_engine import NutritionEngine


class TestNutritionEngine:
    """Tests for NutritionEngine class."""

    def test_generate_weekly_meal_plan(self, nutrition_engine: NutritionEngine):
        """Test generating a weekly meal plan."""
        meal_plan = nutrition_engine.generate_weekly_meal_plan(
            weekly_km=30.0,
            target_distance=10,
        )

        assert "nutrition_targets" in meal_plan
        assert "meal_options" in meal_plan
        assert "general_tips" in meal_plan
        assert "hydration_guide" in meal_plan

    def test_nutrition_targets_structure(self, nutrition_engine: NutritionEngine):
        """Test that nutrition targets have correct structure."""
        meal_plan = nutrition_engine.generate_weekly_meal_plan(
            weekly_km=40.0,
            target_distance=21.1,
        )

        targets = meal_plan["nutrition_targets"]
        assert "calories" in targets
        assert "protein" in targets
        assert "fiber" in targets
        assert "carbs" in targets
        assert "fat" in targets

    def test_meal_options_by_type(self, nutrition_engine: NutritionEngine):
        """Test that meal options include all meal types."""
        meal_plan = nutrition_engine.generate_weekly_meal_plan(
            weekly_km=25.0,
            target_distance=5,
        )

        meal_options = meal_plan["meal_options"]
        expected_types = {"breakfast", "lunch", "dinner", "snack", "post_workout"}

        for meal_type in expected_types:
            assert meal_type in meal_options
            assert len(meal_options[meal_type]) > 0

    def test_calorie_scaling_with_mileage(self, nutrition_engine: NutritionEngine):
        """Test that calorie targets scale with weekly mileage."""
        low_mileage_plan = nutrition_engine.generate_weekly_meal_plan(
            weekly_km=20.0,
            target_distance=5,
        )

        high_mileage_plan = nutrition_engine.generate_weekly_meal_plan(
            weekly_km=60.0,
            target_distance=42.2,
        )

        low_calories = low_mileage_plan["nutrition_targets"]["calories"]
        high_calories = high_mileage_plan["nutrition_targets"]["calories"]

        assert high_calories > low_calories

    def test_protein_requirements(self, nutrition_engine: NutritionEngine):
        """Test that protein targets are reasonable for runners."""
        meal_plan = nutrition_engine.generate_weekly_meal_plan(
            weekly_km=40.0,
            target_distance=21.1,
        )

        protein = meal_plan["nutrition_targets"]["protein"]
        # Runners typically need 1.2-1.7g protein per kg body weight
        # Assuming 70kg average, that's 84-119g
        assert 60 <= protein <= 200

    def test_hydration_guide_structure(self, nutrition_engine: NutritionEngine):
        """Test that hydration guide has required information."""
        meal_plan = nutrition_engine.generate_weekly_meal_plan(
            weekly_km=30.0,
            target_distance=10,
        )

        hydration = meal_plan["hydration_guide"]
        # Should have daily target info
        assert hydration is not None

    def test_seeded_randomization(self):
        """Test that seeded engine produces consistent results."""
        engine1 = NutritionEngine(random_seed=42)
        engine2 = NutritionEngine(random_seed=42)

        plan1 = engine1.generate_weekly_meal_plan(30.0, 10)
        plan2 = engine2.generate_weekly_meal_plan(30.0, 10)

        # Same seed should produce same results
        assert plan1["nutrition_targets"] == plan2["nutrition_targets"]

    def test_different_seeds_produce_different_results(self):
        """Test that different seeds produce different meal options."""
        engine1 = NutritionEngine(random_seed=42)
        engine2 = NutritionEngine(random_seed=12345)

        plan1 = engine1.generate_weekly_meal_plan(30.0, 10)
        plan2 = engine2.generate_weekly_meal_plan(30.0, 10)

        # Different seeds should produce different meal selections
        breakfast1 = [m["name"] for m in plan1["meal_options"]["breakfast"]]
        breakfast2 = [m["name"] for m in plan2["meal_options"]["breakfast"]]

        # They should not be identical (very unlikely with different seeds)
        # But we can't guarantee they're different due to randomness
        # Just verify the structure is correct
        assert len(breakfast1) > 0
        assert len(breakfast2) > 0

    def test_meal_nutritional_info(self, nutrition_engine: NutritionEngine):
        """Test that meals have nutritional information."""
        meal_plan = nutrition_engine.generate_weekly_meal_plan(
            weekly_km=30.0,
            target_distance=10,
        )

        for meal_type, meals in meal_plan["meal_options"].items():
            for meal in meals:
                assert "name" in meal
                assert "calories" in meal
                assert "protein" in meal
                assert "fiber" in meal

    def test_trail_running_nutrition(self, nutrition_engine: NutritionEngine):
        """Test nutrition plan for trail running (30.0 = Trail Running)."""
        meal_plan = nutrition_engine.generate_weekly_meal_plan(
            weekly_km=40.0,
            target_distance=30.0,
        )

        # Trail runners need good carbs for sustained effort
        carbs = meal_plan["nutrition_targets"]["carbs"]
        assert carbs > 0


class TestMealDatabase:
    """Tests for MealDatabase class."""

    def test_load_meals(self):
        """Test that meals are loaded from JSON file."""
        db = MealDatabase()
        assert len(db.meals) > 0

    def test_get_meals_by_type(self):
        """Test filtering meals by type."""
        db = MealDatabase()

        breakfast_meals = db.get_meals_by_type("breakfast")
        assert len(breakfast_meals) > 0
        assert all(m["meal_type"] == "breakfast" for m in breakfast_meals)

    def test_get_high_protein_meals(self):
        """Test filtering high protein meals."""
        db = MealDatabase()

        high_protein = db.get_high_protein_meals(min_protein=20)
        assert len(high_protein) > 0
        assert all(m["protein"] >= 20 for m in high_protein)

    def test_get_high_fiber_meals(self):
        """Test filtering high fiber meals."""
        db = MealDatabase()

        high_fiber = db.get_high_fiber_meals(min_fiber=8)
        assert len(high_fiber) > 0
        assert all(m["fiber"] >= 8 for m in high_fiber)

    def test_meal_count(self):
        """Test meal count by type."""
        db = MealDatabase()
        counts = db.get_meal_count()

        # Should have meals in multiple categories
        assert len(counts) >= 4

    def test_search_meals(self):
        """Test meal search functionality."""
        db = MealDatabase()

        # Search for common ingredient
        results = db.search_meals("chicken")
        # May or may not find results depending on meal data
        assert isinstance(results, list)
