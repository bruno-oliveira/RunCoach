"""Regression tests for TrainingLoadService load fidelity (audit B4/B5/B6)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.runner.fitness.training_load_service import TrainingLoadService
from app.models import Base, RunLog, User


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
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


def _run(user_id, dt, *, minutes=60, wtype=None, rpe=None, hr=None):
    return RunLog(
        id=_uid(),
        user_id=user_id,
        date=dt,
        duration_minutes=minutes,
        distance_km=10.0,
        workout_type=wtype,
        perceived_effort=rpe,
        avg_heart_rate=hr,
    )


class TestIntensityAwareLoad:
    """B5: load is no longer intensity-blind for HR/RPE-less runs."""

    def test_type_differentiates_equal_duration_runs(self):
        u = "u1"
        easy = _run(u, _now(), minutes=60, wtype="easy")
        tempo = _run(u, _now(), minutes=60, wtype="tempo")
        interval = _run(u, _now(), minutes=60, wtype="interval")
        le = TrainingLoadService._run_load(easy)
        lt = TrainingLoadService._run_load(tempo)
        li = TrainingLoadService._run_load(interval)
        assert le < lt < li, f"expected easy<tempo<interval, got {le} {lt} {li}"

    def test_rpe_takes_priority_over_type(self):
        u = "u1"
        run = _run(u, _now(), minutes=60, wtype="easy", rpe=9)
        # RPE 9 -> intensity 0.5 + 0.9*1.5 = 1.85, well above the easy-type 0.8.
        assert TrainingLoadService._run_load(run) > 100

    def test_hr_fraction_is_clamped(self):
        u = "u1"
        run = _run(u, _now(), minutes=60, wtype="easy", hr=400)  # bad reading
        # Clamped at 1.8 -> 60 * 1.8 = 108, not 60 * 2.67.
        assert TrainingLoadService._run_load(run) == pytest.approx(108.0)


class TestAcwrInsufficientData:
    """B6: ACWR uses min(days, 28) and reports insufficient_data when thin."""

    def test_short_history_reports_insufficient_data(self, db):
        u = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
        db.add(u)
        db.flush()
        start = _now() - timedelta(days=10)
        for i in range(10):
            db.add(_run(u.id, start + timedelta(days=i), minutes=50, wtype="easy"))
        db.commit()

        res = TrainingLoadService.get_training_load(u.id, db, lookback_days=90)
        assert res["available"] is True
        assert res["current"]["risk"] == "insufficient_data"
        assert res["current"]["load_confidence"] == "low"

    def test_long_steady_history_is_optimal_not_false_high(self, db):
        u = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
        db.add(u)
        db.flush()
        start = _now() - timedelta(days=60)
        for i in range(60):
            db.add(_run(u.id, start + timedelta(days=i), minutes=50, wtype="easy"))
        db.commit()

        res = TrainingLoadService.get_training_load(u.id, db, lookback_days=30)
        cur = res["current"]
        # Steady identical daily load => ACWR ~1.0 and high confidence.
        assert cur["risk"] in ("optimal", "low")
        assert cur["load_confidence"] == "high"
        assert 0.8 <= cur["acwr"] <= 1.3


class TestCtlSeeding:
    """B4: CTL/ATL are seeded from mean load, not cold-started at 0."""

    def test_ctl_is_seeded_not_zero_on_short_history(self, db):
        u = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
        db.add(u)
        db.flush()
        start = _now() - timedelta(days=7)
        for i in range(7):
            db.add(_run(u.id, start + timedelta(days=i), minutes=60, wtype="easy"))
        db.commit()

        cur = TrainingLoadService.get_training_load(u.id, db, lookback_days=90)[
            "current"
        ]
        # A cold start would leave CTL far below the ~48/day load after a week;
        # seeding keeps it in the right ballpark.
        assert cur["ctl"] > 20, f"CTL {cur['ctl']} looks cold-started"
        assert cur["load_confidence"] == "low"
