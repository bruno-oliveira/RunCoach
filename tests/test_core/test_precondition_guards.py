"""Tests for the precondition-guard module used by ``_run_adjust``.

These tests build the smallest possible plan/user/run rows needed to walk
each of the four early-exit branches plus the happy "proceed" path.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation import change_reasons as _reasons
from app.contexts.plan.adaptation.precondition_guards import (
    check_preconditions_or_gather,
)
from app.models import Base, RunLog, TrainingPlan, User


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _uid():
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _make_user(db):
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()
    return user


def _make_plan(db, user, *, start_date=None):
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="5",
        weeks_duration=8,
        vdot=45.0,
        plan_data=[],
        start_date=start_date,
    )
    db.add(plan)
    db.flush()
    return plan


def _add_runs(db, user, plan, count, *, days_ago_start=1):
    for i in range(count):
        db.add(
            RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                date=_now() - timedelta(days=days_ago_start + i),
                distance_km=5.0,
                duration_minutes=30.0,
            )
        )
    db.flush()


@pytest.mark.parametrize("mode", ["applied", "preview"])
def test_plan_not_found_returns_early_with_plan_not_found_reason(db, mode):
    early, gathered = check_preconditions_or_gather(_uid(), _uid(), db, mode=mode)
    assert gathered is None
    assert early is not None
    assert early["adjusted"] is False
    assert early["reason"] == "Plan not found"
    assert early["change_plan"]["mode"] == mode
    assert early["change_plan"]["action"] == "adjust"
    assert early["change_plan"]["reason"] == "Plan not found."


@pytest.mark.parametrize("mode", ["applied", "preview"])
def test_no_start_date_returns_NO_CHANGE_PLAN_NOT_STARTED(db, mode):
    user = _make_user(db)
    plan = _make_plan(db, user, start_date=None)

    early, gathered = check_preconditions_or_gather(plan.id, user.id, db, mode=mode)
    assert gathered is None
    assert early is not None
    assert early["reason"] == "Plan has no start date."
    assert early["change_plan"]["reason"] == _reasons.NO_CHANGE_PLAN_NOT_STARTED
    assert early["change_plan"]["mode"] == mode


@pytest.mark.parametrize("mode", ["applied", "preview"])
def test_insufficient_runs_returns_NO_CHANGE_INSUFFICIENT_DATA_with_total_runs(
    db, mode
):
    user = _make_user(db)
    plan = _make_plan(db, user, start_date=_now() - timedelta(weeks=2))
    _add_runs(db, user, plan, count=1)

    early, gathered = check_preconditions_or_gather(plan.id, user.id, db, mode=mode)
    assert gathered is None
    assert early is not None
    assert "Not enough data" in early["reason"]
    assert early["total_runs"] == 1
    assert early["change_plan"]["reason"] == _reasons.NO_CHANGE_INSUFFICIENT_DATA
    assert early["change_plan"]["mode"] == mode


@pytest.mark.parametrize("mode", ["applied", "preview"])
def test_no_past_workouts_returns_no_past_workouts_reason(db, mode):
    """Plan starts in the future, runs are logged, but no workouts have been
    scheduled yet — gather_signals returns None after the past-workouts check."""
    user = _make_user(db)
    # Future start date and an empty plan_data → no past workouts.
    plan = _make_plan(db, user, start_date=_now() + timedelta(weeks=1))
    _add_runs(db, user, plan, count=3)

    early, gathered = check_preconditions_or_gather(plan.id, user.id, db, mode=mode)
    assert gathered is None
    assert early is not None
    assert early["reason"] == "No past workouts to evaluate yet."
    assert early["change_plan"]["reason"] == "No past workouts to evaluate yet."
    assert early["change_plan"]["mode"] == mode


def test_proceed_when_gather_signals_returns_dict(db, monkeypatch):
    """When gather_signals has enough data, the guard returns (None, gathered)."""
    sentinel = {"training_plan": "x", "signals": {"multiplier": 1.0}}

    def fake_gather(plan_id, user_id, db_):  # noqa: ARG001
        return sentinel

    monkeypatch.setattr(
        "app.contexts.plan.adaptation.plan_adjuster.gather_signals",
        fake_gather,
    )

    early, gathered = check_preconditions_or_gather(_uid(), _uid(), db, mode="applied")
    assert early is None
    assert gathered is sentinel
