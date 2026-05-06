"""Schema tests for the new trail / ultra PlanRequest fields.

Covers the parameterized trail mode (is_trail + target_elevation_gain_m)
that replaces the legacy ``target_distance == 30.0`` + ``terrain`` toggle.
The legacy path is exercised via auto-migration in the model_validator.
"""

import pytest

from app.exceptions import (
    InadequateBaseException,
    InsufficientTimeException,
    ZeroMileageUnsupportedException,
)
from app.schemas import PlanRequest


class TestLegacyAutoMigration:
    """Pre-existing form posts (target=30.0 + optional terrain) keep working."""

    def test_30km_no_flags_promotes_to_trail_with_hilly_default(self):
        req = PlanRequest(
            current_km=25, target_distance=30.0, weeks=12, max_runs_per_week=4
        )
        assert req.is_trail is True
        assert req.target_elevation_gain_m == 1000.0

    def test_30km_terrain_flat_maps_to_low_elevation(self):
        req = PlanRequest(
            current_km=25,
            target_distance=30.0,
            weeks=12,
            max_runs_per_week=4,
            terrain="flat",
        )
        assert req.is_trail is True
        assert req.target_elevation_gain_m == 200.0

    def test_explicit_elevation_wins_over_terrain_default(self):
        req = PlanRequest(
            current_km=25,
            target_distance=30.0,
            weeks=12,
            max_runs_per_week=4,
            terrain="hilly",
            target_elevation_gain_m=500.0,
        )
        assert req.target_elevation_gain_m == 500.0


class TestNewTrailFormHappyPaths:
    """The user-facing 'Trail / Ultra (custom)' inputs."""

    @pytest.mark.parametrize(
        "distance,elev,weeks,runs",
        [
            (10.0, 0.0, 6, 3),       # short flat trail (10 km road = 10 km trail OK with is_trail)
            (15.0, 500.0, 8, 3),     # short rolling
            (30.0, 1000.0, 12, 4),   # standard hilly (legacy default)
            (50.0, 200.0, 16, 5),    # ultra flat
            (80.0, 4500.0, 24, 6),   # long_ultra mountainous
            (163.0, 6000.0, 32, 6),  # 100-mile race
        ],
    )
    def test_valid_trail_combos(self, distance, elev, weeks, runs):
        # Use a base mileage well above the bracket floor (which scales with
        # distance and bumps 20% for mountainous courses).
        req = PlanRequest(
            current_km=max(20.0, 0.55 * distance),
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
            is_trail=True,
            target_elevation_gain_m=elev,
        )
        assert req.is_trail is True
        assert req.target_distance == distance
        assert req.target_elevation_gain_m == elev


class TestNewTrailRejections:
    """Validation errors specific to the parameterized trail mode."""

    def test_distance_below_floor_rejected(self):
        with pytest.raises(ValueError, match="Trail/ultra distance must be"):
            PlanRequest(
                current_km=15,
                target_distance=7.0,  # < 8 km floor
                weeks=8,
                max_runs_per_week=4,
                is_trail=True,
                target_elevation_gain_m=200.0,
            )

    def test_distance_above_ceiling_rejected_by_field(self):
        # The Field(le=163.0) catches this before our model validator runs.
        with pytest.raises(Exception):
            PlanRequest(
                current_km=70,
                target_distance=200.0,
                weeks=32,
                max_runs_per_week=6,
                is_trail=True,
                target_elevation_gain_m=5000.0,
            )

    def test_missing_elevation_rejected(self):
        with pytest.raises(ValueError, match="elevation gain"):
            PlanRequest(
                current_km=40,
                target_distance=50.0,
                weeks=16,
                max_runs_per_week=5,
                is_trail=True,
            )

    def test_elevation_above_ceiling_rejected(self):
        with pytest.raises(Exception):
            PlanRequest(
                current_km=70,
                target_distance=80.0,
                weeks=24,
                max_runs_per_week=6,
                is_trail=True,
                target_elevation_gain_m=12000.0,
            )

    @pytest.mark.parametrize(
        # weeks must sit inside each bracket's window (short ≤ 18, standard
        # ≤ 22, ultra ≥ 12, long_ultra ≥ 16) so the rejection comes from the
        # runs-per-week validator and not the weeks one.
        "distance,runs,weeks,bracket",
        [
            (15.0, 2, 12, "short"),
            (30.0, 3, 12, "standard"),
            (50.0, 4, 16, "ultra"),
            (100.0, 5, 20, "long_ultra"),
        ],
    )
    def test_runs_per_week_below_bracket_floor_rejected(self, distance, runs, weeks, bracket):
        with pytest.raises(ValueError, match="needs at least"):
            PlanRequest(
                current_km=max(20.0, 0.55 * distance),
                target_distance=distance,
                weeks=weeks,
                max_runs_per_week=runs,
                is_trail=True,
                target_elevation_gain_m=1000.0,
            )

    @pytest.mark.parametrize(
        "distance,too_few_weeks,floor",
        [
            (50.0, 11, 12),     # ultra needs 12+ weeks
            (100.0, 15, 16),    # long_ultra needs 16+ weeks
        ],
    )
    def test_too_few_weeks_for_ultra_rejected(self, distance, too_few_weeks, floor):
        with pytest.raises(InsufficientTimeException):
            PlanRequest(
                current_km=max(15.0, 0.4 * distance),
                target_distance=distance,
                weeks=too_few_weeks,
                max_runs_per_week=6,
                is_trail=True,
                target_elevation_gain_m=2000.0,
            )

    def test_too_many_weeks_for_short_bracket_rejected(self):
        # short bracket caps at 18 weeks
        with pytest.raises(ValueError, match="should not exceed"):
            PlanRequest(
                current_km=20,
                target_distance=15.0,
                weeks=20,
                max_runs_per_week=4,
                is_trail=True,
                target_elevation_gain_m=500.0,
            )

    def test_below_min_mileage_for_ultra_rejected(self):
        # ultra distance 50 km needs base of max(15, 0.35*50) = 17.5 km/wk
        with pytest.raises(InadequateBaseException):
            PlanRequest(
                current_km=10,
                target_distance=50.0,
                weeks=16,
                max_runs_per_week=5,
                is_trail=True,
                target_elevation_gain_m=200.0,
            )

    def test_zero_mileage_rejected_for_trail(self):
        with pytest.raises(ZeroMileageUnsupportedException):
            PlanRequest(
                current_km=0,
                target_distance=50.0,
                weeks=16,
                max_runs_per_week=5,
                is_trail=True,
                target_elevation_gain_m=200.0,
            )


class TestRoadStillWorks:
    """The road plan path is unchanged by the trail-mode addition."""

    @pytest.mark.parametrize(
        "distance,weeks,runs,base",
        [
            (5.0, 8, 3, 10.0),
            (10.0, 10, 4, 20.0),
            (21.1, 12, 4, 30.0),
            (42.2, 18, 5, 50.0),
        ],
    )
    def test_road_distances_accept(self, distance, weeks, runs, base):
        req = PlanRequest(
            current_km=base,
            target_distance=distance,
            weeks=weeks,
            max_runs_per_week=runs,
        )
        assert req.is_trail is False
        assert req.target_elevation_gain_m is None

    def test_unknown_road_distance_rejected(self):
        with pytest.raises(ValueError, match="select a valid distance"):
            PlanRequest(
                current_km=20,
                target_distance=15.0,  # not in road preset, is_trail not set
                weeks=10,
                max_runs_per_week=4,
            )
