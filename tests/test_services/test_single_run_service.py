"""Single runs: creation, pairing with the imported activity, and the watch."""

import asyncio
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.orm import Session

from app.application import single_run_service
from app.application.single_run_service import (
    WATCH_AUTH,
    WATCH_NOT_CONNECTED,
    WATCH_PROVIDER,
    create_single_run,
    delete_single_run,
    send_to_watch,
    view_of,
)
from app.contexts.plan.adaptation.run_mapper import map_runs_to_plan
from app.application.single_run_service import plan_overlaps
from app.contexts.runner.single_runs import (
    claim_completed_single_runs,
    planned_runs_between,
    recent_weekly_km,
)
from app.core.time_utils import local_today
from app.exceptions import ValidationException
from app.infrastructure.integrations.intervals_service import (
    IntervalsAuthorizationError,
)
from app.models import DailyWorkout, RunLog, SingleRun, TrainingPlan, User, WeeklyPlan


@pytest.fixture
def runner(test_db: Session) -> User:
    user = User(id="sr-runner", email="sr@example.com")
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def connected(test_db: Session) -> User:
    user = User(
        id="sr-connected",
        email="sr-connected@example.com",
        intervals_athlete_id="i42",
        intervals_access_token="token",
    )
    test_db.add(user)
    test_db.commit()
    return user


def _log_run(db: Session, user: User, when, km: float, **fields) -> RunLog:
    run = RunLog(
        user_id=user.id,
        date=datetime.combine(when, time(7, 30)),
        distance_km=km,
        duration_minutes=km * 5.5,
        avg_pace_min_km=5.5,
        **fields,
    )
    db.add(run)
    db.commit()
    return run


def _single_run(db: Session, user: User, when, km: float, run_type="tempo"):
    single_run = SingleRun(
        user_id=user.id,
        date=when,
        run_type=run_type,
        distance_km=km,
        workout={"type": run_type, "distance": km, "steps": []},
    )
    db.add(single_run)
    db.commit()
    return single_run


def _plan_with_day(
    db: Session, user: User, km: float, workout_type: str = "easy"
) -> tuple[TrainingPlan, str]:
    """A plan that started today whose day-1 workout is a run of ``km``."""
    today = local_today()
    plan = TrainingPlan(
        id="sr-plan",
        user_id=user.id,
        start_date=datetime.combine(today, time.min),
        weeks_duration=8,
        target_distance="10",
        current_weekly_km=30,
        vdot=50.0,
        plan_data=[],
    )
    week = WeeklyPlan(id="sr-week", training_plan_id=plan.id, week_number=1)
    day = DailyWorkout(
        id="sr-day", weekly_plan_id=week.id, day_of_week=1,
        workout_type=workout_type, distance_km=km,
    )
    db.add_all([plan, week, day])
    db.commit()
    return plan, day.id


# --- creation ---------------------------------------------------------------


def test_create_without_fitness_is_by_effort(test_db, runner):
    single_run = create_single_run(
        runner, test_db, run_type="easy", distance_km=5, duration_minutes=None,
        on_date=None,
    )

    assert single_run.vdot is None
    assert single_run.date == local_today()
    assert single_run.workout["steps"]
    assert view_of(single_run, test_db).estimated_minutes is None


def test_create_uses_the_in_progress_plans_paces(test_db, runner):
    _plan_with_day(test_db, runner, 8.0)

    single_run = create_single_run(
        runner, test_db, run_type="tempo", distance_km=8, duration_minutes=None,
        on_date=None,
    )

    # The plan's VDOT, not whatever the run log would suggest: one runner must
    # not get two different threshold paces on the same calendar.
    assert single_run.vdot == 50.0
    assert "/km" in single_run.workout["description"]


def test_create_falls_back_to_recent_runs(test_db, runner, monkeypatch):
    monkeypatch.setattr(
        single_run_service.RacePredictorService,
        "get_best_recent_vdot",
        staticmethod(lambda user_id, weeks=12, *, db: 44.0),
    )

    single_run = create_single_run(
        runner, test_db, run_type="easy", distance_km=None, duration_minutes=40,
        on_date=None,
    )

    assert single_run.vdot == 44.0
    assert view_of(single_run, test_db).estimated_minutes == pytest.approx(40, abs=3)


def test_duration_without_fitness_is_refused_not_guessed(test_db, runner):
    with pytest.raises(ValidationException, match="distance"):
        create_single_run(
            runner, test_db, run_type="easy", distance_km=None, duration_minutes=40,
            on_date=None,
        )
    assert test_db.query(SingleRun).count() == 0


