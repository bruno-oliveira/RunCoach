"""The Coach page end to end: what a runner in each situation is told."""

from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.application.coach_read_service import CHART_WEEKS, build_coach_page
from app.core.time_utils import local_today
from app.dependencies import get_current_user, get_db, get_optional_user
from app.main import app
from app.models import DailyWorkout, RunLog, TrainingPlan, User, WeeklyPlan


@pytest.fixture
def runner(test_db: Session) -> User:
    user = User(id="coach-runner", email="coach-runner@example.com")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def api(test_db: Session):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _as(user: User | None) -> None:
    async def override():
        return user

    app.dependency_overrides[get_current_user] = override
    app.dependency_overrides[get_optional_user] = override


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _log(db: Session, user: User, day: date, km: float, kind: str = "easy") -> None:
    db.add(
        RunLog(
            user_id=user.id,
            date=datetime.combine(day, time(7, 0)),
            distance_km=km,
            duration_minutes=km * 6,
            workout_type=kind,
        )
    )


def _log_weeks(db: Session, user: User, weeks: int, runs: list[tuple[int, float, str]]):
    """Log the same week of ``(weekday, km, type)`` runs for the last ``weeks``."""
    this_monday = _monday(local_today())
    for back in range(1, weeks + 1):
        monday = this_monday - timedelta(weeks=back)
        for weekday, km, kind in runs:
            _log(db, user, monday + timedelta(days=weekday), km, kind)
    db.commit()


def _plan(
    db: Session, user: User, *, weeks_ago: int, week: list[tuple[int, str, float]]
):
    """A plan that started ``weeks_ago`` Mondays back, every week the same."""
    start = _monday(local_today()) - timedelta(weeks=weeks_ago)
    db.add(
        TrainingPlan(
            id="coach-plan",
            user_id=user.id,
            start_date=datetime.combine(start, time.min),
            weeks_duration=12,
            target_distance="21.1",
            current_weekly_km=30,
            plan_data=[],
        )
    )
    for number in range(1, 13):
        week_id = f"coach-week-{number}"
        db.add(
            WeeklyPlan(id=week_id, training_plan_id="coach-plan", week_number=number)
        )
        for day_of_week, kind, km in week:
            db.add(
                DailyWorkout(
                    weekly_plan_id=week_id,
                    day_of_week=day_of_week,
                    workout_type=kind,
                    distance_km=km,
                )
            )
    db.commit()


VARIED_WEEK = [(0, 6.0, "easy"), (2, 8.0, "tempo"), (4, 6.0, "easy"), (6, 14.0, "long")]
PLAN_WEEK = [(1, "easy", 6.0), (3, "tempo", 8.0), (5, "easy", 6.0), (7, "long", 14.0)]


def test_signed_out_visitors_are_sent_home(api):
    _as(None)

    assert api.get("/coach", follow_redirects=False).status_code == 302


