"""Tests for the trail profile classifier.

Boundary-focused — every bracket and elevation-class cutoff has a pair of
just-below / just-at cases so a future change to a constant has to update
the test (not slip through on rounding).
"""

import pytest

from app.core.training.trail_profile import (
    TRAIL_DISTANCE_MAX_KM,
    TRAIL_DISTANCE_MIN_KM,
    TRAIL_ELEVATION_MAX_M,
    TrailProfile,
    classify_trail,
    trail_max_weekly_mileage,
    trail_max_weeks,
    trail_min_runs_per_week,
    trail_min_weekly_mileage,
    trail_min_weeks,
)


class TestBracketClassification:
    """Distance bracket: short (<21) / standard (<42.2) / ultra (<80) / long_ultra."""

    @pytest.mark.parametrize(
        "distance_km,expected",
        [
            (TRAIL_DISTANCE_MIN_KM, "short"),
            (8.0, "short"),
            (15.0, "short"),
            (20.99, "short"),
            (21.0, "standard"),
            (30.0, "standard"),
            (42.19, "standard"),
            (42.2, "ultra"),
            (50.0, "ultra"),
            (79.99, "ultra"),
            (80.0, "long_ultra"),
            (100.0, "long_ultra"),
            (TRAIL_DISTANCE_MAX_KM, "long_ultra"),
        ],
    )
    def test_bracket_at_boundaries(self, distance_km, expected):
        profile = classify_trail(distance_km, elevation_gain_m=500.0)
        assert profile.bracket == expected


class TestElevationClassification:
    """Elevation class: flat (<10 m/km) / rolling (<25) / hilly (<50) / mountainous."""

    @pytest.mark.parametrize(
        "distance_km,elevation_m,expected",
        [
            # 0 vert is always flat
            (50.0, 0.0, "flat"),
            # Just below / at flat→rolling boundary (10 m/km)
            (50.0, 499.0, "flat"),
            (50.0, 500.0, "rolling"),
            # Just below / at rolling→hilly boundary (25 m/km)
            (50.0, 1249.0, "rolling"),
            (50.0, 1250.0, "hilly"),
            # Just below / at hilly→mountainous boundary (50 m/km)
            (50.0, 2499.0, "hilly"),
            (50.0, 2500.0, "mountainous"),
            # Steep ITRA-style mountain race
            (100.0, 5000.0, "mountainous"),
            (50.0, TRAIL_ELEVATION_MAX_M, "mountainous"),
        ],
    )
    def test_elevation_class_at_boundaries(self, distance_km, elevation_m, expected):
        profile = classify_trail(distance_km, elevation_gain_m=elevation_m)
        assert profile.elevation_class == expected

    def test_zero_distance_does_not_divide(self):
        """Defensive: distance=0 must not raise."""
        profile = classify_trail(0.0, 500.0)
        assert profile.elevation_class == "flat"
        assert profile.m_per_km == 0.0


class TestProfileProperties:
    """is_ultra / is_long_ultra / category_key derived properties."""

    def test_is_ultra_for_ultra_and_long_ultra(self):
        assert classify_trail(50.0, 1000.0).is_ultra is True
        assert classify_trail(100.0, 3000.0).is_ultra is True

    def test_is_ultra_false_for_short_and_standard(self):
        assert classify_trail(15.0, 300.0).is_ultra is False
        assert classify_trail(30.0, 1500.0).is_ultra is False

    def test_is_long_ultra_only_for_long_ultra_bracket(self):
        assert classify_trail(80.0, 2000.0).is_long_ultra is True
        assert classify_trail(163.0, 6000.0).is_long_ultra is True
        assert classify_trail(50.0, 2000.0).is_long_ultra is False
        assert classify_trail(30.0, 1500.0).is_long_ultra is False

    def test_m_per_km_calculation(self):
        # 50 km, 1500 m → 30 m/km (hilly band)
        profile = classify_trail(50.0, 1500.0)
        assert profile.m_per_km == pytest.approx(30.0)
        assert profile.elevation_class == "hilly"

    def test_category_key_format(self):
        # Backward-compat baseline: 30 km / 1000 m → 33 m/km → standard / hilly.
        # (The historical hardcoded "Trail" prescribed moderate hill work, which
        # corresponds to the hilly band, not mountainous.)
        profile = classify_trail(30.0, 1000.0)
        assert profile.category_key == "Trail_standard_hilly"

        # User's flat-50k flag scenario
        profile = classify_trail(50.0, 200.0)
        assert profile.category_key == "Trail_ultra_flat"

        # 100-mile race with significant vert: 6000 / 163 ≈ 36.8 m/km → hilly
        profile = classify_trail(163.0, 6000.0)
        assert profile.category_key == "Trail_long_ultra_hilly"

        # A truly mountainous 100-miler (e.g. UTMB-class): 9000 / 163 ≈ 55 m/km
        profile_mountain = classify_trail(163.0, 9000.0)
        assert profile_mountain.category_key == "Trail_long_ultra_mountainous"

    def test_profile_is_frozen(self):
        """Frozen dataclass — generators can use it as a dict key / cache key."""
        profile = classify_trail(30.0, 1500.0)
        with pytest.raises(Exception):
            profile.distance_km = 42.0  # type: ignore[misc]


