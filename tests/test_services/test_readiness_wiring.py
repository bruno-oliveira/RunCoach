"""Tests that real readiness logs reach the adaptation signal engine.

Covers the wiring seam scope-3 asks for: a persisted ReadinessLog is picked up
by ``_recent_readiness_logs`` and, fed into ``compute_adjustment_signals``,
drives the readiness signal (``source="logs"``) instead of the TSB fallback.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation.plan_adjuster import _recent_readiness_logs
from app.contexts.plan.adaptation.signal_computer import compute_adjustment_signals
from app.contexts.runner.wellness.checkin_service import CheckInService
from app.models import Base, ReadinessLog, User

TODAY = date(2026, 7, 22)


def _uid() -> str:
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


@pytest.fixture()
def user(db: Session) -> User:
    u = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(u)
    db.commit()
    return u


def _log(db, user, day, **kw):
    CheckInService(db).record(user.id, on_date=day, **kw)


def test_recent_readiness_logs_filters_window_user_and_null_score(db, user):
    other = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(other)
    db.commit()

    _log(db, user, TODAY, energy=4)
    _log(db, user, TODAY - timedelta(days=5), energy=3)
    _log(db, user, TODAY - timedelta(days=40), energy=2)  # outside 21-day window
    _log(db, other, TODAY, energy=5)  # different user
    # A scoreless row must not count.
    db.add(ReadinessLog(id=_uid(), user_id=user.id, date=TODAY - timedelta(days=1)))
    db.commit()

    logs = _recent_readiness_logs(user.id, TODAY, db)
    assert [log.date for log in logs] == [TODAY, TODAY - timedelta(days=5)]


def test_readiness_logs_drive_the_signal_over_tsb(db, user):
    # Three fresh mornings → the signal should read from logs, not TSB.
    for offset in (0, 1, 2):
        _log(
            db,
            user,
            TODAY - timedelta(days=offset),
            sleep_hours=8,
            sleep_quality=5,
            energy=5,
            soreness=1,
        )
    logs = _recent_readiness_logs(user.id, TODAY, db)
    assert len(logs) == 3

    result = compute_adjustment_signals(
        all_plan_runs=[],
        past_workouts=[],
        past_workout_ids=set(),
        today=TODAY,
        plan_id="plan-x",
        db=db,
        recency_weight_fn=lambda _d: 1.0,
        readiness_logs=logs,
        training_load={"available": True, "current": {"tsb": -30.0}},
    )

    # 3 scored logs flowed through → the signal counts them and the fresh
    # mornings push the readiness factor to its top of band, overriding the
    # fatigued-TSB fallback that would otherwise have nudged down.
    assert result["readiness_log_count"] == 3
    assert result["readiness_factor"] == pytest.approx(0.92 + 1.0 * 0.13)
