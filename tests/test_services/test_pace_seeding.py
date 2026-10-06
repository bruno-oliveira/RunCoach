"""A plan that started with no fitness on record gains paces once runs arrive.

Such a plan is prescribed by effort — heart-rate zones and no pace. These pin
the three places that used to leave it that way for the whole block: the
recalibrator (which had no VDOT to move *from*), the change headline (which
only knew how to say "old → new"), and the plan page's pace-zone table (which
only time-goal plans were given).
"""

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.contexts.plan.adaptation import backtest as bt
from app.contexts.plan.adaptation.reconcile import pace_zones_for
from app.contexts.plan.adaptation.vdot_recalibrator import (
    DIRECTION_SET,
    recalibrate_zones_only,
)
from app.contexts.plan.plan_type_registry import (
    DistancePlanHandler,
    _single_vdot_training_zones,
)
from app.core.time_utils import utcnow_naive
from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.core.training.workouts.workout_steps import fill_step_paces
from app.infrastructure.integrations.post_sync_service import (
    _auto_adjust_headline,
    _race_headline,
    _recalibrate_headline,
    recalibrate_from_race,
)
from app.models import RunLog

LOGGED_VDOT = 41.0
WEEKS_IN = 3


@pytest.fixture
def effort_only_plan(test_db):
    """A half-marathon block three weeks in, built with no VDOT."""
    user, plan = bt._make_plan(
        test_db,
        current_km=35.0,
        target_distance=21.1,
        weeks=12,
        vdot=None,
        with_hr_zones=False,
    )
    plan.start_date = datetime.combine(
        datetime.now().date() - timedelta(weeks=WEEKS_IN), datetime.min.time()
    )
    test_db.commit()
    return user, plan


def _log_runs(db, user, *, count: int = 5) -> None:
    for days_ago in range(1, count + 1):
        db.add(
            RunLog(
                id=str(uuid.uuid4()),
                user_id=user.id,
                date=utcnow_naive() - timedelta(days=days_ago),
                distance_km=8.0,
                duration_minutes=44.0,
                avg_pace_min_km=44.0 / 8.0,
                vdot=LOGGED_VDOT,
            )
        )
    db.flush()


def _paces(plan, *, from_week: int, to_week: int) -> set:
    return {
        step["pace_str"]
        for week in plan.plan_data
        if from_week <= week["week"] <= to_week
        for workout in week["daily_workouts"]
        for step in workout.get("steps") or []
        if step.get("pace_zone") in ("E", "T", "I")
    }


class TestFillStepPaces:
    ZONES = VDOTCalculator.get_pace_zones(LOGGED_VDOT)

    def test_a_zone_labelled_step_gains_its_zones_pace(self):
        steps = [{"pace_zone": "E", "pace_str": None}]
        assert fill_step_paces(steps, self.ZONES) == 1
        assert steps[0]["pace_str"] == self.ZONES["E"]["pace_str"]

    def test_a_pace_that_is_already_there_is_left_alone(self):
        steps = [{"pace_zone": "E", "pace_str": "6:50/km"}]
        assert fill_step_paces(steps, self.ZONES) == 0
        assert steps[0]["pace_str"] == "6:50/km"

    def test_a_step_with_no_zone_or_an_unknown_one_stays_by_feel(self):
        steps = [{"pace_zone": None, "pace_str": None}, {"pace_zone": "WALK"}]
        assert fill_step_paces(steps, self.ZONES) == 0

    def test_no_zones_fills_nothing(self):
        assert fill_step_paces([{"pace_zone": "E", "pace_str": None}], None) == 0


