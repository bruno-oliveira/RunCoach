"""Tests for the trail intensive-weekend workout step builders."""

from app.core.training.workout_steps import (
    _compute_distance_from_steps,
    build_hike_run_steps,
    build_ladder_steps,
    build_pyramid_steps,
)

_VALID_KINDS = {"warmup", "run", "recovery", "cooldown", "strides", "walk", "rest"}


class TestPyramidSteps:
    def test_default_pyramid_structure(self):
        steps = build_pyramid_steps(9.0)
        kinds = [s["kind"] for s in steps]
        assert kinds[0] == "warmup"
        assert kinds[-1] == "cooldown"
        runs = [s for s in steps if s["kind"] == "run"]
        assert [s["distance_m"] for s in runs] == [400, 800, 1200, 800, 400]
        # Equal-distance recovery between reps, but not after the final rep.
        recoveries = [s for s in steps if s["kind"] == "recovery"]
        assert len(recoveries) == len(runs) - 1
        for s in steps:
            assert s["kind"] in _VALID_KINDS

    def test_run_reps_at_trail_pace(self):
        steps = build_pyramid_steps(9.0, pace_zone="T")
        assert all(s["pace_zone"] == "T" for s in steps if s["kind"] == "run")

    def test_custom_pattern(self):
        steps = build_pyramid_steps(9.0, pattern=[200, 400, 200])
        runs = [s for s in steps if s["kind"] == "run"]
        assert [s["distance_m"] for s in runs] == [200, 400, 200]

    def test_empty_for_zero_distance(self):
        assert build_pyramid_steps(0) == []


class TestLadderSteps:
    def test_default_ladder_is_ascending(self):
        steps = build_ladder_steps(9.0)
        runs = [s for s in steps if s["kind"] == "run"]
        assert [s["distance_m"] for s in runs] == [400, 800, 1200, 1600]
        recoveries = [s for s in steps if s["kind"] == "recovery"]
        assert len(recoveries) == len(runs) - 1

    def test_empty_for_zero_distance(self):
        assert build_ladder_steps(0) == []


class TestHikeRunSteps:
    def test_distance_is_deterministic_and_close(self):
        steps = build_hike_run_steps(30.0)
        total = _compute_distance_from_steps(steps)
        # Whole-set rounding can drop up to one set's worth of distance.
        assert abs(total - 30.0) <= 2.0

    def test_has_run_and_walk_blocks_with_explicit_distance(self):
        steps = build_hike_run_steps(30.0)
        kinds = {s["kind"] for s in steps}
        assert "run" in kinds
        assert "walk" in kinds
        for s in steps:
            assert s["kind"] in _VALID_KINDS
            # Explicit distance_m keeps the recomputed total pace-independent.
            assert s.get("distance_m"), "hike-run blocks must carry distance_m"

    def test_empty_for_zero_distance(self):
        assert build_hike_run_steps(0) == []
