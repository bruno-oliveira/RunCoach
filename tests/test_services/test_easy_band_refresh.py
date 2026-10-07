"""A plan's easy band is measured from the runner's runs, and follows them."""

from datetime import datetime, timedelta

from app.contexts.plan.adaptation.easy_band_refresh import refresh_easy_band
from app.contexts.plan.adaptation.reconcile import pace_zones_for
from app.contexts.plan.adaptation.vdot_recalibrator import recalibrate_zones_only
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.plan_service import _with_logged_fitness
from app.contexts.runner.fitness.easy_pace_service import (
    current_easy_pace,
    easy_hr_ceiling,
)
from app.core.time_utils import local_today
from app.models import RunLog, TrainingPlan, User
from app.schemas import PlanRequest

VDOT = 45.0
# Threshold 160 puts the top of the aerobic zone at 145 bpm.
THRESHOLD_HR = 160
EASY_HR = 138


def _runner(db, **anchors) -> User:
    user = User(email="easy@example.com", **anchors)
    db.add(user)
    db.flush()
    return user


def _log_easy_runs(db, user, pace, *, count=5, hr=EASY_HR, days_ago=2) -> None:
    for i in range(count):
        db.add(
            RunLog(
                user_id=user.id,
                date=datetime.now() - timedelta(days=days_ago + i),
                distance_km=8.0,
                duration_minutes=8.0 * pace,
                avg_pace_min_km=pace,
                avg_heart_rate=hr,
                elevation_gain_m=20,
            )
        )
    db.flush()


def _plan(db, user, *, easy_pace=None, vdot=VDOT) -> TrainingPlan:
    plan_data = TrainingPlanGenerator().generate_plan(
        40, 21.1, 12, 4, vdot=vdot, easy_pace_min_km=easy_pace
    )
    monday = local_today() - timedelta(days=local_today().weekday())
    plan = TrainingPlan(
        user_id=user.id,
        current_weekly_km=40,
        target_distance="21.1",
        weeks_duration=12,
        max_runs_per_week=4,
        plan_data=plan_data,
        vdot=vdot,
        easy_pace_min_km=easy_pace,
        # Two weeks in, so there are weeks both behind and ahead.
        start_date=datetime.combine(monday - timedelta(weeks=2), datetime.min.time()),
    )
    db.add(plan)
    db.flush()
    return plan


def _easy_zone_paces(plan, *, jogs: bool, from_week=1, to_week=99) -> set:
    return {
        step["pace_str"]
        for week in plan.plan_data
        if from_week <= week["week"] <= to_week
        for workout in week["daily_workouts"]
        for step in workout.get("steps") or []
        if step["pace_zone"] == "E" and (step["kind"] == "recovery") is jogs
    }


def _easy_paces(plan, **weeks) -> set:
    """Paces of the easy-zone steps that are runs, warm-ups and cool-downs."""
    return _easy_zone_paces(plan, jogs=False, **weeks)


def _jog_paces(plan, **weeks) -> set:
    """Paces of the jogs between reps, which sit below the easy band."""
    return _easy_zone_paces(plan, jogs=True, **weeks)


def _other_paces(plan) -> list:
    return [
        (week["week"], workout["day"], step["pace_zone"], step["pace_str"])
        for week in plan.plan_data
        for workout in week["daily_workouts"]
        for step in workout.get("steps") or []
        if step["pace_zone"] != "E"
    ]


