"""Pace and heart-rate targets must describe the runner, not the goal.

Every case here is one runner — 28:00 for 5 km today, chasing 25:00 — or the
trail equivalent, because the failures these pin were all the same mistake in
different places: a number derived from the *goal* presented as a target for
the runner as they are now.
"""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.contexts.plan.adaptation.reconcile import pace_zones_for
from app.contexts.plan.generators.performance_plan_generator import (
    PerformancePlanGenerator,
)
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.plan_service import PlanService
from app.contexts.plan.plan_type_registry import _current_week_pace_zones
from app.core.time_utils import local_today, utcnow_naive
from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.core.training.physiology.zone_calculator import calculate_zones
from app.core.training.workouts.key_workout_library.builders import (
    _KEY_WORKOUT_STEP_BUILDERS,
)
from app.models import RunLog, User
from app.schemas.plan_request import PlanRequest

CURRENT_PACE = 28 / 5
GOAL_PACE = 25 / 5
CURRENT_VDOT = VDOTCalculator.calculate_vdot(5.0, 28 * 60)
GOAL_VDOT = VDOTCalculator.calculate_vdot(5.0, 25 * 60)


def _work_steps(workout: dict) -> list[dict]:
    return [s for s in workout.get("steps", []) if s["kind"] == "run"]


@pytest.fixture(scope="module")
def time_goal_plan() -> dict:
    return PerformancePlanGenerator().generate_plan(
        5.0, CURRENT_PACE, GOAL_PACE, 8, 20, runs_per_week=4, max_heart_rate=185
    )


class TestGoalPaceSession:
    def test_5k_goal_pace_reps_are_built_at_5k_pace(self):
        zones = VDOTCalculator.get_pace_zones(CURRENT_VDOT, 5.0)
        steps = _KEY_WORKOUT_STEP_BUILDERS["5k_race_pace_3km"](5.0, zones)
        (work,) = _work_steps({"steps": steps})
        assert work["pace_zone"] == "5K"
        assert work["pace_str"] == zones["5K"]["pace_str"]
        assert work["effort"] == "hard"

    def test_time_goal_plan_rehearses_the_goal_pace_not_threshold(self, time_goal_plan):
        sessions = [
            w
            for week in time_goal_plan["weekly_plans"]
            for w in week["daily_workouts"]
            if w.get("key_workout_id") == "5k_race_pace_3km"
        ]
        assert sessions, "expected the goal-pace session in an 8-week 5K block"
        for session in sessions:
            assert [s["pace_str"] for s in _work_steps(session)] == ["5:00/km"]


class TestEasyRunsSitInTheirHeartRateZone:
    def test_easy_and_long_runs_carry_the_easy_band(self, time_goal_plan):
        week_one = time_goal_plan["weekly_plans"][0]
        band = VDOTCalculator.get_pace_zones(CURRENT_VDOT)["E"]["pace_str"]
        aerobic = [
            w for w in week_one["daily_workouts"] if w["type"] in ("easy", "long")
        ]
        assert aerobic
        for workout in aerobic:
            assert workout["zone"] == "zone_2"
            assert [s["pace_str"] for s in _work_steps(workout)] == [band]


class TestRaceBandEffort:
    def test_goal_pace_beyond_vo2max_pace_keeps_its_near_max_label(self):
        zones = calculate_zones(
            vdot=CURRENT_VDOT, goal_pace=GOAL_PACE, max_hr=185, race_distance_km=5.0
        )
        assert zones["zone_5_race"]["hr_range"] == "95-100%"
        assert zones["zone_5_race"]["pace"] < zones["zone_4_vo2max"]["pace"]

    def test_goal_pace_within_reach_borrows_the_vo2max_band(self):
        zones = calculate_zones(
            vdot=GOAL_VDOT, goal_pace=GOAL_PACE, max_hr=185, race_distance_km=5.0
        )
        race = zones["zone_5_race"]
        assert race["hr_range"] == zones["zone_4_vo2max"]["hr_range"]
        assert race["hr_bpm_range"] == zones["zone_4_vo2max"]["hr_bpm_range"]


class TestPlanPagePacePanel:
    def _plan(self, weeks_in: int) -> SimpleNamespace:
        return SimpleNamespace(
            target_distance_km=5.0,
            goal_pace=GOAL_PACE,
            current_pace=CURRENT_PACE,
            weeks_duration=8,
            start_date=local_today() - timedelta(weeks=weeks_in),
        )

    def test_first_week_shows_the_paces_of_current_fitness(self):
        zones = _current_week_pace_zones(self._plan(weeks_in=0))
        current = VDOTCalculator.get_pace_zones(CURRENT_VDOT)
        assert zones["E"]["pace_str"] == current["E"]["pace_str"]
        assert zones["T"]["pace_str"] == current["T"]["pace_str"]

    def test_final_week_shows_the_paces_of_goal_fitness(self):
        zones = _current_week_pace_zones(self._plan(weeks_in=7))
        goal = VDOTCalculator.get_pace_zones(GOAL_VDOT)
        assert zones["T"]["pace_str"] == goal["T"]["pace_str"]

    def test_a_finished_plan_stays_on_its_final_week(self):
        late = _current_week_pace_zones(self._plan(weeks_in=20))
        final = _current_week_pace_zones(self._plan(weeks_in=7))
        assert late["T"] == final["T"]

    def test_no_goal_pace_yields_no_zones(self):
        plan = self._plan(weeks_in=0)
        plan.goal_pace = None
        assert _current_week_pace_zones(plan) is None


