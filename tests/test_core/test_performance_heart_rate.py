"""Tests for max heart rate zone calculation functionality."""

from datetime import datetime, timedelta, timezone

import pytest

from app.contexts.plan.generators.performance_plan_generator import (
    PerformancePlanGenerator,
)
from app.contexts.runner.fitness.performance_service import PerformanceService
from app.models import RunLog, User


class TestHeartRateZoneCalculation:
    """Test heart rate zone calculation with and without max HR."""

    def test_calculate_zones_with_max_hr(self):
        """Test that BPM ranges are calculated correctly when max_hr is provided."""
        generator = PerformancePlanGenerator()
        goal_pace = 5.0  # 5:00/km
        max_hr = 180

        zones = generator.calculate_training_zones(goal_pace, max_hr)

        # Verify all zones exist
        assert "zone_1_recovery" in zones
        assert "zone_2_aerobic" in zones
        assert "zone_3_tempo" in zones
        assert "zone_4_vo2max" in zones
        assert "zone_5_race" in zones

        # Verify BPM ranges are present
        assert "hr_bpm_range" in zones["zone_1_recovery"]
        assert "hr_bpm_range" in zones["zone_2_aerobic"]
        assert "hr_bpm_range" in zones["zone_3_tempo"]
        assert "hr_bpm_range" in zones["zone_4_vo2max"]
        assert "hr_bpm_range" in zones["zone_5_race"]

        # Verify BPM calculations are correct
        # Zone 1: 60-70% of 180 = 108-126 BPM (int conversion may round down)
        assert zones["zone_1_recovery"]["hr_bpm_range"] in [
            "108-126 BPM",
            "108-125 BPM",
        ]

        # Zone 2: 70-80% of 180 = 126-144 BPM
        assert zones["zone_2_aerobic"]["hr_bpm_range"] in ["126-144 BPM", "125-144 BPM"]

        # Zone 3: 80-88% of 180 = 144-158 BPM
        assert zones["zone_3_tempo"]["hr_bpm_range"] == "144-158 BPM"

        # BPM bands now come from the single HR-zone authority (LTHR-anchored,
        # here the 88%-of-max default), not a separate flat-%max truncation, so
        # the upper bands differ by ~1 BPM from the old computation.
        # Zone 4: 158-170 BPM
        assert zones["zone_4_vo2max"]["hr_bpm_range"] == "158-170 BPM"

        # Zone 5: 170-180 BPM (top capped at max HR)
        assert zones["zone_5_race"]["hr_bpm_range"] == "170-180 BPM"

        # Verify percentage ranges are still present
        assert zones["zone_1_recovery"]["hr_range"] == "60-70%"
        assert zones["zone_5_race"]["hr_range"] == "95-100%"

    def test_calculate_zones_without_max_hr(self):
        """Test backwards compatibility - zones work without max_hr."""
        generator = PerformancePlanGenerator()
        goal_pace = 5.0  # 5:00/km

        zones = generator.calculate_training_zones(goal_pace)

        # Verify all zones exist
        assert "zone_1_recovery" in zones
        assert "zone_2_aerobic" in zones
        assert "zone_3_tempo" in zones
        assert "zone_4_vo2max" in zones
        assert "zone_5_race" in zones

        # Verify BPM ranges are NOT present
        assert "hr_bpm_range" not in zones["zone_1_recovery"]
        assert "hr_bpm_range" not in zones["zone_5_race"]

        # Verify percentage ranges are still present
        assert zones["zone_1_recovery"]["hr_range"] == "60-70%"
        assert zones["zone_5_race"]["hr_range"] == "95-100%"

        # Verify pace calculations still work
        assert zones["zone_1_recovery"]["pace"] == pytest.approx(6.5, rel=0.1)
        assert zones["zone_5_race"]["pace"] == pytest.approx(5.0, rel=0.1)

    def test_generate_plan_with_max_hr(self):
        """Test that generate_plan passes max_hr to zones correctly."""
        generator = PerformancePlanGenerator()

        plan = generator.generate_plan(
            target_distance=10.0,
            current_pace=5.5,
            goal_pace=5.0,
            weeks=8,
            current_weekly_km=40,
            runs_per_week=5,
            max_heart_rate=185,
        )

        # Verify training zones include BPM ranges
        zones = plan["training_zones"]
        assert "hr_bpm_range" in zones["zone_1_recovery"]
        # LTHR-anchored (88%-of-max default) canonical band for max 185.
        assert zones["zone_1_recovery"]["hr_bpm_range"] == "111-130 BPM"

    def test_generate_plan_without_max_hr(self):
        """Test that generate_plan works without max_hr (backwards compatible)."""
        generator = PerformancePlanGenerator()

        plan = generator.generate_plan(
            target_distance=10.0,
            current_pace=5.5,
            goal_pace=5.0,
            weeks=8,
            current_weekly_km=40,
            runs_per_week=5,
        )

        # Verify training zones work without BPM ranges
        zones = plan["training_zones"]
        assert "hr_bpm_range" not in zones["zone_1_recovery"]
        assert zones["zone_1_recovery"]["hr_range"] == "60-70%"