class TestKnownScenarios:
    """End-to-end scenarios from the implementation plan's verification list."""

    def test_legacy_30km_hilly_default(self):
        """Backward compat: the historic default trail plan (~33 m/km is hilly)."""
        profile = classify_trail(30.0, 1000.0)
        assert profile.bracket == "standard"
        assert profile.elevation_class == "hilly"

    def test_legacy_30km_mountainous_steep(self):
        """A 30 km race with 1500 m vert is genuinely mountainous (50 m/km exactly)."""
        profile = classify_trail(30.0, 1500.0)
        assert profile.elevation_class == "mountainous"

    def test_legacy_30km_flat_terrain(self):
        """Backward compat: the historic 'flat' terrain toggle."""
        # 300 / 30 = 10 m/km exactly → rolling (10 is the upper-exclusive cutoff)
        profile_at_boundary = classify_trail(30.0, 300.0)
        assert profile_at_boundary.bracket == "standard"
        assert profile_at_boundary.elevation_class == "rolling"

        # 200 / 30 ≈ 6.7 m/km → flat
        profile_truly_flat = classify_trail(30.0, 200.0)
        assert profile_truly_flat.elevation_class == "flat"

    def test_short_rolling_15km(self):
        profile = classify_trail(15.0, 500.0)  # 33 m/km
        assert profile.bracket == "short"
        assert profile.elevation_class == "hilly"

    def test_flat_50k(self):
        profile = classify_trail(50.0, 200.0)  # 4 m/km
        assert profile.bracket == "ultra"
        assert profile.elevation_class == "flat"
        assert profile.is_ultra is True

    def test_mountain_80k(self):
        profile = classify_trail(80.0, 4500.0)  # 56 m/km
        assert profile.bracket == "long_ultra"
        assert profile.elevation_class == "mountainous"

    def test_100_miler(self):
        profile = classify_trail(163.0, 6000.0)  # ~37 m/km
        assert profile.bracket == "long_ultra"
        assert profile.elevation_class == "hilly"
        assert profile.is_long_ultra is True


class TestBracketConstraints:
    """Bracket-aware plan constraints used by PlanRequest validators."""

    @pytest.mark.parametrize(
        "distance_km,expected_min,expected_max",
        [
            (15.0, 5, 18),  # short
            (30.0, 6, 22),  # standard
            (50.0, 12, 32),  # ultra
            (100.0, 16, 40),  # long_ultra
        ],
    )
    def test_min_max_weeks_by_bracket(self, distance_km, expected_min, expected_max):
        profile = classify_trail(distance_km, 1000.0)
        assert trail_min_weeks(profile) == expected_min
        assert trail_max_weeks(profile) == expected_max

    @pytest.mark.parametrize(
        "distance_km,expected_runs",
        [(15.0, 3), (30.0, 4), (50.0, 5), (100.0, 6)],
    )
    def test_min_runs_by_bracket(self, distance_km, expected_runs):
        profile = classify_trail(distance_km, 1000.0)
        assert trail_min_runs_per_week(profile) == expected_runs

    def test_min_mileage_floor_is_15_for_short_trail(self):
        # 0.35 * 15 = 5.25, but the floor is 15.
        profile = classify_trail(15.0, 100.0)
        assert trail_min_weekly_mileage(profile) == 15.0

    def test_min_mileage_scales_with_distance(self):
        # 0.35 * 100 = 35
        profile = classify_trail(100.0, 1000.0)
        assert trail_min_weekly_mileage(profile) == 35.0

    def test_min_mileage_mountainous_uplift(self):
        # 50 km flat: 0.35 * 50 = 17.5
        flat = classify_trail(50.0, 0.0)
        assert trail_min_weekly_mileage(flat) == 17.5
        # 50 km mountainous: same base × 1.20 = 21.0
        mountain = classify_trail(50.0, 3000.0)  # 60 m/km → mountainous
        assert mountain.elevation_class == "mountainous"
        assert trail_min_weekly_mileage(mountain) == 21.0

    def test_max_mileage_continuous_in_distance_and_elevation(self):
        # 30 km / 1000 m → 35 + 25.5 + 3.5 = 64 km/wk (was hardcoded 60 in old config)
        profile = classify_trail(30.0, 1000.0)
        assert trail_max_weekly_mileage(profile) == pytest.approx(64.0, abs=0.5)

    def test_max_mileage_saturates_at_140(self):
        # 163 km / 10000 m → far above 140, must clamp
        profile = classify_trail(163.0, 10000.0)
        assert trail_max_weekly_mileage(profile) == 140.0

    def test_max_mileage_floor_50(self):
        # 8 km / 0 m → 35 + 6.8 = 41.8, floor is 50
        profile = classify_trail(8.0, 0.0)
        assert trail_max_weekly_mileage(profile) == 50.0


class TestTrailProfileDirectConstruction:
    """The dataclass itself accepts pre-classified inputs (used in fixtures)."""

    def test_direct_construction(self):
        profile = TrailProfile(
            distance_km=42.2,
            elevation_gain_m=1000.0,
            bracket="ultra",
            elevation_class="rolling",
        )
        assert profile.distance_km == 42.2
        assert profile.bracket == "ultra"
        assert profile.is_ultra is True
        assert profile.category_key == "Trail_ultra_rolling"
