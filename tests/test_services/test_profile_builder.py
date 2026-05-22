"""Tests for RunnerProfile assembly from logged runs."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.runner.profile.profile_builder import build_profile
from app.models import Base, RunLog, User


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


def _add_run(db, user, *, weeks_ago, dist, pace, hr=None, elev=0.0, wtype="easy"):
    db.add(
        RunLog(
            id=_uid(),
            user_id=user.id,
            date=_now() - timedelta(weeks=weeks_ago),
            distance_km=dist,
            duration_minutes=int(dist * pace),
            avg_pace_min_km=pace,
            avg_heart_rate=hr,
            elevation_gain_m=elev,
            workout_type=wtype,
        )
    )


class TestBuildProfile:
    def test_insufficient_data(self, db):
        user = _user(db)
        _add_run(db, user, weeks_ago=1, dist=5.0, pace=6.0)
        _add_run(db, user, weeks_ago=2, dist=5.0, pace=6.0)
        db.commit()
        profile = build_profile(user.id, db)
        assert profile.has_sufficient_data is False
        assert profile.total_runs == 0  # default profile, not populated

    def test_full_profile_populated(self, db):
        user = _user(db)
        # One run per week for 8 weeks, with HR + pace for efficiency.
        for wk in range(8, 0, -1):
            _add_run(
                db,
                user,
                weeks_ago=wk,
                dist=6.0 + wk * 0.5,
                pace=6.0,
                hr=150,
                wtype="easy" if wk % 2 else "tempo",
            )
        db.commit()

        profile = build_profile(user.id, db)
        assert profile.has_sufficient_data is True
        assert profile.total_runs == 8
        assert profile.weeks_of_data >= 1
        assert profile.avg_weekly_km > 0
        assert profile.peak_weekly_km >= profile.avg_weekly_km
        assert profile.runs_per_week == 1.0
        assert profile.rest_days_per_week == 6.0
        assert profile.longest_run_km > 0
        assert profile.avg_run_km > 0
        assert profile.avg_pace_min_km == 6.0
        # 8 efficiency-eligible runs → efficiency + trend computed.
        assert profile.avg_efficiency is not None
        assert profile.efficiency_trend_pct is not None
        # Workout types counted.
        assert sum(profile.workout_type_counts.values()) == 8

    def test_volume_trend_increasing(self, db):
        user = _user(db)
        # Low early weeks, high later weeks → increasing trend.
        for wk, dist in zip(range(8, 0, -1), [4, 4, 5, 5, 11, 11, 12, 12]):
            _add_run(db, user, weeks_ago=wk, dist=dist, pace=6.0)
        db.commit()
        profile = build_profile(user.id, db)
        assert profile.volume_trend == "increasing"

    def test_trail_runs_detected(self, db):
        user = _user(db)
        for wk in range(8, 0, -1):
            # 25 m/km climb → classified as trail.
            _add_run(db, user, weeks_ago=wk, dist=10.0, pace=6.5, elev=250.0)
        db.commit()
        profile = build_profile(user.id, db)
        assert profile.trail_runs_count == 8
        assert profile.trail_total_km > 0
        assert profile.trail_weekly_km > 0
