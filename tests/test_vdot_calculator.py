"""Tests for VDOT calculator prediction methods."""

import pytest
from app.core.vdot_calculator import VDOTCalculator


class TestVDOTCalculator:
    """Test VDOT calculation and predictions."""

    def test_calculate_vdot_from_race(self):
        """VDOT calculation from race result."""
        vdot = VDOTCalculator.calculate_vdot(10.0, 3000)  # 10K in 50 min
        assert vdot == 40.0

    def test_calculate_vdot_5k(self):
        """VDOT calculation for 5K - 20 min 5K is fast."""
        vdot = VDOTCalculator.calculate_vdot(5.0, 1200)  # 5K in 20 min
        assert 48.0 <= vdot <= 51.0  # Fast runner

    def test_calculate_vdot_marathon(self):
        """VDOT calculation for marathon - 3hr marathon is fast."""
        vdot = VDOTCalculator.calculate_vdot(42.195, 10800)  # 3hr marathon
        assert 52.0 <= vdot <= 55.0  # Fast marathoner

    def test_calculate_vdot_invalid_inputs(self):
        """Handle invalid inputs."""
        assert VDOTCalculator.calculate_vdot(0, 100) is None
        assert VDOTCalculator.calculate_vdot(5.0, 0) is None
        assert VDOTCalculator.calculate_vdot(-5.0, 100) is None


class TestPredictionMethods:
    """Test race time prediction methods."""

    def test_predict_times_returns_all_distances(self):
        """predict_times returns predictions for all standard distances."""
        predictions = VDOTCalculator.predict_times(50.0)
        assert "5K" in predictions
        assert "10K" in predictions
        assert "trail" in predictions
        assert "half_marathon" in predictions
        assert "marathon" in predictions

    def test_predict_times_includes_formatted_time(self):
        """Predictions include formatted time string."""
        predictions = VDOTCalculator.predict_times(50.0)
        for name, pred in predictions.items():
            assert "formatted" in pred
            assert "seconds" in pred
            assert pred["seconds"] > 0

    def test_predict_time_for_distance(self):
        """predict_time_for_distance returns seconds for a specific distance."""
        time = VDOTCalculator.predict_time_for_distance(50.0, 5.0)
        assert time is not None
        assert 900 < time < 1800  # 5K should be ~15-30 min

    def test_predict_time_invalid_vdot(self):
        """Handle invalid VDOT values."""
        assert VDOTCalculator.predict_time_for_distance(10, 5.0) is None
        assert VDOTCalculator.predict_time_for_distance(90, 5.0) is None
        assert VDOTCalculator.predict_time_for_distance(50.0, 0) is None

    def test_confidence_range(self):
        """get_confidence_range returns fast/slow estimates."""
        range_data = VDOTCalculator.get_confidence_range(50.0, 5.0)
        assert "fast" in range_data
        assert "slow" in range_data
        assert "base" in range_data
        assert range_data["fast"] < range_data["base"]
        assert range_data["slow"] > range_data["base"]


class TestFormatting:
    """Test formatting utilities."""

    def test_format_duration_under_hour(self):
        """Format times under 1 hour."""
        assert VDOTCalculator.format_duration(180) == "3:00"
        assert VDOTCalculator.format_duration(3661) == "1:01:01"

    def test_format_duration_exact_minutes(self):
        """Format exact minute durations."""
        assert VDOTCalculator.format_duration(60) == "1:00"
        assert VDOTCalculator.format_duration(600) == "10:00"

    def test_validate_race_distance(self):
        """validate_race_distance works correctly."""
        assert VDOTCalculator.validate_race_distance(5.0) is True
        assert VDOTCalculator.validate_race_distance(10.0) is True
        assert VDOTCalculator.validate_race_distance(21.0975) is True
        assert VDOTCalculator.validate_race_distance(42.195) is True
        assert VDOTCalculator.validate_race_distance(3.0) is False
        assert VDOTCalculator.validate_race_distance(0) is False


class TestRoundTrip:
    """Test that predictions are consistent with VDOT calculation."""

    def test_roundtrip_5k(self):
        """Predicting 5K time and calculating VDOT gives same result."""
        original_vdot = 45.0
        predicted_time = VDOTCalculator.predict_time_for_distance(original_vdot, 5.0)
        assert predicted_time is not None
        calculated_vdot = VDOTCalculator.calculate_vdot(5.0, predicted_time)
        assert calculated_vdot is not None
        assert abs(calculated_vdot - original_vdot) < 0.5

    def test_roundtrip_marathon(self):
        """Predicting marathon time and calculating VDOT gives same result."""
        original_vdot = 50.0
        predicted_time = VDOTCalculator.predict_time_for_distance(original_vdot, 42.195)
        assert predicted_time is not None
        calculated_vdot = VDOTCalculator.calculate_vdot(42.195, predicted_time)
        assert calculated_vdot is not None
        assert abs(calculated_vdot - original_vdot) < 0.5
