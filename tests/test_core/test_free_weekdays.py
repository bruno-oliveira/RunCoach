"""Tuesday and Friday carry no run, whichever generator built the plan.

Each generator used to own its day table, and they disagreed: a three-run week
was Mon/Wed/Sat on a road plan, Tue/Thu/Sat on a goal-time plan and Mon/Wed/Fri
on a beginner one. ``FREE_WEEKDAYS`` is the single rule they all read now, and
these tests pin it per generator so a new layout cannot quietly bring a
Tuesday back.
"""

import pytest

from app.contexts.plan.generators.beginner_plan_generator import BeginnerPlanGenerator
from app.contexts.plan.generators.performance_plan_generator import (
    PerformancePlanGenerator,
)
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.core.training.frequency import get_composer
from app.core.training.periodization.recovery_block import build_recovery_block
from app.core.training.periodization.week_scheduler import (
    schedule_from_composer,
    schedule_workout_types,
)
from app.core.training.profiles.backyard_profile import classify_backyard
from app.core.training.tuning import FREE_WEEKDAYS

TUESDAY, FRIDAY, SUNDAY = 2, 5, 7
_QUALITY = ("interval", "tempo", "hill")
# Run counts that fit in the five days left over.
_FITTING_RUNS = (2, 3, 4, 5)


def _run_days(week: dict) -> set[int]:
    """Weekdays (1 = Monday) of ``week`` that carry a run."""
    return {
        w["day"]
        for w in week["daily_workouts"]
        if w.get("type") != "rest" and (w.get("distance") or 0) > 0
    }


def _scheduled_run_days(types: list) -> set[int]:
    """Weekdays (1 = Monday) a scheduler output puts a run on."""
    return {i + 1 for i, t in enumerate(types) if t not in ("rest", "recovery")}


def _assert_free(weeks: list[dict]) -> None:
    for week in weeks:
        assert not _run_days(week) & FREE_WEEKDAYS, (week["week"], _run_days(week))


def test_the_free_weekdays_are_tuesday_and_friday():
    assert FREE_WEEKDAYS == {TUESDAY, FRIDAY}


class TestComposerSchedule:
    @pytest.mark.parametrize("runs", _FITTING_RUNS)
    @pytest.mark.parametrize("phase", ("base", "build", "peak", "taper"))
    @pytest.mark.parametrize(
        "quality", ({}, {"interval": 1}, {"interval": 1, "tempo": 1})
    )
    def test_no_run_on_a_free_weekday(self, runs, phase, quality):
        types = schedule_from_composer(get_composer(runs), phase, quality, False)
        assert not _scheduled_run_days(types) & FREE_WEEKDAYS, types

    def test_three_runs_are_monday_wednesday_saturday(self):
        types = schedule_from_composer(get_composer(3), "build", {"interval": 1}, False)
        assert _scheduled_run_days(types) == {1, 3, 6}, types

    def test_quality_days_do_not_move(self):
        # The tempo builder keys its variant on the day number, so a second
        # quality session that drifted off Thursday changed the session itself.
        types = schedule_from_composer(
            get_composer(5), "build", {"interval": 1, "tempo": 1}, False
        )
        assert [i for i, t in enumerate(types) if t in _QUALITY] == [0, 3], types

    def test_six_runs_give_up_friday_and_keep_tuesday(self):
        types = schedule_from_composer(get_composer(6), "build", {"interval": 1}, False)
        assert _scheduled_run_days(types) & FREE_WEEKDAYS == {FRIDAY}, types


class TestLegacySchedule:
    """The trail and backyard path, which predates the composers."""

    @staticmethod
    def _distribution(easy: int, tempo: int = 0) -> dict:
        return {
            "easy": easy,
            "long": 1,
            "interval": 0,
            "tempo": tempo,
            "hill": 0,
            "rest": 7,
        }

    @pytest.mark.parametrize("easy,tempo", [(1, 0), (2, 0), (2, 1), (3, 1), (4, 0)])
    def test_no_run_on_a_free_weekday(self, easy, tempo):
        types = schedule_workout_types(
            self._distribution(easy, tempo), "build", 5, False
        )
        assert not _scheduled_run_days(types) & FREE_WEEKDAYS, types

    def test_a_reserved_day_is_given_up_after_the_free_weekdays(self):
        # Backyard: Sunday belongs to the day after the simulation, so a
        # five-run week takes Friday before it parks a run there.
        types = schedule_workout_types(
            self._distribution(3, tempo=1),
            "build",
            5,
            False,
            reserved_days=frozenset({SUNDAY - 1}),
        )
        assert _scheduled_run_days(types) == {1, 3, 4, FRIDAY, 6}, types


class TestGeneratedPlans:
    @pytest.mark.parametrize("runs", _FITTING_RUNS)
    def test_road_plan(self, runs):
        plan = TrainingPlanGenerator().generate_plan(
            30, 10.0, 10, max_runs_per_week=runs
        )
        _assert_free(plan)

    @pytest.mark.parametrize("runs", (3, 4, 5))
    def test_trail_plan(self, runs):
        plan = TrainingPlanGenerator().generate_plan(
            40, 30.0, 16, max_runs_per_week=runs
        )
        _assert_free(plan)

    @pytest.mark.parametrize("runs", _FITTING_RUNS)
    def test_goal_time_plan(self, runs):
        plan = PerformancePlanGenerator().generate_plan(
            5.0, 5.6, 5.0, 10, 20, runs_per_week=runs
        )
        _assert_free(plan["weekly_plans"])

    def test_three_run_goal_time_plan_is_monday_wednesday_saturday(self):
        # The plan that prompted the rule: 5K, 28:00 to 25:00, 20 km a week.
        plan = PerformancePlanGenerator().generate_plan(
            5.0, 5.6, 5.0, 10, 20, runs_per_week=3
        )
        for week in plan["weekly_plans"][:-1]:
            assert _run_days(week) == {1, 3, 6}, week["week"]

    def test_six_run_goal_time_plan_gives_up_friday_and_keeps_tuesday(self):
        plan = PerformancePlanGenerator().generate_plan(
            5.0, 5.6, 5.0, 10, 40, runs_per_week=6
        )
        for week in plan["weekly_plans"]:
            assert TUESDAY not in _run_days(week), week["week"]

    @pytest.mark.parametrize("runs", (2, 3, 4))
    def test_beginner_plan(self, runs):
        _assert_free(BeginnerPlanGenerator().generate_plan(5.0, 10, runs))

    @pytest.mark.parametrize("runs", _FITTING_RUNS)
    def test_recovery_block(self, runs):
        block = build_recovery_block(
            race_km=42.2, race_name="marathon", peak_km=70, runs_per_week=runs
        )
        assert block
        _assert_free(block)

    def test_backyard_simulation_weeks_keep_their_easy_runs_in_proportion(self):
        # With Friday free the fifth run moved to Sunday, where an overnight
        # simulation overwrote it and its distance landed on the midweek easy
        # runs. Sunday is reserved for the simulation instead.
        plan = TrainingPlanGenerator().generate_plan(
            50, 80, 16, max_runs_per_week=5, backyard_profile=classify_backyard(12)
        )
        for week in plan[:-1]:
            workouts = week["daily_workouts"]
            long_km = max(w["distance"] for w in workouts if w["type"] == "long")
            easy_km = [w["distance"] for w in workouts if w["type"] == "easy"]
            assert max(easy_km) < long_km * 0.6, (week["week"], easy_km, long_km)
