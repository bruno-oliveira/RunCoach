"""Tests for the daily readiness CheckInService (once-per-day upsert + scoring)."""

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.runner.wellness.checkin_service import CheckInService
from app.models import Base, ReadinessLog, User


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
    u = User(id="rc-user", email="rc@example.com", name="RC")
    db.add(u)
    db.commit()
    return u


DAY = date(2026, 7, 22)


def test_record_creates_scored_log(db, user):
    svc = CheckInService(db)
    log = svc.record(
        user.id, sleep_hours=8, sleep_quality=5, energy=5, soreness=1, on_date=DAY
    )
    assert log.id
    assert log.date == DAY
    assert log.score == 100.0
    assert db.query(ReadinessLog).count() == 1


def test_second_record_same_day_upserts(db, user):
    svc = CheckInService(db)
    first = svc.record(user.id, sleep_hours=5, soreness=5, on_date=DAY)
    low_score = first.score
    second = svc.record(
        user.id, sleep_hours=8, sleep_quality=5, energy=5, soreness=1, on_date=DAY
    )
    # Same row, re-scored — not a duplicate.
    assert second.id == first.id
    assert db.query(ReadinessLog).count() == 1
    assert second.score != low_score
    assert second.score == 100.0


def test_different_days_are_separate_rows(db, user):
    svc = CheckInService(db)
    svc.record(user.id, energy=3, on_date=date(2026, 7, 21))
    svc.record(user.id, energy=4, on_date=date(2026, 7, 22))
    assert db.query(ReadinessLog).count() == 2


def test_get_today_returns_the_days_log(db, user):
    svc = CheckInService(db)
    svc.record(user.id, energy=4, on_date=DAY)
    assert svc.get_today(user.id, on_date=DAY) is not None
    assert svc.get_today(user.id, on_date=date(2026, 7, 23)) is None


def test_assess_recovers_band_and_drivers(db, user):
    svc = CheckInService(db)
    log = svc.record(user.id, sleep_hours=5, soreness=4, energy=2, on_date=DAY)
    assessment = CheckInService.assess(log)
    assert assessment.is_low is True
    assert "your legs are heavy" in assessment.drivers


def test_list_recent_orders_newest_first_and_respects_window(db, user):
    from app.core.time_utils import local_today

    today = local_today()
    svc = CheckInService(db)
    svc.record(user.id, energy=3, on_date=today - timedelta(days=2))
    svc.record(user.id, energy=4, on_date=today)
    svc.record(user.id, energy=2, on_date=today - timedelta(days=40))  # outside window

    recent = svc.list_recent(user.id, days=14)
    assert [log.date for log in recent] == [today, today - timedelta(days=2)]
