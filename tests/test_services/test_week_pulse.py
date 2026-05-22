"""Tests for the week-pulse inline feedback generator."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.runner.enrichment.week_pulse_generator import get_week_pulse
from app.models import Base, RunLog, TrainingPlan, User


def _uid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


def _plan(db, *, with_start=True, planned_km=30.0):
    user = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
    db.add(user)
    db.flush()
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="21.1",
        weeks_duration=8,
        start_date=_now() - timedelta(weeks=1) if with_start else None,
        plan_data=[{"week": 2, "total_km": planned_km, "daily_workouts": []}],
    )
    db.add(plan)
    db.flush()
    return user, plan


def _run(db, user, plan, *, days_ago, dist, effort=None):
    db.add(
        RunLog(
            id=_uid(),
            user_id=user.id,
            training_plan_id=plan.id,
            date=_now() - timedelta(days=days_ago),
            distance_km=dist,
            duration_minutes=int(dist * 6),
            perceived_effort=effort,
        )
    )


# current_week=2: week_start == today, prev week == [today-7d, today).
_WK = 2


def test_no_start_date(db):
    user, plan = _plan(db, with_start=False)
    assert get_week_pulse(plan, _WK, db) is None


def test_no_runs_returns_none(db):
    user, plan = _plan(db)
    assert get_week_pulse(plan, _WK, db) is None


def test_on_track_positive(db):
    user, plan = _plan(db, planned_km=30.0)
    _run(db, user, plan, days_ago=0, dist=28.0, effort=4)
    db.commit()
    pulse = get_week_pulse(plan, _WK, db)
    assert pulse["mood"] == "positive"
    assert pulse["runs_this_week"] == 1
    assert pulse["km_this_week"] == 28.0
    assert any("fresh" in d for d in pulse["details"])


def test_partial_progress(db):
    user, plan = _plan(db, planned_km=30.0)
    _run(db, user, plan, days_ago=0, dist=20.0, effort=6)
    db.commit()
    pulse = get_week_pulse(plan, _WK, db)
    assert "%" in pulse["message"]
    assert any("working range" in d for d in pulse["details"])


def test_hard_week_caution(db):
    user, plan = _plan(db, planned_km=30.0)
    _run(db, user, plan, days_ago=0, dist=10.0, effort=9)
    db.commit()
    pulse = get_week_pulse(plan, _WK, db)
    assert pulse["mood"] == "caution"
    assert any("running hard" in d for d in pulse["details"])


def test_effort_climbing_vs_last_week(db):
    # planned_km=0 so the per-week pct message doesn't pre-empt the headline,
    # letting the effort-climbing message surface as message[0].
    user, plan = _plan(db, planned_km=0.0)
    # Easy last week, hard this week → effort-climbing caution message.
    _run(db, user, plan, days_ago=4, dist=10.0, effort=4)
    _run(db, user, plan, days_ago=0, dist=10.0, effort=8)
    db.commit()
    pulse = get_week_pulse(plan, _WK, db)
    assert "fatigue" in pulse["message"].lower()
    assert pulse["mood"] == "caution"


def test_no_runs_this_week_but_prev(db):
    user, plan = _plan(db, planned_km=30.0)
    _run(db, user, plan, days_ago=4, dist=12.0, effort=5)
    db.commit()
    pulse = get_week_pulse(plan, _WK, db)
    assert pulse["runs_this_week"] == 0
    assert "No runs logged yet" in pulse["message"]