class TestDistancePlanWithAGoalTime:
    def test_training_paces_follow_the_recent_race_not_the_goal(self):
        request = PlanRequest(
            current_km=20,
            target_distance=5.0,
            weeks=8,
            max_runs_per_week=4,
            recent_race_distance_km=5.0,
            recent_race_time="28:00",
            goal_time="25:00",
        )
        assert request.vdot == CURRENT_VDOT
        assert request.goal_vdot == GOAL_VDOT
        assert request.pacing_vdot == CURRENT_VDOT

    def test_the_goal_is_the_anchor_only_when_it_is_the_sole_one(self):
        request = PlanRequest(
            current_km=20,
            target_distance=5.0,
            weeks=8,
            max_runs_per_week=4,
            goal_time="25:00",
        )
        assert request.pacing_vdot == GOAL_VDOT

    def test_logged_fitness_outranks_the_goal(self):
        request = PlanRequest(
            current_km=20,
            target_distance=5.0,
            weeks=8,
            max_runs_per_week=4,
            goal_time="25:00",
        ).model_copy(update={"logged_vdot": 38.5})
        assert request.pacing_vdot == 38.5

    def test_a_recent_race_outranks_logged_fitness(self):
        request = PlanRequest(
            current_km=20,
            target_distance=5.0,
            weeks=8,
            max_runs_per_week=4,
            recent_race_distance_km=5.0,
            recent_race_time="28:00",
            goal_time="25:00",
        ).model_copy(update={"logged_vdot": 38.5})
        assert request.pacing_vdot == CURRENT_VDOT

    def test_race_day_runs_at_the_goal_and_easy_days_at_current_fitness(self):
        plan = TrainingPlanGenerator().generate_plan(
            20, 5.0, 8, 4, vdot=CURRENT_VDOT, goal_pace_min_km=GOAL_PACE
        )
        current = VDOTCalculator.get_pace_zones(CURRENT_VDOT)
        workouts = [w for week in plan for w in week["daily_workouts"]]
        race = next(w for w in workouts if w["type"] == "race")
        assert {s["pace_str"] for s in _work_steps(race)} == {"5:00/km"}
        easy = next(w for w in workouts if w["type"] == "easy")
        assert _work_steps(easy)[0]["pace_str"] == current["E"]["pace_str"]


class TestGoalOnlyPlanIsPacedFromLoggedRuns:
    """A goal time with no recent race: the runner's history sets the paces."""

    LOGGED_VDOT = 36.0

    def _request(self, **overrides) -> PlanRequest:
        fields = {
            "current_km": 20,
            "target_distance": 5.0,
            "weeks": 8,
            "max_runs_per_week": 4,
            "goal_time": "25:00",
        }
        return PlanRequest(**{**fields, **overrides})

    def _runner(self, db, *, logged_runs: int) -> User:
        user = User(id=str(uuid.uuid4()), email=f"{uuid.uuid4().hex[:8]}@test.com")
        db.add(user)
        for days_ago in range(1, logged_runs + 1):
            db.add(
                RunLog(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    date=utcnow_naive() - timedelta(days=days_ago),
                    distance_km=8.0,
                    duration_minutes=46.0,
                    avg_pace_min_km=46.0 / 8.0,
                    vdot=self.LOGGED_VDOT,
                )
            )
        db.flush()
        return user

    def _create(self, db, user, request, plan_generator, nutrition_engine):
        plan, plan_data = PlanService().create_plan(
            request, user, db, plan_generator, nutrition_engine
        )
        return plan, [w for week in plan_data for w in week["daily_workouts"]]

    def test_training_paces_come_from_the_logged_runs(
        self, test_db, plan_generator, nutrition_engine_seeded
    ):
        user = self._runner(test_db, logged_runs=6)
        plan, workouts = self._create(
            test_db, user, self._request(), plan_generator, nutrition_engine_seeded
        )
        assert plan.vdot == self.LOGGED_VDOT
        logged = VDOTCalculator.get_pace_zones(self.LOGGED_VDOT)
        easy = next(w for w in workouts if w["type"] == "easy")
        assert _work_steps(easy)[0]["pace_str"] == logged["E"]["pace_str"]

    def test_race_day_still_runs_at_the_goal(
        self, test_db, plan_generator, nutrition_engine_seeded
    ):
        user = self._runner(test_db, logged_runs=6)
        plan, workouts = self._create(
            test_db, user, self._request(), plan_generator, nutrition_engine_seeded
        )
        race = next(w for w in workouts if w["type"] == "race")
        assert {s["pace_str"] for s in _work_steps(race)} == {"5:00/km"}
        assert plan.goal_time == "25:00"

    def test_a_runner_with_no_history_keeps_the_goal_as_the_anchor(
        self, test_db, plan_generator, nutrition_engine_seeded
    ):
        user = self._runner(test_db, logged_runs=0)
        plan, _ = self._create(
            test_db, user, self._request(), plan_generator, nutrition_engine_seeded
        )
        assert plan.vdot == GOAL_VDOT

    def test_a_recent_race_is_not_second_guessed_by_the_history(
        self, test_db, plan_generator, nutrition_engine_seeded
    ):
        user = self._runner(test_db, logged_runs=6)
        request = self._request(recent_race_distance_km=5.0, recent_race_time="28:00")
        plan, _ = self._create(
            test_db, user, request, plan_generator, nutrition_engine_seeded
        )
        assert plan.vdot == CURRENT_VDOT

    def test_no_goal_time_derives_no_paces_from_the_history(
        self, test_db, plan_generator, nutrition_engine_seeded
    ):
        user = self._runner(test_db, logged_runs=6)
        plan, _ = self._create(
            test_db,
            user,
            self._request(goal_time=None),
            plan_generator,
            nutrition_engine_seeded,
        )
        assert plan.vdot is None

    def test_resubmitting_the_same_goal_returns_the_plan_already_made(
        self, test_db, plan_generator, nutrition_engine_seeded
    ):
        user = self._runner(test_db, logged_runs=6)
        first, _ = self._create(
            test_db, user, self._request(), plan_generator, nutrition_engine_seeded
        )
        test_db.flush()
        service = PlanService()
        assert service.find_duplicate(self._request(), user.id, test_db) is first
        other_goal = self._request(goal_time="24:00")
        assert service.find_duplicate(other_goal, user.id, test_db) is None


