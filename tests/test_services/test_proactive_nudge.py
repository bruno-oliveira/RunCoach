"""Tests for proactive, suggest-only adaptation nudges (proactive_nudge).

The detector is layered over the read-only signal engine. These tests stub
``gather_signals`` so they exercise the *nudge decision* (thresholds, safety,
suppression, dismissal) without standing up the full run→signal pipeline.
"""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation import proactive_nudge
from app.models import Base, DailyWorkout, TrainingPlan, User, WeeklyPlan

TODAY = date(2026, 6, 19)


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
        start_date=datetime.combine(TODAY - timedelta(days=14), datetime.min.time()),
    )
    db.add(tp)
    db.commit()
    return tp


def _gathered(*, current_week=3, current_day_of_week=3, **signal_overrides):
    """A gathered-signals payload with one adjustable (future) week by default.

    Defaults describe a clear fitness jump; pass signal overrides to flip the
    scenario. ``current_day_of_week`` mirrors what gather_signals supplies so
    the current-week-remaining lookup behaves.
    """
    signals = {
        "multiplier": 1.06,
        "overreach_detected": False,
        "completion_rate": 0.9,
        "vdot_trend": "improving",
        "avg_zone_deviation": -0.7,
    }
    signals.update(signal_overrides)
    return {
        "signals": signals,
        "current_week": current_week,
        "current_day_of_week": current_day_of_week,
        "adjustable_weeks": [WeeklyPlan(week_number=current_week + 1)],
    }


def _stub_gather(monkeypatch, gathered):
    monkeypatch.setattr(proactive_nudge, "gather_signals", lambda *a, **k: gathered)


def _add_week(db, plan, week_number, workouts):
    """Persist a WeeklyPlan + DailyWorkouts. ``workouts``: (day, type, km)."""
    wp = WeeklyPlan(id=_uid(), training_plan_id=plan.id, week_number=week_number)
    db.add(wp)
    db.flush()
    for day, wtype, dist in workouts:
        db.add(
            DailyWorkout(
                id=_uid(),
                weekly_plan_id=wp.id,
                day_of_week=day,
                workout_type=wtype,
                distance_km=dist,
            )
        )
    db.commit()


def test_fires_on_clear_fitness_jump(db, plan, freeze_today, monkeypatch):
    _stub_gather(monkeypatch, _gathered())
    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)
    assert nudge is not None
    assert nudge["kind"] == "fitness_jump"
    assert nudge["intent"] == "feeling_strong"
    assert nudge["signature"]


def test_fires_on_hr_drift_alone(db, plan, freeze_today, monkeypatch):
    # VDOT flat, but easy runs are coming in well below their zones.
    _stub_gather(monkeypatch, _gathered(vdot_trend="stable", avg_zone_deviation=-0.8))
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is not None


def test_fires_on_vdot_alone(db, plan, freeze_today, monkeypatch):
    # No HR data (deviation ~0) but VDOT clearly improving.
    _stub_gather(monkeypatch, _gathered(vdot_trend="improving", avg_zone_deviation=0.0))
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is not None


def test_silent_on_overreach(db, plan, freeze_today, monkeypatch):
    # Even with a fit-looking trend, an overreach flag must never push harder.
    _stub_gather(monkeypatch, _gathered(overreach_detected=True))
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is None


def test_silent_when_multiplier_too_low(db, plan, freeze_today, monkeypatch):
    _stub_gather(monkeypatch, _gathered(multiplier=1.01))
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is None


def test_silent_when_completion_low(db, plan, freeze_today, monkeypatch):
    # Don't tell someone skipping sessions to add volume.
    _stub_gather(monkeypatch, _gathered(completion_rate=0.4))
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is None


def test_silent_without_signal(db, plan, freeze_today, monkeypatch):
    _stub_gather(monkeypatch, _gathered(vdot_trend="stable", avg_zone_deviation=0.0))
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is None


def test_silent_when_no_adjustable_weeks(db, plan, freeze_today, monkeypatch):
    g = _gathered()
    g["adjustable_weeks"] = []
    _stub_gather(monkeypatch, g)
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is None


def test_dismissed_signature_suppresses(db, plan, freeze_today, monkeypatch):
    _stub_gather(monkeypatch, _gathered())
    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)
    assert nudge is not None

    proactive_nudge.dismiss_nudge(plan.id, plan.user_id, nudge["signature"], db)
    db.expire_all()

    # Same situation → same signature → stays quiet.
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is None


def test_changed_signature_resurfaces_after_dismiss(
    db, plan, freeze_today, monkeypatch
):
    _stub_gather(monkeypatch, _gathered())
    first = proactive_nudge.get_nudge(plan.id, plan.user_id, db)
    proactive_nudge.dismiss_nudge(plan.id, plan.user_id, first["signature"], db)
    db.expire_all()

    # Situation moves on (different week) → new signature → surfaces again.
    _stub_gather(monkeypatch, {**_gathered(), "current_week": 5})
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is not None


