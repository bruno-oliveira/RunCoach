"""Tests for beginner plan generation path (current_km=0)."""

import pytest

from app.core.beginner_plan_generator import BeginnerPlanGenerator
from app.core.plan_generator import TrainingPlanGenerator
from app.exceptions import ZeroMileageUnsupportedException


class TestBeginnerPlanGenerator:
    """Direct tests for the BeginnerPlanGenerator."""

    def test_5k_8_weeks_succeeds(self):
        gen = BeginnerPlanGenerator()
        plan = gen.generate_plan(target_distance=5.0, weeks=8)

        assert len(plan) == 8
        for week in plan:
            assert "week" in week
            assert "total_km" in week
            assert "daily_workouts" in week
            assert week.get("is_beginner_plan") is True

    def test_10k_12_weeks_succeeds(self):
        gen = BeginnerPlanGenerator()
        plan = gen.generate_plan(target_distance=10.0, weeks=12)

        assert len(plan) == 12
        # Weeks 9-12 should be extension weeks with actual distances
        for week in plan[8:]:
            total = sum(w.get("distance", 0) for w in week["daily_workouts"])
            assert total > 0, f"Week {week['week']} extension should have distance"

    def test_total_km_nonzero_for_couch_to_5k(self):
        """Regression: Couch-to-5K weeks must report nonzero total_km."""
        gen = BeginnerPlanGenerator()
        plan = gen.generate_plan(target_distance=5.0, weeks=8)

        for week in plan:
            assert week["total_km"] > 0, \
                f"Week {week['week']}: total_km should not be zero"

    def test_max_runs_capped_at_3(self):
        gen = BeginnerPlanGenerator()
        plan = gen.generate_plan(target_distance=5.0, weeks=8, max_runs_per_week=6)

        for week in plan:
            workout_count = len(week["daily_workouts"])
            assert workout_count <= 3


class TestZeroMileageThroughPlanGenerator:
    """Test the 0-km code path through TrainingPlanGenerator.generate_plan()."""

    def test_zero_km_5k_returns_beginner_plan(self):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(current_km=0, target_distance=5.0, weeks=8)

        assert len(plan) == 8
        assert plan[0].get("is_beginner_plan") is True

    def test_zero_km_10k_returns_beginner_plan(self):
        gen = TrainingPlanGenerator()
        plan = gen.generate_plan(current_km=0, target_distance=10.0, weeks=12)

        assert len(plan) == 12
        assert plan[0].get("is_beginner_plan") is True

    def test_zero_km_half_marathon_raises(self):
        gen = TrainingPlanGenerator()
        with pytest.raises(ZeroMileageUnsupportedException):
            gen.generate_plan(current_km=0, target_distance=21.1, weeks=12)

    def test_zero_km_marathon_raises(self):
        gen = TrainingPlanGenerator()
        with pytest.raises(ZeroMileageUnsupportedException):
            gen.generate_plan(current_km=0, target_distance=42.2, weeks=16)

    def test_zero_km_trail_raises(self):
        gen = TrainingPlanGenerator()
        with pytest.raises(ZeroMileageUnsupportedException):
            gen.generate_plan(current_km=0, target_distance=30.0, weeks=10)
