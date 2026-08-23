"""Schema tests for the backyard ultra PlanRequest fields.

A backyard goal enters as a loop count and leaves as a trail plan: the request
derives the ultra projection the engine periodises against, and the runner's
own numbers survive alongside it so nothing downstream has to guess.
"""

import pytest
from pydantic import ValidationError

from app.core.training.backyard_profile import BACKYARD_LOOP_KM, classify_backyard
from app.core.training.trail_profile import TRAIL_DISTANCE_MAX_KM
from app.exceptions import (
    InadequateBaseException,
    InsufficientTimeException,
    ZeroMileageUnsupportedException,
)
from app.schemas import PlanRequest


def _req(**overrides):
    kwargs = dict(
        current_km=70,
        target_distance=BACKYARD_LOOP_KM,
        weeks=20,
        max_runs_per_week=5,
        is_backyard=True,
        backyard_target_loops=24,
    )
    kwargs.update(overrides)
    return PlanRequest(**kwargs)


class TestProjection:
    def test_the_loop_count_derives_the_training_distance(self):
        req = _req()
        expected = classify_backyard(24).equivalent_distance_km
        assert req.target_distance == pytest.approx(expected)
        assert req.is_trail is True

    def test_a_supplied_target_distance_is_overwritten_by_the_projection(self):
        """The form's distance field is a sentinel; the loop count is the input."""
        req = _req(target_distance=42.2)
        assert req.target_distance != 42.2

    def test_loop_elevation_projects_into_the_race_elevation(self):
        flat = _req(backyard_loop_elevation_gain_m=0)
        hilly = _req(backyard_loop_elevation_gain_m=150)
        assert flat.target_elevation_gain_m == 0
        assert hilly.target_elevation_gain_m > 0
        assert hilly.resolved_training_terrain() != flat.resolved_training_terrain()

    def test_the_projection_is_clamped_but_the_loop_count_is_not(self):
        req = _req(
            backyard_target_loops=48, current_km=120, weeks=36, max_runs_per_week=6
        )
        assert req.target_distance == TRAIL_DISTANCE_MAX_KM
        assert req.backyard_target_loops == 48

    def test_backyard_profile_round_trips_the_runner_s_own_numbers(self):
        req = _req(backyard_loop_km=7.0, backyard_loop_elevation_gain_m=80)
        profile = req.backyard_profile()
        assert profile.target_loops == 24
        assert profile.loop_km == 7.0
        assert profile.loop_elevation_gain_m == 80

    def test_non_backyard_requests_have_no_profile(self):
        req = PlanRequest(current_km=40, target_distance=42.2, weeks=16)
        assert req.backyard_profile() is None
        assert req.is_backyard is False


class TestRequiredInputs:
    def test_a_backyard_without_a_loop_count_is_rejected(self):
        with pytest.raises(ValidationError, match="how many hourly loops"):
            PlanRequest(
                current_km=70,
                target_distance=BACKYARD_LOOP_KM,
                weeks=20,
                max_runs_per_week=5,
                is_backyard=True,
            )

    @pytest.mark.parametrize("loops", [0, 5, 49, 200])
    def test_loop_count_outside_the_supported_range_is_rejected(self, loops):
        with pytest.raises(ValidationError):
            _req(backyard_target_loops=loops)

    @pytest.mark.parametrize("loop_km", [1.0, 5.0, 8.5, 42.2])
    def test_a_loop_that_isn_t_a_backyard_loop_is_rejected(self, loop_km):
        with pytest.raises(ValidationError):
            _req(backyard_loop_km=loop_km)

    def test_an_implausible_loop_climb_is_rejected(self):
        with pytest.raises(ValidationError):
            _req(backyard_loop_elevation_gain_m=900)

    def test_the_standard_loop_is_the_default(self):
        assert _req().backyard_loop_km == BACKYARD_LOOP_KM


class TestTierAwareConstraints:
    def test_too_few_weeks_for_the_goal(self):
        with pytest.raises(InsufficientTimeException, match="24 loops"):
            _req(weeks=10)

    def test_too_many_weeks_for_the_goal(self):
        with pytest.raises(ValidationError, match="should not exceed"):
            _req(backyard_target_loops=8, weeks=30, current_km=40, max_runs_per_week=3)

    def test_a_modest_goal_accepts_a_short_block(self):
        assert _req(
            backyard_target_loops=8, weeks=10, current_km=40, max_runs_per_week=3
        )

    def test_runs_per_week_floor_is_enforced(self):
        with pytest.raises(ValidationError, match="runs per week"):
            _req(max_runs_per_week=3)

    def test_base_mileage_floor_is_enforced(self):
        with pytest.raises(InadequateBaseException, match="24-loop"):
            _req(current_km=30)

    def test_a_hilly_loop_raises_the_base_floor(self):
        """The same loop count on a climbing loop is a bigger ask."""
        km = 62.0
        assert _req(current_km=km, backyard_loop_elevation_gain_m=0)
        with pytest.raises(InadequateBaseException):
            _req(current_km=km, backyard_loop_elevation_gain_m=250)

    def test_starting_from_zero_is_refused_and_says_so_in_loops(self):
        with pytest.raises(ZeroMileageUnsupportedException, match="24-loop backyard"):
            _req(current_km=0)


class TestGoalTime:
    def test_a_goal_time_is_ignored_for_a_backyard(self):
        """The goal is a loop count; a finish time has no meaning in this format."""
        req = _req(goal_time="24:00:00")
        assert req.goal_vdot is None
        assert req.goal_pace_min_km is None

    def test_a_recent_race_still_paces_the_plan(self):
        req = _req(recent_race_distance_km=42.2, recent_race_time="3:30:00")
        assert req.vdot is not None and req.vdot > 0
