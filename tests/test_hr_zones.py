"""Tests for heart rate zone calculator."""

import pytest

from app.core.training.hr_zone_calculator import HRZoneCalculator, ZONE_DEFINITIONS
from app.services.hr_zone_service import get_user_max_hr


class TestCalculateZones:
    def test_returns_five_zones(self):
        zones = HRZoneCalculator.calculate_zones(200)
        assert len(zones) == 5

    def test_zone_bpm_ranges_are_ascending(self):
        zones = HRZoneCalculator.calculate_zones(190)
        for i in range(len(zones) - 1):
            assert zones[i]["max_bpm"] <= zones[i + 1]["min_bpm"]

    def test_zone_1_starts_at_50_pct(self):
        zones = HRZoneCalculator.calculate_zones(200)
        assert zones[0]["min_bpm"] == 100  # 50% of 200

    def test_zone_5_max_is_max_hr(self):
        zones = HRZoneCalculator.calculate_zones(200)
        assert zones[4]["max_bpm"] == 200

    def test_typical_runner_zones(self):
        """A 30-year-old with max HR ~190 should get realistic zones."""
        zones = HRZoneCalculator.calculate_zones(190)
        z2 = next(z for z in zones if z["zone"] == 2)
        assert 110 <= z2["min_bpm"] <= 120
        assert 130 <= z2["max_bpm"] <= 140


class TestClassifyHR:
    def test_low_hr_returns_zone_1(self):
        zones = HRZoneCalculator.calculate_zones(200)
        assert HRZoneCalculator.classify_hr(80, zones) == 1

    def test_very_high_hr_returns_zone_5(self):
        zones = HRZoneCalculator.calculate_zones(200)
        assert HRZoneCalculator.classify_hr(195, zones) == 5

    def test_exact_boundary(self):
        zones = HRZoneCalculator.calculate_zones(200)
        z3_min = zones[2]["min_bpm"]  # Zone 3 min
        assert HRZoneCalculator.classify_hr(z3_min, zones) == 3

    def test_mid_zone_2(self):
        zones = HRZoneCalculator.calculate_zones(200)
        assert HRZoneCalculator.classify_hr(130, zones) == 2


class TestWorkoutZone:
    def test_easy_maps_to_zone_2(self):
        assert HRZoneCalculator.get_workout_zone("easy") == 2

    def test_recovery_maps_to_zone_1(self):
        assert HRZoneCalculator.get_workout_zone("recovery") == 1

    def test_interval_and_hill_map_to_zone_5(self):
        assert HRZoneCalculator.get_workout_zone("interval") == 5
        assert HRZoneCalculator.get_workout_zone("hill") == 5

    def test_unknown_defaults_to_zone_2(self):
        assert HRZoneCalculator.get_workout_zone("unknown") == 2


class TestZoneLabel:
    def test_format(self):
        zones = HRZoneCalculator.calculate_zones(200)
        label = HRZoneCalculator.zone_label(2, zones)
        assert "Zone 2" in label
        assert "Aerobic" in label
        assert "bpm" in label


class TestMaxHREstimation:
    def test_age_based_formula(self):
        # Tanaka formula: 208 - 0.7 * age
        assert HRZoneCalculator.estimate_max_hr_age_based(30) == 187
        assert HRZoneCalculator.estimate_max_hr_age_based(50) == 173

    def test_get_user_max_hr_no_data(self):
        """When no data available, returns default."""

        class FakeDB:
            def query(self, *a):
                return self
            def filter(self, *a):
                return self
            def order_by(self, *a):
                return self
            def first(self):
                return None

        hr, source = get_user_max_hr("user1", FakeDB())
        assert source == "default"
        assert hr == 190

    def test_get_user_max_hr_with_age(self):
        class FakeDB:
            def query(self, *a):
                return self
            def filter(self, *a):
                return self
            def order_by(self, *a):
                return self
            def first(self):
                return None

        hr, source = get_user_max_hr("user1", FakeDB(), user_age=35)
        assert source == "estimated"
        assert hr == round(208 - 0.7 * 35)