def test_the_old_address_still_lands_on_the_page(api, runner):
    _as(runner)

    response = api.get("/analytics", follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["location"] == "/coach"


def test_a_runner_with_no_runs_is_told_there_is_nothing_to_read(api, runner):
    _as(runner)

    page = api.get("/coach")

    assert page.status_code == 200
    assert 'data-i18n="coach.head_no_runs"' in page.text
    assert "connectWatch()" in page.text
    # Nothing to configure, and nothing to chart.
    assert "<select" not in page.text and "coach-bars" not in page.text


def test_free_running_with_no_goal_is_read_from_the_runs_alone(api, runner, test_db):
    _log_weeks(
        test_db, runner, 6, [(0, 6.0, "easy"), (2, 6.0, "easy"), (4, 6.5, "easy")]
    )
    _as(runner)

    page = api.get("/coach")

    assert 'data-i18n="coach.no_goal"' in page.text
    # All easy, all one length: the first of the two becomes the one change.
    assert 'data-i18n="coach.head_tune"' in page.text
    assert page.text.count('data-i18n="coach.all_easy"') == 2
    assert 'data-i18n="coach.same_length"' in page.text
    assert 'href="/run"' in page.text


def test_too_much_hard_running_leads_the_page(api, runner, test_db):
    _log_weeks(
        test_db, runner, 6, [(0, 8.0, "tempo"), (2, 8.0, "interval"), (5, 12.0, "easy")]
    )
    _as(runner)

    page = api.get("/coach")

    assert 'data-i18n="coach.head_attention"' in page.text
    assert "coach-read--change" in page.text
    assert 'data-i18n="coach.too_hard_do"' in page.text


def test_a_plan_run_as_written_is_on_track(api, runner, test_db):
    _plan(test_db, runner, weeks_ago=4, week=PLAN_WEEK)
    _log_weeks(test_db, runner, 4, VARIED_WEEK)
    _as(runner)

    page = api.get("/coach")

    assert 'data-i18n="coach.head_goal_on_track"' in page.text
    assert "Week 5 of 12" in page.text
    for key in ("sessions_ok", "volume_ok", "long_on_plan"):
        assert f'data-i18n="coach.{key}"' in page.text
    assert 'data-i18n="coach.nothing_to_change"' in page.text


def test_runs_count_toward_the_goal_whichever_day_they_were_done(runner, test_db):
    _plan(test_db, runner, weeks_ago=4, week=PLAN_WEEK)
    # Every session a day late, and none of them matched to a planned day.
    _log_weeks(
        test_db, runner, 4, [(1, 6.0, "easy"), (3, 8.0, "tempo"), (5, 20.0, "long")]
    )

    read = build_coach_page(runner, test_db, local_today()).read

    by_area = {finding.area: finding for finding in read.goal_findings}
    assert by_area["volume"].key == "volume_ok"
    assert by_area["sessions"].figures == (9, 12)


def test_a_plan_being_skipped_says_so_and_points_at_the_plan(api, runner, test_db):
    _plan(test_db, runner, weeks_ago=4, week=PLAN_WEEK)
    # One run a week, on the Sunday — recent enough on any day this test runs
    # that the runner has not "gone quiet", which would outrank the goal.
    _log_weeks(test_db, runner, 4, [(6, 6.0, "easy")])
    _as(runner)

    page = api.get("/coach")

    assert 'data-i18n="coach.head_goal_behind"' in page.text
    assert page.text.count('data-i18n="coach.sessions_missed"') == 2
    assert 'class="btn btn-accent" href="/plan/coach-plan"' in page.text


def _predict(monkeypatch, **seconds_by_distance):
    """Stand in for the race predictor: ``{"10K": 3300}`` and nothing else."""
    distances = {"5K": 5.0, "10K": 10.0, "half_marathon": 21.0975, "trail": 30.0}
    predictions = {
        name: {"seconds": seconds, "distance_km": distances[name]}
        for name, seconds in seconds_by_distance.items()
    }
    monkeypatch.setattr(
        "app.application.coach_read_service.RacePredictorService."
        "get_predictions_for_user",
        lambda user_id, db: {"vdot_trend": "stable", "predictions": predictions},
    )


def _set_goal(db, **fields):
    plan = db.get(TrainingPlan, "coach-plan")
    for name, value in fields.items():
        setattr(plan, name, value)
    db.commit()


def test_a_goal_time_out_of_reach_is_said_in_times(api, runner, test_db, monkeypatch):
    _plan(test_db, runner, weeks_ago=4, week=PLAN_WEEK)
    _set_goal(test_db, goal_time="1:45:00")
    _log_weeks(test_db, runner, 4, VARIED_WEEK)
    _predict(monkeypatch, half_marathon=7200)
    _as(runner)

    page = api.get("/coach")

    assert 'data-i18n="coach.head_goal_behind"' in page.text
    assert page.text.count('data-i18n="coach.time_far"') == 2
    assert "2:00:00" in page.text and "1:45:00" in page.text


def test_a_reachable_goal_time_leaves_the_plan_on_track(runner, test_db, monkeypatch):
    _plan(test_db, runner, weeks_ago=4, week=PLAN_WEEK)
    _set_goal(test_db, goal_time="1:45:00")
    _log_weeks(test_db, runner, 4, VARIED_WEEK)
    _predict(monkeypatch, half_marathon=6400)

    page = build_coach_page(runner, test_db, local_today())

    by_area = {finding.area: finding for finding in page.read.goal_findings}
    # 1.6% to find with seven weeks left after this one.
    assert by_area["race_time"].key == "time_reachable"
    assert by_area["race_time"].figures == (6400, 6300)
    assert page.goal is not None
    assert (page.goal.predicted_time, page.goal.goal_time) == ("1:46:40", "1:45:00")


def test_a_goal_with_no_time_has_no_time_to_judge(runner, test_db, monkeypatch):
    _plan(test_db, runner, weeks_ago=4, week=PLAN_WEEK)
    _log_weeks(test_db, runner, 4, VARIED_WEEK)
    _predict(monkeypatch, half_marathon=7200)

    page = build_coach_page(runner, test_db, local_today())

    assert "race_time" not in {finding.area for finding in page.read.goal_findings}
    assert page.goal is not None and page.goal.goal_time is None


def test_a_trail_goal_is_not_held_to_a_road_prediction(runner, test_db, monkeypatch):
    _plan(test_db, runner, weeks_ago=4, week=PLAN_WEEK)
    _set_goal(test_db, goal_time="3:30:00", target_distance="30", is_trail=True)
    _log_weeks(test_db, runner, 4, VARIED_WEEK)
    _predict(monkeypatch, trail=14400)

    read = build_coach_page(runner, test_db, local_today()).read

    assert "race_time" not in {finding.area for finding in read.goal_findings}


def test_no_prediction_for_the_goal_distance_means_no_verdict(
    runner, test_db, monkeypatch
):
    _plan(test_db, runner, weeks_ago=4, week=PLAN_WEEK)
    _set_goal(test_db, goal_time="1:45:00")
    _log_weeks(test_db, runner, 4, VARIED_WEEK)
    _predict(monkeypatch)

    read = build_coach_page(runner, test_db, local_today()).read

    assert "race_time" not in {finding.area for finding in read.goal_findings}


def test_a_goal_time_is_judged_in_the_plans_first_week(
    api, runner, test_db, monkeypatch
):
    _plan(test_db, runner, weeks_ago=0, week=PLAN_WEEK)
    _set_goal(test_db, goal_time="1:45:00")
    _log_weeks(test_db, runner, 4, VARIED_WEEK)
    _predict(monkeypatch, half_marathon=6300)
    _as(runner)

    page = api.get("/coach")

    assert 'data-i18n="coach.time_ahead"' in page.text
    # Nothing has been run against the plan yet, and the page still says so.
    assert 'data-i18n="coach.goal_too_early"' in page.text
    assert 'data-i18n="coach.goal_window"' not in page.text


def test_a_plan_in_its_first_week_is_not_judged(api, runner, test_db):
    _plan(test_db, runner, weeks_ago=0, week=PLAN_WEEK)
    _log_weeks(test_db, runner, 4, VARIED_WEEK)
    _as(runner)

    page = api.get("/coach")

    assert 'data-i18n="coach.head_goal_too_early"' in page.text
    assert 'data-i18n="coach.goal_too_early"' in page.text


def test_the_week_strip_ends_on_the_week_in_progress(runner, test_db):
    today = local_today()
    _log_weeks(test_db, runner, 2, [(0, 10.0, "easy")])
    _log(test_db, runner, _monday(today), 5.0)
    test_db.commit()

    weeks = build_coach_page(runner, test_db, today).weeks

    assert len(weeks) == CHART_WEEKS
    assert [week.km for week in weeks[-3:]] == [10.0, 10.0, 5.0]
    assert weeks[-1].in_progress and weeks[-1].height_pct == 50
    assert not any(week.in_progress for week in weeks[:-1])


def test_weeks_before_a_new_runners_first_run_are_not_blank_weeks(runner, test_db):
    _log_weeks(
        test_db, runner, 3, [(0, 5.0, "easy"), (2, 5.0, "easy"), (4, 8.0, "easy")]
    )

    read = build_coach_page(runner, test_db, local_today()).read

    assert "patchy" not in {finding.key for finding in read.recent_findings}


def test_a_runner_who_stopped_long_ago_is_told_so(api, runner, test_db):
    _log(test_db, runner, local_today() - timedelta(days=120), 8.0)
    test_db.commit()
    _as(runner)

    page = api.get("/coach")

    assert 'data-i18n="coach.gone_quiet"' in page.text
    assert "120" in page.text


def test_best_times_are_listed_quietly(api, runner, test_db):
    _log_weeks(
        test_db, runner, 4, [(0, 5.0, "easy"), (2, 10.0, "easy"), (5, 6.0, "easy")]
    )
    _as(runner)

    page = api.get("/coach")

    assert '<details class="coach-records">' in page.text
    assert "5K" in page.text and "10K" in page.text
