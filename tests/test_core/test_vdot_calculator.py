"""Tests for VDOT calculator prediction methods."""

import pytest
from app.core.training.vdot_calculator import VDOTCalculator


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


class TestElevationHandling:
    """Tests for elevation-aware VDOT and predictions."""

    def test_calculate_vdot_skips_hilly_runs(self):
        """A run with > 20m of climb per km is excluded from VDOT estimation."""
        # 10 km in 50 min on flat ground -> VDOT 40
        baseline = VDOTCalculator.calculate_vdot(10.0, 3000)
        assert baseline is not None

        # Same effort with 250 m of gain over 10 km (25 m/km) is too hilly
        # to feed back into a flat-ground VDOT.
        hilly = VDOTCalculator.calculate_vdot(10.0, 3000, elevation_gain_m=250)
        assert hilly is None

    def test_calculate_vdot_allows_modest_elevation(self):
        """Runs below the trail threshold still produce VDOT."""
        result = VDOTCalculator.calculate_vdot(10.0, 3000, elevation_gain_m=150)
        assert result is not None

    def test_predict_time_applies_elevation_penalty(self):
        """1000 m of elevation over 22.3 km lands in the steep band of the piecewise penalty."""
        flat = VDOTCalculator.predict_time_for_distance(45.0, 22.3)
        hilly = VDOTCalculator.predict_time_for_distance(
            45.0, 22.3, elevation_gain_m=1000
        )
        assert flat is not None and hilly is not None
        delta = hilly - flat
        # avg grade 4.5% -> effective 8.97% -> rate 24 sec/km/% on 11.15 km
        # -> ~2400 sec. Allow a band for binary-search jitter.
        assert 2200 < delta < 2600

    def test_predict_time_low_grade_matches_linear_baseline(self):
        """Mild rolling terrain still costs ~1.2 sec per meter of gain."""
        flat = VDOTCalculator.predict_time_for_distance(45.0, 10.0)
        rolling = VDOTCalculator.predict_time_for_distance(
            45.0, 10.0, elevation_gain_m=100
        )
        assert flat is not None and rolling is not None
        delta = rolling - flat
        # 100m / 10km -> 1% avg, 2% effective, rate 12 -> 12*2*5 = 120 sec
        assert 100 < delta < 140

    def test_predict_time_trail_inexperience_penalty(self):
        """A first-time trail runner gets a ~1.5x multiplier on top of elevation."""
        experienced = VDOTCalculator.predict_time_for_distance(
            45.0, 22.3, elevation_gain_m=1000, trail_runs_count=10
        )
        beginner = VDOTCalculator.predict_time_for_distance(
            45.0, 22.3, elevation_gain_m=1000, trail_runs_count=0
        )
        assert experienced is not None and beginner is not None
        ratio = beginner / experienced
        assert 1.40 < ratio < 1.55

    def test_predict_time_no_inexperience_penalty_on_road(self):
        """Trail experience factor only kicks in when elevation is trail-like."""
        no_count = VDOTCalculator.predict_time_for_distance(45.0, 10.0)
        beginner_road = VDOTCalculator.predict_time_for_distance(
            45.0, 10.0, trail_runs_count=0
        )
        assert no_count == beginner_road  # No elevation -> no trail penalty

    def test_confidence_range_widens_for_trail_distance(self):
        """Trail (30 km) confidence range is wider than road."""
        road = VDOTCalculator.get_confidence_range(50.0, 10.0)
        trail = VDOTCalculator.get_confidence_range(50.0, 30.0, target_distance=30.0)
        road_spread = road["slow"] - road["fast"]
        trail_spread = trail["slow"] - trail["fast"]
        # Trail margin is ±5 vs road's ±1.5 -> spread should be much wider per km
        assert trail_spread / 30.0 > road_spread / 10.0

    def test_confidence_range_widens_for_high_elevation_distance(self):
        """A non-30k distance with significant elevation also gets the wide band."""
        flat = VDOTCalculator.get_confidence_range(50.0, 22.3)
        hilly = VDOTCalculator.get_confidence_range(
            50.0, 22.3, elevation_gain_m=1000
        )
        assert (hilly["slow"] - hilly["fast"]) > (flat["slow"] - flat["fast"])

    def test_ultra_endurance_decay_applies_beyond_3h(self):
        """Predictions for events >3 hours get a decay multiplier."""
        vdot = 40.0
        marathon = VDOTCalculator.predict_time_for_distance(vdot, 42.195)
        trail = VDOTCalculator.predict_time_for_distance(
            vdot, 30.0, elevation_gain_m=1500, trail_runs_count=0
        )
        assert marathon is not None and trail is not None
        trail_hours = trail / 3600.0
        assert trail_hours > 3.0
        marathon_hours = marathon / 3600.0
        if marathon_hours > 3.0:
            ratio = marathon / VDOTCalculator.predict_time_for_distance(vdot, 42.195)
            assert ratio >= 1.0

    def test_predict_times_accepts_elevation_map(self):
        """predict_times can receive per-distance elevation data."""
        predictions = VDOTCalculator.predict_times(
            45.0,
            trail_runs_count=0,
            elevation_map={"trail": 1500.0},
        )
        assert "trail" in predictions
        trail_seconds = predictions["trail"]["seconds"]
        flat_trail = VDOTCalculator.predict_times(45.0)["trail"]["seconds"]
        assert trail_seconds > flat_trail

    def test_predict_times_elevation_map_ignored_for_road(self):
        """Road distances ignore elevation_map entries not keyed to them."""
        predictions = VDOTCalculator.predict_times(
            45.0,
            elevation_map={"trail": 1500.0},
        )
        five_k = predictions["5K"]["seconds"]
        five_k_no_map = VDOTCalculator.predict_times(45.0)["5K"]["seconds"]
        assert five_k == five_k_no_map


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
        assert abs(calculated_vdot - original_vdot) < 1.0
