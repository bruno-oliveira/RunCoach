"""The adaptation engine's read-only views of its own signals.

- ``preview_adjust_signals`` must perform NO database writes: it gathers
  signals with ``run_map=False`` so it is safe to call on a GET request.
- ``build_signal_snapshot`` freezes the six signals onto an applied adjust
  event in a JSON-serialisable shape.
"""

import json
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation import AdaptationService
from app.contexts.plan.adaptation.adjustment_results import (
    build_signal_snapshot as _build_signal_snapshot,
)
from app.models import (
    Base,
    DailyWorkout,
    RunLog,
    TrainingPlan,
    User,
    WeeklyPlan,
)

MON = date(2026, 5, 18)  # isoweekday 1
_SIGNAL_KEYS = {"volume", "effort", "completion", "hr_zone", "feedback", "readiness"}


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


@pytest.fixture(autouse=True)
def _freeze_today(monkeypatch):
    """Freeze today across the adaptation modules so scheduling is stable."""

    def fake_today():
        return MON

    for mod in (
        "app.contexts.plan.adaptation._helpers",
        "app.contexts.plan.adaptation.plan_adjuster",
    ):
        monkeypatch.setattr(f"{mod}.today_date", fake_today)


def _make_plan(db: Session, *, current_week: int = 3, weeks: int = 8):
    """Plan whose start_date puts the frozen MON inside `current_week`."""
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    days_elapsed = (current_week - 1) * 7 + (MON.isoweekday() - 1)
    start_date = datetime.combine(
        MON - timedelta(days=days_elapsed), datetime.min.time()
    )

    plan_data = [
        {
            "week": w + 1,
            "total_km": 30.0,
            "phase": "build",
            "daily_workouts": [
                {"day": d, "type": "easy", "distance": 7.5} for d in range(1, 5)
            ],
        }
        for w in range(weeks)
    ]
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=weeks,
        vdot=45.0,
        start_date=start_date,
        plan_data=plan_data,
    )
    db.add(plan)
    db.flush()

    for wk in range(1, weeks + 1):
        wp = WeeklyPlan(
            id=_uid(), training_plan_id=plan.id, week_number=wk, total_km=30.0
        )
        db.add(wp)
        db.flush()
        for day in range(1, 5):
            db.add(
                DailyWorkout(
                    id=_uid(),
                    weekly_plan_id=wp.id,
                    day_of_week=day,
                    workout_type="easy",
                    distance_km=7.5,
                    baseline_distance_km=7.5,
                )
            )
    db.commit()
    return user, plan


def _log_runs(db: Session, user: User, plan: TrainingPlan, weeks=(1, 2)):
    """Log all 4 runs in each given (past) week with elevated load."""
    for week_number in weeks:
        wp = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan.id,
                WeeklyPlan.week_number == week_number,
            )
            .one()
        )
        workouts = (
            db.query(DailyWorkout)
            .filter(DailyWorkout.weekly_plan_id == wp.id)
            .order_by(DailyWorkout.day_of_week)
            .all()
        )
        for wo in workouts:
            run_date = plan.start_date + timedelta(
                weeks=week_number - 1, days=wo.day_of_week - 1
            )
            db.add(
                RunLog(
                    id=_uid(),
                    user_id=user.id,
                    training_plan_id=plan.id,
                    daily_workout_id=wo.id,
                    date=run_date,
                    distance_km=9.0,
                    duration_minutes=45,
                    avg_pace_min_km=5.0,
                    workout_type="easy",
                    perceived_effort=8,
                )
            )
    db.commit()


def test_preview_adjust_signals_performs_no_writes(db):
    user, plan = _make_plan(db)
    _log_runs(db, user, plan)

    revision_before = plan.adaptation_revision
    distances_before = {wo.id: wo.distance_km for wo in db.query(DailyWorkout).all()}

    signals = AdaptationService().preview_adjust_signals(plan.id, user.id, db)
    assert signals is not None
    assert "multiplier" in signals

    db.expire_all()
    plan_after = db.query(TrainingPlan).filter(TrainingPlan.id == plan.id).one()
    assert plan_after.adaptation_revision == revision_before
    distances_after = {wo.id: wo.distance_km for wo in db.query(DailyWorkout).all()}
    assert distances_after == distances_before


# --------------------------------------------------------------------------
# _build_signal_snapshot
# --------------------------------------------------------------------------


def test_build_signal_snapshot_shape():
    signals = {
        "multiplier": 1.08,
        "current_phase": "build",
        "volume_ratio": 1.1,
        "effort_factor": 0.96,
        "completion_factor": 1.05,
        "hr_zone_factor": 1.0,
        "feedback_factor": 1.02,
        "readiness_factor": 0.99,
        "phase_weights": {
            "volume": 0.33,
            "effort": 0.20,
            "completion": 0.16,
            "hr_zone": 0.14,
            "feedback": 0.09,
            "readiness": 0.08,
        },
        "ctl": 42.0,
        "atl": 38.0,
        "tsb": 4.0,
        "tsb_form": "fresh",
    }
    snap = _build_signal_snapshot(signals)
    assert snap["multiplier"] == 1.08
    assert snap["phase"] == "build"
    assert set(snap["signals"].keys()) == _SIGNAL_KEYS
    assert snap["signals"]["volume"] == {"factor": 1.1, "weight": 0.33}
    assert snap["form"]["tsb_form"] == "fresh"
    json.dumps(snap)
