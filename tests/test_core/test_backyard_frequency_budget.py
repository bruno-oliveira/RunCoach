"""The backyard frequency budget is a hard cap, and derived km fields are real.

Two audit findings live here:

* at low running frequency the backyard week could carry more running
  sessions than the runner asked for — the distribution handed out a quality
  slot on top of the long run regardless of the budget, and the second day
  after a simulation could spend a session the week never had. Every week of
  a backyard plan, week 1 included, must fit inside the requested frequency.
* a week dict's ``training_km`` is derived from its own day cards by one
  shared helper (``training_constants.workouts_training_km``) — never 0.0,
  never disagreeing with the sessions underneath it.
"""

import pytest

from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.periodization.training_constants import (
    training_km,
    workouts_training_km,
)
from app.core.training.profiles.backyard_profile import classify_backyard

# Backyard plans refuse fewer than the tier's minimum weeks; 8 is the
# first-timer floor and the smallest block these invariants can be observed
# on through the public generator.
_MIN_BACKYARD_WEEKS = 8


def _backyard_plan(runs: int):
    profile = classify_backyard(6)
    plan = TrainingPlanGenerator().generate_plan(
        current_km=30,
        target_distance=profile.equivalent_distance_km,
        weeks=_MIN_BACKYARD_WEEKS,
        max_runs_per_week=runs,
        vdot=45,
        backyard_profile=profile,
    )
    return plan


def _running_sessions(week):
    return [
        w
        for w in week["daily_workouts"]
        if w.get("type") not in ("rest", "recovery") and (w.get("distance") or 0) > 0
    ]


class TestBackyardFrequencyBudgetIsAHardCap:
    @pytest.mark.parametrize("runs", [1, 2, 3])
    def test_week_one_fits_the_frequency_budget(self, runs):
        """Week 1 is where a low budget used to be ignored; it holds here."""
        plan = _backyard_plan(runs)
        assert len(_running_sessions(plan[0])) <= runs

    @pytest.mark.parametrize("runs", [1, 2, 3])
    def test_every_week_fits_the_frequency_budget(self, runs):
        """No week, including the race week, exceeds the runner's budget."""
        plan = _backyard_plan(runs)
        for week in plan:
            assert len(_running_sessions(week)) <= runs, (
                f"week {week['week']} carried "
                f"{len(_running_sessions(week))} sessions at {runs} runs/week"
            )

    def test_at_one_run_per_week_week_one_is_exactly_one_session(self):
        plan = _backyard_plan(1)
        assert len(_running_sessions(plan[0])) == 1


class TestWeekTrainingKmIsDerived:
    def test_every_backyard_week_reports_its_training_km(self):
        plan = _backyard_plan(3)
        for week in plan:
            expected = workouts_training_km(week["daily_workouts"])
            assert week["training_km"] == pytest.approx(expected, abs=0.05)

    def test_training_km_is_positive_where_training_exists(self):
        plan = _backyard_plan(3)
        for week in plan[:-1]:
            assert week["training_km"] > 0.0, (
                f"week {week['week']} has {week['total_km']} km of sessions "
                "but reports 0.0 training km"
            )

    def test_race_week_training_km_excludes_the_race(self):
        """The final week's goal event is the race, not training load."""
        plan = _backyard_plan(3)
        race_week = plan[-1]
        assert race_week["training_km"] == pytest.approx(
            training_km(race_week), abs=0.05
        )
        assert race_week["training_km"] < race_week["total_km"]

    def test_road_plan_weeks_carry_the_same_derived_field(self):
        plan = TrainingPlanGenerator().generate_plan(40.0, 21.1, 12, 4, vdot=45.0)
        for week in plan:
            expected = workouts_training_km(week["daily_workouts"])
            assert week["training_km"] == pytest.approx(expected, abs=0.05)
            assert week["training_km"] > 0.0


class TestWorkoutsTrainingKmHelper:
    def test_sums_the_weeks_distances(self):
        workouts = [
            {"type": "easy", "distance": 8.0},
            {"type": "long", "distance": 20.0},
            {"type": "rest", "distance": 0},
        ]
        assert workouts_training_km(workouts) == 28.0

    def test_race_cards_are_excluded(self):
        workouts = [
            {"type": "easy", "distance": 3.0},
            {"type": "race", "distance": 42.2},
        ]
        assert workouts_training_km(workouts) == 3.0

    def test_missing_distances_count_as_zero(self):
        workouts = [{"type": "easy", "distance": None}, {"type": "rest"}]
        assert workouts_training_km(workouts) == 0.0
