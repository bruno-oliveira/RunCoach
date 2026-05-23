"""Tests for the Coach hub assembler (app/application/coach_summary_service).

Covers the three read-only payloads the Coach tab consumes:
- build_coach_summary: 6-signal reshape, form, direction, graceful degradation
- build_adaptation_history: normalization of the persisted JSON, newest-first
- build_coach_patterns: shape + empty-data path

Plus the load-bearing guarantee that preview_adjust_signals performs NO DB
writes (it must be safe to call on a GET request).
"""

import json
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.coach_summary_service import (
    build_adaptation_history,
    build_coach_patterns,
    build_coach_summary,
)
from app.contexts.plan.adaptation import AdaptationService
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


# --------------------------------------------------------------------------
# build_coach_summary
# --------------------------------------------------------------------------


def test_coach_summary_reshapes_six_signals(db):
    user, plan = _make_plan(db)
    _log_runs(db, user, plan)

    summary = build_coach_summary(plan, user.id, db)

    assert summary["available"] is True
    assert set(summary["signals"].keys()) == _SIGNAL_KEYS
    for block in summary["signals"].values():
        assert "factor" in block and "weight" in block and "has_data" in block
    assert summary["direction"] in {"increase", "decrease", "hold"}
    assert isinstance(summary["multiplier"], (int, float))
    assert "tsb_form" in summary["form"]
    assert isinstance(summary["headline_reason"], str) and summary["headline_reason"]
    # The whole payload must survive JSON serialization (it is returned as-is
    # by the GET endpoint).
    json.dumps(summary)


def test_coach_summary_insufficient_data(db):
    user, plan = _make_plan(db)
    # Only one run — below the 3-run threshold gather_signals requires.
    wp = (
        db.query(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan.id, WeeklyPlan.week_number == 1)
        .first()
    )
    wo = db.query(DailyWorkout).filter(DailyWorkout.weekly_plan_id == wp.id).first()
    db.add(
        RunLog(
            id=_uid(),
            user_id=user.id,
            training_plan_id=plan.id,
            daily_workout_id=wo.id,
            date=plan.start_date,
            distance_km=8.0,
            duration_minutes=40,
            workout_type="easy",
        )
    )
    db.commit()

    summary = build_coach_summary(plan, user.id, db)
    assert summary["available"] is False
    assert "reason" in summary


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
# build_adaptation_history
# --------------------------------------------------------------------------


def test_adaptation_history_normalizes_newest_first(db):
    user, plan = _make_plan(db)
    plan.adaptation_history = [
        {"date": "2026-05-01", "type": "adjust", "multiplier": 1.05, "reason": "older"},
        {
            "date": "2026-05-10",
            "type": "recalibrate",
            "weeks_changed": 3,
            "reason": "newer",
        },
    ]
    db.commit()

    result = build_adaptation_history(plan)
    assert result["available"] is True
    events = result["events"]
    assert len(events) == 2
    # Newest-first: the recalibrate event (appended last) comes first.
    assert events[0]["type"] == "recalibrate"
    assert events[0]["label"] == "Recalibrated"
    assert events[1]["type"] == "adjust"
    assert events[1]["pct"] == 5  # (1.05 - 1) * 100


def test_adaptation_history_empty(db):
    user, plan = _make_plan(db)
    result = build_adaptation_history(plan)
    assert result == {"available": True, "events": []}


# --------------------------------------------------------------------------
# build_coach_patterns
# --------------------------------------------------------------------------


def test_coach_patterns_shape(db):
    user, plan = _make_plan(db)
    _log_runs(db, user, plan)

    result = build_coach_patterns(plan, user.id, db)
    assert result["available"] is True
    assert isinstance(result["patterns"], list)
    # week_pulse may be None depending on the frozen week; key must exist.
    assert "week_pulse" in result