@pytest.mark.parametrize("offset", [-1, single_run_service.MAX_DAYS_AHEAD + 1])
def test_date_outside_the_window_is_refused(test_db, runner, offset):
    with pytest.raises(ValidationException):
        create_single_run(
            runner, test_db, run_type="easy", distance_km=5, duration_minutes=None,
            on_date=local_today() + timedelta(days=offset),
        )


def test_out_of_range_distance_is_a_validation_error(test_db, runner):
    with pytest.raises(ValidationException):
        create_single_run(
            runner, test_db, run_type="interval", distance_km=2,
            duration_minutes=None, on_date=None,
        )


def test_recent_weekly_km_averages_four_weeks(test_db, runner):
    today = local_today()
    _log_run(test_db, runner, today - timedelta(days=3), 10)
    _log_run(test_db, runner, today - timedelta(days=20), 30)
    _log_run(test_db, runner, today - timedelta(days=60), 99)  # outside the window

    assert recent_weekly_km(runner.id, test_db, today) == 10.0


# --- pairing with the imported activity -------------------------------------


def test_claim_pairs_the_closest_run_and_tags_its_type(test_db, runner):
    today = local_today()
    single_run = _single_run(test_db, runner, today, 8.0)
    far = _log_run(test_db, runner, today, 20.0)
    near = _log_run(test_db, runner, today, 7.6)

    assert claim_completed_single_runs(runner.id, test_db, today) == 1

    assert near.single_run_id == single_run.id
    assert near.workout_type == "tempo"
    assert far.single_run_id is None
    assert view_of(single_run, test_db).completed_run is near


def test_claim_ignores_a_run_nothing_like_the_session(test_db, runner):
    today = local_today()
    _single_run(test_db, runner, today, 6.0)
    run = _log_run(test_db, runner, today, 21.0)

    assert claim_completed_single_runs(runner.id, test_db, today) == 0
    assert run.single_run_id is None


def test_claim_never_takes_a_run_already_matched_to_a_planned_day(test_db, runner):
    today = local_today()
    _, day_id = _plan_with_day(test_db, runner, 8.0)
    _single_run(test_db, runner, today, 8.0)
    run = _log_run(test_db, runner, today, 8.0, daily_workout_id=day_id)

    assert claim_completed_single_runs(runner.id, test_db, today) == 0
    assert run.daily_workout_id == day_id


def test_claim_keeps_a_label_the_activity_already_had(test_db, runner):
    today = local_today()
    _single_run(test_db, runner, today, 8.0)
    run = _log_run(test_db, runner, today, 8.0, workout_type="race")

    claim_completed_single_runs(runner.id, test_db, today)

    assert run.workout_type == "race"


def test_claim_is_idempotent(test_db, runner):
    today = local_today()
    _single_run(test_db, runner, today, 8.0)
    _log_run(test_db, runner, today, 8.0)
    _log_run(test_db, runner, today, 8.2)

    assert claim_completed_single_runs(runner.id, test_db, today) == 1
    assert claim_completed_single_runs(runner.id, test_db, today) == 0
    assert test_db.query(RunLog).filter(RunLog.single_run_id.isnot(None)).count() == 1


def test_claimed_run_counts_as_volume_but_never_fills_a_planned_day(test_db, runner):
    """The "load only" contract, end to end through the real mapper."""
    today = local_today()
    plan, day_id = _plan_with_day(test_db, runner, 8.0)
    _single_run(test_db, runner, today, 8.0)
    run = _log_run(test_db, runner, today, 8.0)

    # Without the claim this run is a perfect match for the planned easy day.
    assert map_runs_to_plan(plan.id, runner.id, test_db, dry_run=True)["proposals"][0][
        "match_type"
    ] == "workout"

    claim_completed_single_runs(runner.id, test_db, today)
    result = map_runs_to_plan(plan.id, runner.id, test_db)

    assert [p["match_type"] for p in result["proposals"]] == ["weekly_volume"]
    test_db.refresh(run)
    assert run.training_plan_id == plan.id  # counted toward the plan week
    assert run.daily_workout_id is None  # the planned day is still open
    assert day_id not in {
        r.daily_workout_id for r in test_db.query(RunLog).all()
    }


# --- one run, two sessions --------------------------------------------------
#
# The plan had a run that day, the runner made a single run too, and ran once.