class TestMaxHeartRateCalculation:
    """Test automatic max heart rate calculation."""

    def test_calculate_max_hr_from_run_logs(self, test_db):
        """Test max HR calculation from RunLog data (highest confidence)."""
        # Create a test user
        user = User(id="test-user", email="test@example.com")
        test_db.add(user)

        # Add runs with heart rate data
        base_date = datetime.now(timezone.utc).replace(tzinfo=None)
        hr_values = [175, 178, 182, 180, 185, 183, 179, 184, 181, 186]

        for i, hr in enumerate(hr_values):
            run = RunLog(
                user_id=user.id,
                date=base_date - timedelta(days=i * 3),
                distance_km=8.0,
                duration_minutes=40.0,
                avg_pace_min_km=5.0,
                max_heart_rate=hr,
            )
            test_db.add(run)

        test_db.commit()

        # Calculate max HR
        service = PerformanceService(test_db)
        result = service.calculate_max_heart_rate(user_id=user.id, goal_pace=5.0)

        # Should return 98th percentile
        assert result["confidence"] == "high"
        assert result["source"] == "run_data"
        # 98th percentile of [175, 178, 179, 180, 181, 182, 183, 184, 185, 186] ≈ 185-186
        assert result["max_hr"] in [185, 186]
        assert "runs with heart rate data" in result["message"]

    def test_calculate_max_hr_from_age(self, test_db):
        """Test max HR calculation from age formula (medium confidence)."""
        # Create a test user with age but no run data
        user = User(id="test-user-age", email="test2@example.com", age=30)
        test_db.add(user)
        test_db.commit()

        service = PerformanceService(test_db)
        result = service.calculate_max_heart_rate(user_id=user.id, goal_pace=5.0)

        # Should use age formula: 220 - 30 = 190
        assert result["confidence"] == "medium"
        assert result["source"] == "age_formula"
        assert result["max_hr"] == 190
        assert "220 - 30" in result["message"]

    def test_calculate_max_hr_from_pace_fast(self, test_db):
        """Test max HR estimation from fast pace (low confidence)."""
        # Create a test user with no age and no run data
        user = User(id="test-user-pace", email="test3@example.com")
        test_db.add(user)
        test_db.commit()

        service = PerformanceService(test_db)
        result = service.calculate_max_heart_rate(
            user_id=user.id,
            goal_pace=4.0,  # Fast pace
        )

        # Should estimate based on pace
        assert result["confidence"] == "low"
        assert result["source"] == "pace_estimation"
        assert result["max_hr"] == 185
        assert "fast" in result["message"]

    def test_calculate_max_hr_from_pace_average(self, test_db):
        """Test max HR estimation from average pace (low confidence)."""
        user = User(id="test-user-avg", email="test4@example.com")
        test_db.add(user)
        test_db.commit()

        service = PerformanceService(test_db)
        result = service.calculate_max_heart_rate(
            user_id=user.id,
            goal_pace=5.5,  # Average pace
        )

        assert result["confidence"] == "low"
        assert result["source"] == "pace_estimation"
        assert result["max_hr"] == 180
        assert "average" in result["message"]

    def test_calculate_max_hr_from_pace_slow(self, test_db):
        """Test max HR estimation from slower pace (low confidence)."""
        user = User(id="test-user-slow", email="test5@example.com")
        test_db.add(user)
        test_db.commit()

        service = PerformanceService(test_db)
        result = service.calculate_max_heart_rate(
            user_id=user.id,
            goal_pace=7.0,  # Slower pace
        )

        assert result["confidence"] == "low"
        assert result["source"] == "pace_estimation"
        assert result["max_hr"] == 175
        assert "slower" in result["message"]

    def test_calculate_max_hr_insufficient_runs(self, test_db):
        """Test that insufficient runs (<5) fall back to age or pace."""
        user = User(id="test-user-few", email="test6@example.com", age=35)
        test_db.add(user)

        # Add only 3 runs (less than minimum 5)
        for i in range(3):
            run = RunLog(
                user_id=user.id,
                date=datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(days=i),
                distance_km=5.0,
                duration_minutes=25.0,
                avg_pace_min_km=5.0,
                max_heart_rate=180,
            )
            test_db.add(run)

        test_db.commit()

        service = PerformanceService(test_db)
        result = service.calculate_max_heart_rate(user_id=user.id, goal_pace=5.0)

        # Should fall back to age formula
        assert result["source"] == "age_formula"
        assert result["max_hr"] == 185  # 220 - 35


