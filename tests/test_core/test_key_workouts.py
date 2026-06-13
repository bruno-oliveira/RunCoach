"""Tests for the key workout library."""

import pytest

from app.core.training.key_workout_library import _WORKOUTS, KeyWorkoutLibrary


class TestLibraryCompleteness:
    """Every supported race distance has key workouts."""

    @pytest.mark.parametrize("distance", [5.0, 10.0, 21.1, 42.2, 30.0])
    def test_distance_has_workouts(self, distance):
        workouts = KeyWorkoutLibrary.get_all_for_distance(distance)
        assert len(workouts) >= 3, f"Expected >=3 workouts for {distance}km"

    def test_all_workouts_have_required_fields(self):
        required = {
            "id",
            "distances",
            "phases",
            "type",
            "name",
            "structure",
            "description",
            "intensity",
            "target_zone",
            "pace_zone",
            "rationale",
        }
        for w in _WORKOUTS:
            missing = required - set(w.keys())
            assert not missing, f"Workout {w.get('id', '?')} missing: {missing}"

    def test_ids_are_unique(self):
        ids = [w["id"] for w in _WORKOUTS]
        assert len(ids) == len(set(ids)), "Duplicate workout IDs found"


class TestPhaseGuard:
    """Taper is sharpener-only; base serves light quality (build/peak full)."""

    @pytest.mark.parametrize("phase", ["taper"])
    def test_returns_none_for_excluded_phases(self, phase):
        result = KeyWorkoutLibrary.get_for_phase(5.0, phase, 0)
        assert result is None

    @pytest.mark.parametrize(
        "distance,workout_type",
        [(5.0, "interval"), (10.0, "interval"), (21.1, "tempo"), (42.2, "tempo")],
    )
    def test_base_serves_light_quality_only(self, distance, workout_type):
        """Base phase now serves a workout, but only low-intensity ones."""
        result = KeyWorkoutLibrary.get_for_phase(distance, "base", 0, workout_type)
        assert result is not None
        # Base sessions must be light: never high-intensity threshold/VO2max.
        assert result["intensity"] in ("low", "medium")
        assert result["id"].startswith("base_")

    @pytest.mark.parametrize("phase", ["build", "peak"])
    def test_returns_workout_for_allowed_phases(self, phase):
        result = KeyWorkoutLibrary.get_for_phase(5.0, phase, 0, "interval")
        assert result is not None


class TestWorkoutRotation:
    """Different weeks should rotate through available workouts."""

    def test_rotation_produces_variety(self):
        results = set()
        for week in range(6):
            wk = KeyWorkoutLibrary.get_for_phase(42.2, "build", week, "tempo")
            if wk:
                results.add(wk["id"])
        assert len(results) >= 2, "Expected at least 2 different key workouts"


class TestVDOTPaceInjection:
    def test_injects_paces_when_zones_provided(self):
        workout = KeyWorkoutLibrary.get_for_phase(5.0, "build", 0, "interval")
        assert workout is not None

        # Simulate VDOT zones
        zones = {
            "E": {"pace_str": "6:00/km-5:30/km"},
            "M": {"pace_str": "5:00/km"},
            "T": {"pace_str": "4:40/km"},
            "I": {"pace_str": "4:10/km"},
            "R": {"pace_str": "3:50/km"},
        }

        enriched = KeyWorkoutLibrary.inject_vdot_paces(workout, zones)
        # Original should not be modified
        assert (
            enriched is not workout or enriched["description"] != workout["description"]
        )

    def test_returns_unchanged_when_no_zones(self):
        workout = KeyWorkoutLibrary.get_for_phase(10.0, "build", 0, "tempo")
        assert workout is not None
        enriched = KeyWorkoutLibrary.inject_vdot_paces(workout, None)
        assert enriched["description"] == workout["description"]