class TestRecalibratorSeedsAnEffortOnlyPlan:
    def test_logged_runs_give_the_weeks_ahead_their_paces(
        self, test_db, effort_only_plan
    ):
        user, plan = effort_only_plan
        _log_runs(test_db, user)

        result = recalibrate_zones_only(plan, user.id, test_db)

        assert result is not None
        assert result["direction"] == DIRECTION_SET
        assert result["source"] == "logged_runs"
        assert (result["old_vdot"], result["new_vdot"]) == (None, LOGGED_VDOT)
        assert plan.vdot == LOGGED_VDOT
        ahead = _paces(plan, from_week=WEEKS_IN + 1, to_week=12)
        assert None not in ahead
        assert pace_zones_for(plan)["E"]["pace_str"] in ahead

    def test_weeks_already_run_keep_what_was_prescribed(
        self, test_db, effort_only_plan
    ):
        user, plan = effort_only_plan
        _log_runs(test_db, user)
        recalibrate_zones_only(plan, user.id, test_db)
        assert _paces(plan, from_week=1, to_week=WEEKS_IN) == {None}

    def test_seeded_paces_match_a_plan_generated_at_that_vdot(
        self, test_db, effort_only_plan
    ):
        user, plan = effort_only_plan
        _log_runs(test_db, user)
        recalibrate_zones_only(plan, user.id, test_db)
        built = bt.TrainingPlanGenerator().generate_plan(
            35.0, 21.1, 12, vdot=LOGGED_VDOT
        )
        generated = SimpleNamespace(plan_data=built)
        assert _paces(plan, from_week=WEEKS_IN + 1, to_week=12) == _paces(
            generated, from_week=WEEKS_IN + 1, to_week=12
        )

    def test_no_runs_on_record_leaves_the_plan_by_effort(
        self, test_db, effort_only_plan
    ):
        user, plan = effort_only_plan
        assert recalibrate_zones_only(plan, user.id, test_db) is None
        assert plan.vdot is None

    def test_a_seeded_plan_recalibrates_like_any_other_afterwards(
        self, test_db, effort_only_plan
    ):
        user, plan = effort_only_plan
        _log_runs(test_db, user)
        recalibrate_zones_only(plan, user.id, test_db)
        result = recalibrate_zones_only(plan, user.id, test_db, race_vdot=44.0)
        assert result is not None
        assert (result["old_vdot"], result["new_vdot"]) == (LOGGED_VDOT, 44.0)

    def test_a_tagged_race_seeds_the_plan_at_its_word(self, test_db, effort_only_plan):
        user, plan = effort_only_plan
        recalibrate_from_race(plan, user.id, test_db, race_vdot=47.0)
        assert plan.vdot == 47.0
        assert plan.last_change_plan["reason"].startswith("Race result in")
        assert "None" not in plan.last_change_plan["reason"]
        assert plan.adaptation_history[-1]["old_vdot"] is None

    def test_an_implausible_race_seeds_nothing(self, test_db, effort_only_plan):
        user, plan = effort_only_plan
        assert recalibrate_zones_only(plan, user.id, test_db, race_vdot=140.0) is None
        assert plan.vdot is None


class TestFirstPacesHeadline:
    SEED = {"old_vdot": None, "new_vdot": 41.0, "direction": DIRECTION_SET}

    @pytest.mark.parametrize(
        "headline",
        [
            _recalibrate_headline(SEED),
            _race_headline(SEED),
            _auto_adjust_headline(1.05, SEED),
            _auto_adjust_headline(0.9, SEED),
        ],
    )
    def test_it_names_the_new_vdot_and_never_a_missing_old_one(self, headline):
        assert "VDOT 41.0" in headline
        assert "None" not in headline
        assert "→" not in headline

    def test_a_move_still_reads_old_to_new(self):
        move = {"old_vdot": 40.0, "new_vdot": 42.0, "direction": "improved"}
        assert "VDOT 40.0 → 42.0" in _recalibrate_headline(move)
        assert "VDOT 40.0 → 42.0" in _auto_adjust_headline(1.05, move)


class TestDistancePlanPaceTable:
    def _plan(self, **overrides) -> SimpleNamespace:
        fields = {
            "vdot": LOGGED_VDOT,
            "target_distance_km": 10.0,
            "goal_pace": None,
            "is_trail": False,
            "is_backyard": False,
            "max_heart_rate": 190,
            "hr_zones_data": None,
        }
        return SimpleNamespace(**{**fields, **overrides})

    def test_the_table_is_built_from_the_zones_the_cards_use(self):
        plan = self._plan()
        zones = _single_vdot_training_zones(plan)
        assert zones is not None
        assert (
            zones["zone_2_aerobic"]["pace_str"]
            == (pace_zones_for(plan)["E"]["pace_str"])
        )
        assert all(z["pace_range_formatted"] for z in zones.values())
        assert zones["zone_2_aerobic"]["hr_bpm_range"].endswith("BPM")

    def test_no_vdot_means_no_table(self):
        assert _single_vdot_training_zones(self._plan(vdot=None)) is None

    def test_a_road_goal_pace_anchors_the_race_band(self):
        zones = _single_vdot_training_zones(self._plan(goal_pace=5.0))
        assert zones["zone_5_race"]["pace"] == 5.0

    def test_a_trail_goal_pace_never_becomes_a_flat_race_band(self):
        zones = _single_vdot_training_zones(self._plan(goal_pace=8.0, is_trail=True))
        assert zones["zone_5_race"]["pace"] != 8.0

    def test_the_distance_handler_puts_it_in_the_plan_view(self):
        extra = DistancePlanHandler().enrich_view_context(self._plan(), None, {}, [])
        assert "zone_3_tempo" in extra["training_zones"]

    def test_an_effort_only_plan_gets_no_table_in_the_plan_view(self):
        extra = DistancePlanHandler().enrich_view_context(
            self._plan(vdot=None), None, {}, []
        )
        assert "training_zones" not in extra