class TestIntegrationPerformancePlan:
    """Integration tests for complete performance plan with HR zones."""

    def test_create_plan_with_max_hr(self, test_db):
        """Test creating a complete performance plan with max HR."""
        user = User(id="test-integration", email="integration@example.com")
        test_db.add(user)
        test_db.commit()

        service = PerformanceService(test_db)
        training_plan, plan_data = service.create_performance_plan(
            user=user,
            target_distance=10.0,
            goal_pace=5.0,
            weeks=8,
            current_pace=5.5,
            current_weekly_km=40,
            goal_time="50:00",
            current_time="55:00",
            runs_per_week=5,
            max_heart_rate=180,
        )

        # Verify training plan has max_hr
        assert training_plan.max_heart_rate == 180

        # Verify zones include BPM ranges
        zones = plan_data["training_zones"]
        assert "hr_bpm_range" in zones["zone_1_recovery"]
        assert zones["zone_1_recovery"]["hr_bpm_range"] in [
            "108-126 BPM",
            "108-125 BPM",
        ]

    def test_create_plan_without_max_hr(self, test_db):
        """Test creating a performance plan without max HR (backwards compatible)."""
        user = User(id="test-no-hr", email="nohr@example.com")
        test_db.add(user)
        test_db.commit()

        service = PerformanceService(test_db)
        training_plan, plan_data = service.create_performance_plan(
            user=user,
            target_distance=10.0,
            goal_pace=5.0,
            weeks=8,
            current_pace=5.5,
            current_weekly_km=40,
            goal_time="50:00",
            current_time="55:00",
            runs_per_week=5,
            max_heart_rate=None,
        )

        # Verify training plan has no max_hr
        assert training_plan.max_heart_rate is None

        # Verify zones work without BPM ranges
        zones = plan_data["training_zones"]
        assert "hr_bpm_range" not in zones["zone_1_recovery"]
        assert zones["zone_1_recovery"]["hr_range"] == "60-70%"

    def test_retrieve_plan_with_max_hr(self, test_db):
        """Test retrieving a plan preserves max HR in zones."""
        user = User(id="test-retrieve", email="retrieve@example.com")
        test_db.add(user)
        test_db.commit()

        # Create plan
        service = PerformanceService(test_db)
        training_plan, _ = service.create_performance_plan(
            user=user,
            target_distance=10.0,
            goal_pace=5.0,
            weeks=8,
            current_pace=5.5,
            current_weekly_km=40,
            goal_time="50:00",
            runs_per_week=5,
            max_heart_rate=185,
        )

        # Retrieve plan
        retrieved_plan, retrieved_data = service.get_plan_with_data(training_plan.id)

        # Verify max_hr is preserved
        assert retrieved_plan.max_heart_rate == 185
        assert retrieved_data["max_heart_rate"] == 185

        # Verify zones still have BPM ranges
        zones = retrieved_data["training_zones"]
        assert "hr_bpm_range" in zones["zone_1_recovery"]
