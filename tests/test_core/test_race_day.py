"""Race day: every plan ends on the event it was built for.

Plans used to stop one session short of the race — the final week ended on a
taper long run and the runner was left to infer where the race went. These
tests pin the shape of race week and the properties of the race workout that
the rest of the pipeline relies on (chiefly: nothing may rescale it).
"""

import pytest

from app.contexts.plan.generators.plan_generator import (
    RACE_DAY_NUMBER,
    TrainingPlanGenerator,
)
from app.contexts.plan.generators.workout_scaler import is_prescriptive, set_distance
from app.core.training.trail_profile import classify_trail
from app.core.training.training_constants import training_km
from app.core.training.workout_steps import compute_distance_from_steps_checked

ROAD = [(5.0, 8, 20, 3), (10.0, 12, 30, 4), (21.1, 12, 35, 4), (42.2, 16, 50, 5)]


@pytest.fixture(scope="module")
def road_plans():
    gen = TrainingPlanGenerator()
    return {
        km: gen.generate_plan(float(base), km, weeks, runs, vdot=45.0)
        for km, weeks, base, runs in ROAD
    }


def _race(plan):
    races = [w for w in plan[-1]["daily_workouts"] if w["type"] == "race"]
    assert len(races) == 1, f"expected exactly one race day, got {len(races)}"
    return races[0]


@pytest.mark.parametrize("km", [c[0] for c in ROAD])
class TestRaceDayIsPresentAndCorrect:
    def test_final_week_ends_on_the_race(self, road_plans, km):
        final = road_plans[km][-1]
        assert final["daily_workouts"][-1]["type"] == "race"
        assert final.get("is_race_week") is True

    def test_race_is_the_goal_distance(self, road_plans, km):
        assert _race(road_plans[km])["distance"] == pytest.approx(km, abs=0.05)

    def test_race_falls_on_the_last_day_of_the_week(self, road_plans, km):
        assert _race(road_plans[km])["day"] == RACE_DAY_NUMBER

    def test_race_steps_price_to_the_race_distance(self, road_plans, km):
        """A race day must report the event distance exactly.

        Every other card's distance is an estimate; this one is not, so the
        steps may not smuggle a warm-up into the total.
        """
        race = _race(road_plans[km])
        step_km, priced = compute_distance_from_steps_checked(race["steps"])
        assert priced
        assert step_km == pytest.approx(km, abs=0.05)

    def test_race_appears_only_in_the_final_week(self, road_plans, km):
        for week in road_plans[km][:-1]:
            assert not [w for w in week["daily_workouts"] if w["type"] == "race"]

    def test_no_long_run_survives_in_race_week(self, road_plans, km):
        """A near-race-distance long run days before the race is a second race."""
        final = road_plans[km][-1]
        assert not [
            w
            for w in final["daily_workouts"]
            if w["type"] == "long" and (w.get("distance") or 0) > 0
        ]

    def test_race_week_is_a_drawdown_but_not_a_shutdown(self, road_plans, km):
        plan = road_plans[km]
        peak = max(training_km(w) for w in plan[:-1] if not w.get("is_recovery"))
        pre_race = training_km(plan[-1])
        assert 0 < pre_race <= peak * 0.45

    def test_race_week_still_has_seven_days(self, road_plans, km):
        assert len(road_plans[km][-1]["daily_workouts"]) == 7

    def test_race_carries_pace_guidance(self, road_plans, km):
        """The goal pace must reach the card — for half/marathon this only
        works because the generator passes the target distance into
        ``get_pace_zones``, which is what creates the ``race`` zone."""
        race = _race(road_plans[km])
        assert all(s.get("pace_str") for s in race["steps"])


class TestNothingMayRescaleTheRace:
    def test_race_is_prescriptive(self):
        assert is_prescriptive({"type": "race", "distance": 42.2})

    def test_set_distance_leaves_the_race_alone(self):
        """Guards the adaptation path: a week running over budget must not
        turn a marathon into a 38 km race."""
        race = {"type": "race", "distance": 42.2, "steps": []}
        set_distance(race, 38.0)
        assert race["distance"] == 42.2


class TestRaceWeekKeepsTheRunnersFrequency:
    @pytest.mark.parametrize("runs", [3, 4, 5])
    def test_run_count_is_unchanged_in_race_week(self, runs):
        """The race consumes a running slot rather than adding one."""
        plan = TrainingPlanGenerator().generate_plan(40.0, 21.1, 12, runs, vdot=45.0)
        counts = {
            len(
                [
                    w
                    for w in wk["daily_workouts"]
                    if w["type"] not in ("rest", "recovery")
                ]
            )
            for wk in plan
        }
        assert counts == {runs}


class TestTrailRaceDay:
    @pytest.mark.parametrize("km,elev", [(50.0, 2000), (80.0, 3500)])
    def test_trail_plans_end_on_their_race(self, km, elev):
        plan = TrainingPlanGenerator().generate_plan(
            50.0, km, 16, 4, vdot=45.0, trail_profile=classify_trail(km, float(elev))
        )
        race = _race(plan)
        assert race["distance"] == pytest.approx(km, abs=0.05)
        # Trail races are paced by effort, not a goal pace.
        assert all(s["pace_zone"] == "E" for s in race["steps"])


class TestRaceDaySurvivesPlanAdjustments:
    """The plan-adjustment surface must not be able to delete the goal race.

    Race day is installed once, during generation. Nothing re-installs it, so
    a stray type change or week-level distance nudge on the final day would
    remove the event the whole plan was built to reach — permanently.
    """

    @staticmethod
    def _race_week_plan():
        plan = TrainingPlanGenerator().generate_plan(35.0, 21.1, 12, 4, vdot=45.0)
        return plan, plan[-1]["week"]

    def test_type_change_cannot_convert_race_day(self):
        from app.contexts.plan.plan_adjustments import swap_workout

        plan, week_no = self._race_week_plan()
        swap_workout(plan, week_no, f"{RACE_DAY_NUMBER},easy")
        assert _race(plan)["distance"] == pytest.approx(21.1, abs=0.05)

    def test_week_distance_nudge_does_not_move_the_race(self):
        from app.contexts.plan.plan_adjustments import adjust_distance

        plan, week_no = self._race_week_plan()
        adjust_distance(plan, week_no, -10.0)
        assert _race(plan)["distance"] == pytest.approx(21.1, abs=0.05)

    def test_race_day_cannot_be_dragged_to_another_day(self):
        from app.contexts.plan.plan_adjustments import swap_days

        plan, week_no = self._race_week_plan()
        swap_days(plan, week_no, RACE_DAY_NUMBER, 1)
        assert _race(plan)["day"] == RACE_DAY_NUMBER

    def test_race_is_not_a_swap_target(self):
        """No day can be turned *into* a race — "race" is not a buildable type."""
        from app.contexts.plan.plan_adjustments import _KNOWN_TYPES

        assert "race" not in _KNOWN_TYPES