def test_recent_strong_bump_suppresses(db, plan, freeze_today, monkeypatch):
    plan.adaptation_history = [
        {
            "type": "intent",
            "intent": "feeling_strong",
            "date": (TODAY - timedelta(days=2)).isoformat(),
        }
    ]
    db.commit()
    _stub_gather(monkeypatch, _gathered())
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is None


def test_old_strong_bump_does_not_suppress(db, plan, freeze_today, monkeypatch):
    plan.adaptation_history = [
        {
            "type": "intent",
            "intent": "feeling_strong",
            "date": (TODAY - timedelta(days=30)).isoformat(),
        }
    ]
    db.commit()
    _stub_gather(monkeypatch, _gathered())
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is not None


# --- Overtraining guard ------------------------------------------------------


def test_overtraining_fires_on_overreach(db, plan, freeze_today, monkeypatch):
    _add_week(db, plan, 3, [(4, "easy", 8.0)])
    _stub_gather(monkeypatch, _gathered(overreach_detected=True))
    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)
    assert nudge is not None
    assert nudge["kind"] == "overtraining"
    assert nudge["intent"] == "feeling_tired"
    assert nudge["tone"] == "caution"


def test_overtraining_fires_on_hot_hr_with_engine_reduction(
    db, plan, freeze_today, monkeypatch
):
    _add_week(db, plan, 3, [(4, "easy", 8.0)])
    _stub_gather(
        monkeypatch,
        _gathered(
            overreach_detected=False,
            avg_zone_deviation=0.8,  # running above zones
            multiplier=0.94,  # engine corroborates a reduction
            vdot_trend="stable",
        ),
    )
    assert (
        proactive_nudge.get_nudge(plan.id, plan.user_id, db)["kind"] == "overtraining"
    )


def test_hot_hr_without_engine_reduction_stays_silent(
    db, plan, freeze_today, monkeypatch
):
    # HR drifting hot but the engine isn't recommending a cut — no corroboration.
    _add_week(db, plan, 3, [(4, "easy", 8.0)])
    _stub_gather(
        monkeypatch,
        _gathered(avg_zone_deviation=0.8, multiplier=1.0, vdot_trend="stable"),
    )
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is None


def test_overtraining_silent_without_remaining_workouts(
    db, plan, freeze_today, monkeypatch
):
    # Overreach flagged but nothing left this week for feeling_tired to ease.
    _stub_gather(monkeypatch, _gathered(overreach_detected=True))
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is None


def test_recent_tired_suppresses_overtraining(db, plan, freeze_today, monkeypatch):
    _add_week(db, plan, 3, [(4, "easy", 8.0)])
    plan.adaptation_history = [
        {
            "type": "intent",
            "intent": "feeling_tired",
            "date": (TODAY - timedelta(days=2)).isoformat(),
        }
    ]
    db.commit()
    _stub_gather(monkeypatch, _gathered(overreach_detected=True))
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is None


# --- Missed-session reshape --------------------------------------------------


def test_missed_session_fires_with_hard_session_ahead(
    db, plan, freeze_today, monkeypatch
):
    _add_week(db, plan, 3, [(4, "interval", 8.0)])
    _stub_gather(
        monkeypatch,
        _gathered(
            completion_rate=0.45,  # recent skipping
            vdot_trend="stable",
            avg_zone_deviation=0.0,
            multiplier=1.0,
        ),
    )
    nudge = proactive_nudge.get_nudge(plan.id, plan.user_id, db)
    assert nudge is not None
    assert nudge["kind"] == "missed_session"
    assert nudge["intent"] == "feeling_tired"


def test_missed_session_silent_without_hard_session(
    db, plan, freeze_today, monkeypatch
):
    # Skipping, but the only thing ahead is an easy run — nothing to soften.
    _add_week(db, plan, 3, [(4, "easy", 8.0)])
    _stub_gather(
        monkeypatch,
        _gathered(
            completion_rate=0.45,
            vdot_trend="stable",
            avg_zone_deviation=0.0,
            multiplier=1.0,
        ),
    )
    assert proactive_nudge.get_nudge(plan.id, plan.user_id, db) is None


def test_overtraining_takes_priority_over_missed_session(
    db, plan, freeze_today, monkeypatch
):
    # Both could be relevant; the safety overtraining guard wins.
    _add_week(db, plan, 3, [(4, "interval", 8.0)])
    _stub_gather(
        monkeypatch,
        _gathered(overreach_detected=True, completion_rate=0.45),
    )
    assert (
        proactive_nudge.get_nudge(plan.id, plan.user_id, db)["kind"] == "overtraining"
    )
