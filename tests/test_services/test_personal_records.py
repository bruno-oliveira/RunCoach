"""Tests for personal records detection."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.runner.fitness.personal_records_service import PersonalRecordsService
from app.models import Base, RunLog, User
from app.utils import format_pace_bare


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


def _user(db):
    u = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
    db.add(u)
    db.flush()
    return u


def _run(db, user, *, days_ago, dist, dur_min, pace=None, vdot=None):
    db.add(
        RunLog(
            id=_uid(),
            user_id=user.id,
            date=_now() - timedelta(days=days_ago),
            distance_km=dist,
            duration_minutes=dur_min,
            avg_pace_min_km=pace,
            vdot=vdot,
        )
    )


def test_format_pace():
    assert format_pace_bare(5.5) == "5:30"
    assert format_pace_bare(4.0) == "4:00"


def test_no_runs(db):
    user = _user(db)
    result = PersonalRecordsService.get_personal_records(user.id, db)
    assert result["available"] is False
    assert result["records"] == []


def test_distance_records_track_progression(db):
    user = _user(db)
    # Two 5K efforts, the later one faster → PR progression with improvement.
    _run(db, user, days_ago=30, dist=5.0, dur_min=25.0, pace=5.0, vdot=44)
    _run(db, user, days_ago=5, dist=5.0, dur_min=24.0, pace=4.8, vdot=46)
    db.commit()

    result = PersonalRecordsService.get_personal_records(user.id, db)
    assert result["available"] is True
    five_k = next(r for r in result["distance_records"] if r["distance_name"] == "5K")
    assert five_k["pr_count"] == 2
    assert five_k["attempts"] == 2
    # Second PR records an improvement over the first.
    assert "improvement_seconds" in five_k["history"][-1]
    assert five_k["current_pr"]["pace_min_km"] == 4.8


def test_general_records(db):
    user = _user(db)
    _run(db, user, days_ago=10, dist=21.1, dur_min=110.0, pace=5.2, vdot=48)
    _run(db, user, days_ago=3, dist=5.0, dur_min=22.0, pace=4.4, vdot=50)
    db.commit()

    result = PersonalRecordsService.get_personal_records(user.id, db)
    general = {g["type"]: g for g in result["general"]}
    assert general["longest_run"]["value"] == 21.1
    assert general["fastest_pace"]["value"] == 4.4
    assert general["highest_vdot"]["value"] == 50
    assert "best_week" in general