def _lone_run_case(db, user, *, planned_type, single_type, run_km=8.0, **run_fields):
    today = local_today()
    _, day_id = _plan_with_day(db, user, 8.0, planned_type)
    single_run = _single_run(db, user, today, 8.0, single_type)
    run = _log_run(db, user, today, run_km, **run_fields)
    claimed = claim_completed_single_runs(user.id, db, today)
    return claimed, run, single_run


def test_same_kind_of_run_is_left_for_the_plan(test_db, runner):
    # Indistinguishable sessions: claiming it would make the plan see a skip.
    claimed, run, _ = _lone_run_case(
        test_db, runner, planned_type="easy", single_type="easy"
    )

    assert claimed == 0 and run.single_run_id is None


def test_planned_family_counts_as_the_same_kind(test_db, runner):
    claimed, _, _ = _lone_run_case(
        test_db, runner, planned_type="cruise_interval", single_type="tempo"
    )

    assert claimed == 0


def test_a_run_that_looks_like_the_single_run_is_claimed(test_db, runner):
    claimed, run, single_run = _lone_run_case(
        test_db, runner, planned_type="easy", single_type="tempo",
        inferred_workout_type="tempo", inferred_type_confidence=0.9,
    )

    assert claimed == 1 and run.single_run_id == single_run.id


def test_a_run_that_looks_like_the_planned_session_is_left_for_it(test_db, runner):
    claimed, run, _ = _lone_run_case(
        test_db, runner, planned_type="easy", single_type="tempo",
        inferred_workout_type="easy", inferred_type_confidence=0.9,
    )

    assert claimed == 0 and run.single_run_id is None


def test_an_unreadable_run_goes_to_the_closer_prescription(test_db, runner):
    today = local_today()
    _plan_with_day(test_db, runner, 12.0, "easy")
    single_run = _single_run(test_db, runner, today, 8.0, "tempo")
    near_plan = _log_run(test_db, runner, today, 10.9)

    assert claim_completed_single_runs(runner.id, test_db, today) == 0

    near_plan.distance_km = 9.0
    test_db.commit()
    assert claim_completed_single_runs(runner.id, test_db, today) == 1
    assert near_plan.single_run_id == single_run.id


def test_two_runs_that_day_leave_one_for_each_session(test_db, runner):
    today = local_today()
    plan, day_id = _plan_with_day(test_db, runner, 8.0, "easy")
    single_run = _single_run(test_db, runner, today, 8.0, "easy")
    first = _log_run(test_db, runner, today, 8.0)
    second = _log_run(test_db, runner, today, 8.3)

    assert claim_completed_single_runs(runner.id, test_db, today) == 1
    map_runs_to_plan(plan.id, runner.id, test_db)

    test_db.refresh(first)
    test_db.refresh(second)
    assert first.single_run_id == single_run.id and first.daily_workout_id is None
    assert second.daily_workout_id == day_id


def test_with_several_runs_the_one_that_looks_right_is_preferred(test_db, runner):
    today = local_today()
    single_run = _single_run(test_db, runner, today, 8.0, "tempo")
    closer_but_easy = _log_run(
        test_db, runner, today, 8.0,
        inferred_workout_type="easy", inferred_type_confidence=0.9,
    )
    tempo = _log_run(
        test_db, runner, today, 9.0,
        inferred_workout_type="tempo", inferred_type_confidence=0.9,
    )

    claim_completed_single_runs(runner.id, test_db, today)

    assert tempo.single_run_id == single_run.id
    assert closer_but_easy.single_run_id is None


def test_a_planned_day_already_run_does_not_compete(test_db, runner):
    today = local_today()
    _, day_id = _plan_with_day(test_db, runner, 8.0, "easy")
    _log_run(test_db, runner, today, 8.0, daily_workout_id=day_id)
    single_run = _single_run(test_db, runner, today, 8.0, "easy")
    extra = _log_run(test_db, runner, today, 8.1)

    assert claim_completed_single_runs(runner.id, test_db, today) == 1
    assert extra.single_run_id == single_run.id


# --- what the plan already has ----------------------------------------------


def test_planned_runs_are_dated_and_skip_rest_days(test_db, runner):
    today = local_today()
    _, day_id = _plan_with_day(test_db, runner, 8.0, "tempo")
    test_db.add_all(
        [
            DailyWorkout(
                id="sr-rest", weekly_plan_id="sr-week", day_of_week=2,
                workout_type="rest", distance_km=0,
            ),
            DailyWorkout(
                id="sr-day3", weekly_plan_id="sr-week", day_of_week=3,
                workout_type="long", distance_km=16.0,
            ),
        ]
    )
    test_db.commit()

    planned = planned_runs_between(
        runner.id, test_db, today, today + timedelta(days=6)
    )

    assert [(p.workout_id, p.on_date, p.completed) for p in planned] == [
        (day_id, today, False),
        ("sr-day3", today + timedelta(days=2), False),
    ]
    assert planned_runs_between(runner.id, test_db, today, today)[0].workout_id == day_id


