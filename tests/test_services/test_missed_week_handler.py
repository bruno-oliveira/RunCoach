"""Missed-week detection: weeks of a started plan with nothing logged.

The result drives the "you missed weeks 2-3, want to adjust?" prompt, so a false
positive nags a runner who did nothing wrong and a false negative hides a real
gap. Its preconditions (no plan, other runner's plan, no start date) all have to
answer `[]` rather than raise. There was no test here before.
"""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from app.contexts.plan.adaptation.missed_week_handler import detect_missed_weeks
from app.core.time_utils import local_today
from app.models import RunLog, TrainingPlan, User

WEEKS = 8


def _user(db: Session) -> User:
    user = User(id=str(uuid4()), email=f"{uuid4().hex[:8]}@t.com")
    db.add(user)
    db.flush()
    return user


def _plan(db: Session, user: User, *, days_ago: int | None = 14) -> TrainingPlan:
    plan = TrainingPlan(
        id=str(uuid4()),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=WEEKS,
        start_date=(
            local_today() - timedelta(days=days_ago) if days_ago is not None else None
        ),
    )
    db.add(plan)
    db.flush()
    return plan


def _run(db: Session, user: User, plan: TrainingPlan, *, days_ago: int | None) -> None:
    db.add(
        RunLog(
            id=str(uuid4()),
            user_id=user.id,
            training_plan_id=plan.id,
            date=local_today() - timedelta(days=days_ago)
            if days_ago is not None
            else None,
            distance_km=8.0,
            duration_minutes=45.0,
        )
    )
    db.flush()


def test_a_week_with_nothing_logged_is_reported(test_db: Session):
    user = _user(test_db)
    # 14 days in → weeks 1 and 2 are complete, week 3 is current.
    plan = _plan(test_db, user)
    _run(test_db, user, plan, days_ago=13)  # week 1

    assert detect_missed_weeks(plan.id, user.id, test_db) == [2]


def test_a_fully_run_plan_reports_nothing_missed(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user)
    _run(test_db, user, plan, days_ago=13)  # week 1
    _run(test_db, user, plan, days_ago=6)  # week 2

    assert detect_missed_weeks(plan.id, user.id, test_db) == []


def test_only_weeks_before_the_current_one_are_judged(test_db: Session):
    """The week in progress is not a missed week."""
    user = _user(test_db)
    # 8 days in → week 2 is current, so only week 1 can be missed.
    plan = _plan(test_db, user, days_ago=8)

    assert detect_missed_weeks(plan.id, user.id, test_db) == [1]


def test_an_unknown_plan_reports_nothing(test_db: Session):
    user = _user(test_db)

    assert detect_missed_weeks(str(uuid4()), user.id, test_db) == []


def test_another_runners_plan_is_not_readable(test_db: Session):
    owner = _user(test_db)
    intruder = _user(test_db)
    plan = _plan(test_db, owner)

    assert detect_missed_weeks(plan.id, intruder.id, test_db) == []


def test_a_plan_without_a_start_date_reports_nothing(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user, days_ago=None)

    assert detect_missed_weeks(plan.id, user.id, test_db) == []


def test_runs_before_the_plan_started_are_ignored(test_db: Session):
    """Only runs inside the plan's calendar count toward a week."""
    user = _user(test_db)
    plan = _plan(test_db, user, days_ago=14)
    _run(test_db, user, plan, days_ago=30)  # before the plan began

    assert detect_missed_weeks(plan.id, user.id, test_db) == [1, 2]


def test_an_undated_run_is_ignored_rather_than_crashing(test_db: Session):
    """`RunLog.date` is nullable; an undated run cannot fill a week."""
    user = _user(test_db)
    plan = _plan(test_db, user)
    _run(test_db, user, plan, days_ago=None)

    assert detect_missed_weeks(plan.id, user.id, test_db) == [1, 2]


def test_another_runners_runs_do_not_fill_these_weeks(test_db: Session):
    user = _user(test_db)
    other = _user(test_db)
    plan = _plan(test_db, user)
    _run(test_db, other, plan, days_ago=13)

    assert detect_missed_weeks(plan.id, user.id, test_db) == [1, 2]