class TestRebuiltWorkoutsUseThePlansOwnZones:
    """An adjusted week must be paced from the zones its neighbours were."""

    def _plan(self, **overrides) -> SimpleNamespace:
        fields = {
            "vdot": CURRENT_VDOT,
            "target_distance_km": 5.0,
            "goal_pace": GOAL_PACE,
            "is_trail": False,
            "is_backyard": False,
        }
        return SimpleNamespace(**{**fields, **overrides})

    def test_road_plan_keeps_its_goal_pace_and_current_training_paces(self):
        zones = pace_zones_for(self._plan())
        current = VDOTCalculator.get_pace_zones(CURRENT_VDOT)
        assert zones["5K"]["pace_str"] == "5:00/km"
        assert zones["T"] == current["T"]

    def test_longer_road_plan_carries_a_race_entry(self):
        zones = pace_zones_for(self._plan(target_distance_km=21.1, goal_pace=5.45))
        assert zones["race"]["pace_min_km"] == 5.45

    def test_no_goal_leaves_the_predicted_race_pace(self):
        zones = pace_zones_for(self._plan(goal_pace=None))
        assert zones == VDOTCalculator.get_pace_zones(CURRENT_VDOT, 5.0)

    def test_trail_plan_is_never_pinned_to_its_goal_pace(self):
        zones = pace_zones_for(
            self._plan(target_distance_km=30.0, goal_pace=8.0, is_trail=True)
        )
        assert zones == VDOTCalculator.get_pace_zones(CURRENT_VDOT, 30.0)

    def test_backyard_plan_derives_no_race_pace(self):
        zones = pace_zones_for(
            self._plan(target_distance_km=160.0, is_trail=True, is_backyard=True)
        )
        assert "race" not in zones

    def test_no_vdot_means_no_zones(self):
        assert pace_zones_for(self._plan(vdot=None)) is None


class TestTrailGoalTime:
    def _request(self, **overrides) -> PlanRequest:
        fields = {
            "current_km": 40,
            "target_distance": 30.0,
            "weeks": 12,
            "max_runs_per_week": 4,
            "is_trail": True,
            "target_elevation_gain_m": 1200,
            "goal_time": "4:00:00",
        }
        return PlanRequest(**{**fields, **overrides})

    def test_a_trail_finish_time_derives_no_fitness(self):
        request = self._request()
        assert request.goal_vdot is None
        assert request.pacing_vdot is None
        # The pace itself is kept: the race protocol plans around it.
        assert request.goal_pace_min_km == pytest.approx(8.0)

    def test_a_recent_road_race_still_paces_the_trail_plan(self):
        request = self._request(recent_race_distance_km=10.0, recent_race_time="55:00")
        assert request.pacing_vdot == request.vdot
        assert request.vdot == VDOTCalculator.calculate_vdot(10.0, 55 * 60)

    def test_a_trail_goal_pace_is_never_pinned_onto_flat_race_steps(self):
        from app.core.training.profiles.trail_profile import classify_trail

        vdot = VDOTCalculator.calculate_vdot(10.0, 55 * 60)
        plan = TrainingPlanGenerator().generate_plan(
            40,
            30.0,
            12,
            4,
            vdot=vdot,
            trail_profile=classify_trail(30.0, 1200),
            goal_pace_min_km=8.0,
        )
        paces = {
            step.get("pace_str")
            for week in plan
            for workout in week["daily_workouts"]
            for step in workout.get("steps", [])
        }
        assert "8:00/km" not in paces