def test_overlaps_offer_only_open_sessions_with_a_single_run_equivalent(
    test_db, runner
):
    today = local_today()
    _, day_id = _plan_with_day(test_db, runner, 8.0, "cruise_interval")
    test_db.add(
        DailyWorkout(
            id="sr-hill", weekly_plan_id="sr-week", day_of_week=2,
            workout_type="hill", distance_km=7.0,
        )
    )
    test_db.commit()

    assert plan_overlaps(runner, test_db, today) == [
        {
            "date": today.isoformat(),
            "run_type": "tempo",
            "distance_km": 8.0,
            "url": f"/plan/sr-plan/day/{day_id}",
        }
    ]

    _log_run(test_db, runner, today, 8.0, daily_workout_id=day_id)
    assert plan_overlaps(runner, test_db, today) == []


# --- watch ------------------------------------------------------------------


def _real_single_run(db, user) -> SingleRun:
    return create_single_run(
        user, db, run_type="interval", distance_km=8, duration_minutes=None,
        on_date=None,
    )


def test_send_pushes_one_namespaced_event_and_records_it(test_db, connected):
    single_run = _real_single_run(test_db, connected)
    intervals = AsyncMock()

    error = asyncio.run(send_to_watch(single_run, connected, test_db, intervals))

    assert error is None
    token, athlete, event = intervals.push_workout.await_args.args
    assert (token, athlete) == ("token", "i42")
    assert event["external_id"] == f"runcoach-single-{single_run.id}"
    assert single_run.watch_event_hash and single_run.watch_synced_at
    assert view_of(single_run, test_db).on_watch


def test_send_without_a_connection_reports_it(test_db, runner):
    single_run = _real_single_run(test_db, runner)
    intervals = AsyncMock()

    error = asyncio.run(send_to_watch(single_run, runner, test_db, intervals))

    assert error == WATCH_NOT_CONNECTED
    intervals.push_workout.assert_not_awaited()


@pytest.mark.parametrize(
    "raised, reason",
    [(IntervalsAuthorizationError("no"), WATCH_AUTH), (RuntimeError("down"), WATCH_PROVIDER)],
)
def test_a_failed_push_is_reported_and_leaves_the_run_unsent(
    test_db, connected, raised, reason
):
    single_run = _real_single_run(test_db, connected)
    intervals = AsyncMock()
    intervals.push_workout.side_effect = raised

    assert asyncio.run(send_to_watch(single_run, connected, test_db, intervals)) == reason
    assert single_run.watch_event_hash is None


def test_delete_keeps_the_logged_run_and_removes_only_our_event(test_db, connected):
    today = local_today()
    single_run = _real_single_run(test_db, connected)
    intervals = AsyncMock()
    asyncio.run(send_to_watch(single_run, connected, test_db, intervals))
    run = _log_run(test_db, connected, today, 8.0)
    claim_completed_single_runs(connected.id, test_db, today)
    test_db.commit()
    ours = f"runcoach-single-{single_run.id}"
    intervals.fetch_events.return_value = [
        {"id": 1, "external_id": ours},
        {"id": 2, "external_id": "runcoach-someplan-1-1"},
        {"id": 3, "external_id": None},
    ]

    asyncio.run(delete_single_run(single_run, connected, test_db, intervals))

    assert test_db.query(SingleRun).count() == 0
    test_db.refresh(run)
    assert run.single_run_id is None
    assert intervals.delete_events.await_args.args[2] == [1]


def test_delete_survives_a_calendar_outage(test_db, connected):
    single_run = _real_single_run(test_db, connected)
    intervals = AsyncMock()
    asyncio.run(send_to_watch(single_run, connected, test_db, intervals))
    intervals.fetch_events.side_effect = RuntimeError("down")

    asyncio.run(delete_single_run(single_run, connected, test_db, intervals))

    assert test_db.query(SingleRun).count() == 0


def test_delete_of_an_unsent_run_never_touches_the_calendar(test_db, connected):
    single_run = _real_single_run(test_db, connected)
    intervals = AsyncMock()

    asyncio.run(delete_single_run(single_run, connected, test_db, intervals))

    intervals.fetch_events.assert_not_awaited()
