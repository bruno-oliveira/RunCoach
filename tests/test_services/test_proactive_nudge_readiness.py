"""Tests for the low-readiness proactive nudge (proactive_nudge._detect_low_readiness).

A wrecked morning with a hard session still ahead this week should offer to ease
today. Mirrors the stubbing style of test_proactive_nudge: gather_signals is
stubbed so the test exercises the nudge decision, not the full pipeline.
"""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation import proactive_nudge
from app.models import Base, DailyWorkout, TrainingPlan, User, WeeklyPlan

TODAY = date(2026, 6, 19)  # a Friday → isoweekday 5
CURRENT_WEEK = 3


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
def freeze_today(monkeypatch):
    monkeypatch.setattr(
        "app.contexts.plan.adaptation.proactive_nudge.today_date", lambda: TODAY
    )


@pytest.fixture()
def plan(db: Session) -> TrainingPlan:
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()
    tp = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        target_distance="10K",
        weeks_duration=8,
        start_date=datetime.combine(
            TODAY - timedelta(weeks=CURRENT_WEEK - 1), datetime.min.time()
        ),
    )
    db.add(tp)
    db.commit()
    return tp


def _gathered(**overrides):
    signals = {
        "multiplier": 1.0,
        "overreach_detected": False,
        "completion_rate": 0.9,
        "vdot_trend": "stable",
        "avg_zone_deviation": 0.0,
    }
    signals.update(overrides)
    return {
        "signals": signals,
        "current_week": CURRENT_WEEK,
        "current_day_of_week": TODAY.isoweekday(),
        "adjustable_weeks": [WeeklyPlan(week_number=CURRENT_WEEK + 1)],
    }


def _stub_gather(monkeypatch, gathered):
    monkeypatch.setattr(proactive_nudge, "gather_signals", lambda *a, **k: gathered)


def _add_current_week_with_hard_session(db, plan):
    """A current-week plan with an interval session still ahead today."""
    wp = WeeklyPlan(id=_uid(), training_plan_id=plan.id, week_number=CURRENT_WEEK)
    db.add(wp)
    db.flush()
    # Today (Friday, dow 5) has a hard interval session remaining.
    db.add(
        DailyWorkout(
            id=_uid(),
            weekly_plan_id=wp.id,
            day_of_week=TODAY.isoweekday(),
            workout_type="interval",
            distance_km=8.0,
        )
    )
    db.commit()


def _log_readiness(db, plan, *, sleep_hours=None, soreness=None, energy=None):
    from app.contexts.runner.wellness.checkin_service import CheckInService

    CheckInService(db).record(
        plan.user_id,
        sleep_hours=sleep_hours,
        soreness=soreness,
        energy=energy,
        on_date=TODAY,
    )


def test_fires_on_wrecked_morning_with_hard_session_ahead(
    db, plan, freeze_today, monkeypatch
):
    _stub_gather(monkeypatch, _gathered())
    _add_current_week_with_hard_session(db, plan)
    _log_readiness(db, plan, sleep_hours=5, soreness=5, energy=1)

    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)
    assert nudge is not None
    assert nudge["kind"] == "low_readiness"
    assert nudge["intent"] == "feeling_tired"
    assert nudge["evidence"]["readiness_band"] in ("run_down", "depleted")


def test_silent_when_no_checkin_today(db, plan, freeze_today, monkeypatch):
    _stub_gather(monkeypatch, _gathered())
    _add_current_week_with_hard_session(db, plan)
    # No readiness logged → the low-readiness guard can't fire.
    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)
    assert nudge is None or nudge["kind"] != "low_readiness"


def test_silent_on_fresh_morning(db, plan, freeze_today, monkeypatch):
    _stub_gather(monkeypatch, _gathered())
    _add_current_week_with_hard_session(db, plan)
    _log_readiness(db, plan, sleep_hours=8, soreness=1, energy=5)

    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)
    assert nudge is None or nudge["kind"] != "low_readiness"


def test_silent_when_no_hard_session_remaining(db, plan, freeze_today, monkeypatch):
    _stub_gather(monkeypatch, _gathered())
    # Current-week plan with only an easy run today — nothing hard to soften.
    wp = WeeklyPlan(id=_uid(), training_plan_id=plan.id, week_number=CURRENT_WEEK)
    db.add(wp)
    db.flush()
    db.add(
        DailyWorkout(
            id=_uid(),
            weekly_plan_id=wp.id,
            day_of_week=TODAY.isoweekday(),
            workout_type="easy",
            distance_km=5.0,
        )
    )
    db.commit()
    _log_readiness(db, plan, sleep_hours=5, soreness=5, energy=1)

    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)
    assert nudge is None or nudge["kind"] != "low_readiness"


def test_low_readiness_outranks_fitness_jump(db, plan, freeze_today, monkeypatch):
    # Even with a fitness-jump signal, a wrecked morning wins (safety first).
    _stub_gather(
        monkeypatch,
        _gathered(multiplier=1.06, vdot_trend="improving", avg_zone_deviation=-0.7),
    )
    _add_current_week_with_hard_session(db, plan)
    _log_readiness(db, plan, sleep_hours=5, soreness=5, energy=1)

    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)
    assert nudge["kind"] == "low_readiness"