class TestMeasuringTheEasyPace:
    def test_is_the_median_of_runs_under_the_aerobic_ceiling(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        _log_easy_runs(test_db, user, 6.0)
        _log_easy_runs(test_db, user, 5.0, hr=170)  # hard days do not count
        assert easy_hr_ceiling(user, test_db) == 145
        assert current_easy_pace(user.id, test_db) == 6.0

    def test_old_runs_no_longer_speak_for_today(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        _log_easy_runs(test_db, user, 6.0, days_ago=60)
        assert current_easy_pace(user.id, test_db) is None

    def test_zones_from_a_formula_cannot_say_which_runs_were_easy(self, test_db):
        """No anchor from the runner: the ceiling would be an age guess."""
        user = _runner(test_db, age=40)
        _log_easy_runs(test_db, user, 6.0, hr=120)
        assert easy_hr_ceiling(user, test_db) is None
        assert current_easy_pace(user.id, test_db) is None

    def test_an_unknown_runner_has_no_easy_pace(self, test_db):
        assert current_easy_pace(None, test_db) is None
        assert current_easy_pace("nobody", test_db) is None


class TestNewPlan:
    def test_a_stated_race_does_not_outrank_the_measured_easy_pace(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        _log_easy_runs(test_db, user, 6.0)
        request = PlanRequest(
            current_km=40,
            target_distance=21.1,
            weeks=12,
            recent_race_distance_km=10,
            recent_race_time="45:00",
        )
        resolved = _with_logged_fitness(request, user, test_db)
        assert resolved.vdot == request.vdot
        assert resolved.logged_vdot is None
        assert resolved.logged_easy_pace == 6.0

    def test_no_history_leaves_the_request_alone(self, test_db):
        user = _runner(test_db)
        request = PlanRequest(current_km=40, target_distance=21.1, weeks=12)
        assert _with_logged_fitness(request, user, test_db) is request

    def test_rebuilt_days_use_the_band_the_plan_was_written_from(self, test_db):
        user = _runner(test_db)
        plan = _plan(test_db, user, easy_pace=6.0)
        assert _easy_paces(plan) == {pace_zones_for(plan)["E"]["pace_str"]}
        assert pace_zones_for(plan)["E"]["pace_str"] == "6:15/km–5:45/km"


class TestFollowingTheRunner:
    def test_future_weeks_move_to_the_new_pace_and_past_weeks_stay(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        plan = _plan(test_db, user, easy_pace=6.0)
        quality_before = _other_paces(plan)
        _log_easy_runs(test_db, user, 5.8)  # 12 s/km quicker at the same HR

        moved = refresh_easy_band(plan, user.id, test_db)

        assert moved["old_band"] == "6:15/km–5:45/km"
        assert moved["new_band"] == "6:03/km–5:33/km"
        assert plan.easy_pace_min_km == 5.8
        assert _easy_paces(plan, to_week=2) == {"6:15/km–5:45/km"}
        assert _easy_paces(plan, from_week=3) == {"6:03/km–5:33/km"}
        assert _jog_paces(plan, from_week=3) == {"6:33/km–6:03/km"}
        assert _other_paces(plan) == quality_before

    def test_jogs_stored_on_the_easy_band_move_to_the_recovery_range(self, test_db):
        """Plans written before jogs had their own pace carry the easy band."""
        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        plan = _plan(test_db, user, easy_pace=6.0)
        for week in plan.plan_data:
            for workout in week["daily_workouts"]:
                for step in workout.get("steps") or []:
                    if step["kind"] == "recovery" and step["pace_zone"] == "E":
                        step["pace_str"] = "6:15/km–5:45/km"
        _log_easy_runs(test_db, user, 5.8)

        refresh_easy_band(plan, user.id, test_db)

        assert _jog_paces(plan, from_week=3) == {"6:33/km–6:03/km"}

    def test_the_prose_is_re_paced_with_the_steps(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        plan = _plan(test_db, user, easy_pace=6.0)
        _log_easy_runs(test_db, user, 5.8)

        refresh_easy_band(plan, user.id, test_db)

        future_text = " ".join(
            str(workout.get(field) or "")
            for week in plan.plan_data
            if week["week"] >= 3
            for workout in week["daily_workouts"]
            for field in ("description", "coaching_rationale")
        )
        assert "6:03/km–5:33/km" in future_text
        assert "6:15/km–5:45/km" not in future_text

    def test_a_vdot_band_gives_way_to_a_first_measurement(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        plan = _plan(test_db, user)
        _log_easy_runs(test_db, user, 6.0)

        assert refresh_easy_band(plan, user.id, test_db) is not None
        assert plan.easy_pace_min_km == 6.0
        assert _easy_paces(plan, from_week=3) == {"6:15/km–5:45/km"}

    def test_a_few_seconds_does_not_re_pace_the_plan(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        plan = _plan(test_db, user, easy_pace=6.0)
        revision = plan.adaptation_revision
        _log_easy_runs(test_db, user, 6.0 - 3 / 60)

        assert refresh_easy_band(plan, user.id, test_db) is None
        assert plan.easy_pace_min_km == 6.0
        assert plan.adaptation_revision == revision

    def test_nothing_measured_keeps_the_band_the_plan_has(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        plan = _plan(test_db, user, easy_pace=6.0)

        assert refresh_easy_band(plan, user.id, test_db) is None
        assert plan.easy_pace_min_km == 6.0

    def test_a_pace_that_reaches_threshold_is_not_applied(self, test_db):
        """VDOT 30 puts threshold slower than this runner jogs: no band fits."""
        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        plan = _plan(test_db, user, vdot=30.0)
        before = _easy_paces(plan)
        _log_easy_runs(test_db, user, 6.0)

        assert refresh_easy_band(plan, user.id, test_db) is None
        assert plan.easy_pace_min_km is None
        assert _easy_paces(plan) == before

    def test_a_plan_with_no_paces_is_left_for_the_seed(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        plan = _plan(test_db, user, vdot=None)
        _log_easy_runs(test_db, user, 6.0)
        assert refresh_easy_band(plan, user.id, test_db) is None


class TestFitnessChangeKeepsTheBand:
    def test_a_race_moves_quality_paces_and_leaves_the_easy_band(self, test_db):
        user = _runner(test_db)
        plan = _plan(test_db, user, easy_pace=6.0)
        quality_before = _other_paces(plan)

        result = recalibrate_zones_only(plan, user.id, test_db, race_vdot=48.0)

        assert result["new_vdot"] == 48.0
        assert _easy_paces(plan) == {"6:15/km–5:45/km"}
        assert _other_paces(plan) != quality_before


class TestFirstPaces:
    def test_a_plan_with_no_paces_is_seeded_with_the_band_too(self, test_db):
        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        plan = _plan(test_db, user, vdot=None)
        _log_easy_runs(test_db, user, 6.0)
        for run in test_db.query(RunLog).filter(RunLog.user_id == user.id):
            run.vdot = 40.0
        test_db.flush()

        result = recalibrate_zones_only(plan, user.id, test_db)

        assert result["direction"] == "set"
        assert plan.vdot == result["new_vdot"]
        assert plan.easy_pace_min_km == 6.0
        assert _easy_paces(plan, from_week=3) == {"6:15/km–5:45/km"}
        assert _easy_paces(plan, to_week=2) == {None}


class TestSyncRecordsTheMove:
    def test_the_history_says_what_changed(self, test_db):
        from app.infrastructure.integrations.post_sync_service import (
            _refresh_easy_band_and_record,
        )

        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        plan = _plan(test_db, user, easy_pace=6.0)
        _log_easy_runs(test_db, user, 5.8)

        moved = _refresh_easy_band_and_record(plan, user.id, test_db)

        assert moved["new_easy_pace"] == 5.8
        event = plan.adaptation_history[-1]
        assert event["type"] == "easy_pace"
        assert "6:03/km–5:33/km" in event["reason"]

    def test_no_move_leaves_no_trace(self, test_db):
        from app.infrastructure.integrations.post_sync_service import (
            _refresh_easy_band_and_record,
        )

        user = _runner(test_db, max_hr=185, threshold_hr=THRESHOLD_HR)
        plan = _plan(test_db, user, easy_pace=6.0)

        assert _refresh_easy_band_and_record(plan, user.id, test_db) is None
        assert not plan.adaptation_history


class TestHomeRail:
    def test_the_rail_names_the_pace_plans_are_built_around(self):
        from app.contexts.runner.fitness.home_stats_service import _easy_now

        assert _easy_now(None) is None
        assert "6:19/km" in _easy_now(6.32)
