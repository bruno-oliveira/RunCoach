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
    build_readiness_trend,
    build_signal_history,
    build_today,
    build_training_age,
)
from app.contexts.plan.adaptation import AdaptationService
from app.contexts.plan.adaptation.plan_adjuster import _build_signal_snapshot
from app.models import (
    Base,
    DailyWorkout,
    ReadinessLog,
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


# --------------------------------------------------------------------------
# build_today
# --------------------------------------------------------------------------


def _real_today_plan(db, *, current_week=2, weeks=6):
    """Plan whose start_date puts the *real* today inside `current_week`.

    build_today / build_readiness_trend / build_training_age read the stdlib
    date.today() (not the frozen adaptation clock), so these fixtures anchor
    to the real today to stay deterministic on any run date.
    """
    real_today = date.today()
    this_monday = real_today - timedelta(days=real_today.weekday())
    start = this_monday - timedelta(weeks=current_week - 1)

    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    plan_data = [
        {
            "week": w + 1,
            "total_km": 42.0,
            "phase": "build",
            "daily_workouts": [
                {
                    "day": d,
                    "type": "easy",
                    "distance": 6.0,
                    "hr_zone_target": 2,
                    "hr_zone_label": "Zone 2",
                    "duration_min": 36,
                    "description": "Easy run",
                }
                for d in range(1, 8)
            ],
        }
        for w in range(weeks)
    ]
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=42,
        target_distance="21.1",
        weeks_duration=weeks,
        vdot=45.0,
        start_date=datetime.combine(start, datetime.min.time()),
        plan_data=plan_data,
    )
    db.add(plan)
    db.commit()
    return user, plan, this_monday


def test_build_today_shape(db):
    user, plan, this_monday = _real_today_plan(db, current_week=2, weeks=6)
    # Log a run earlier this week (Monday) so the strip shows a "done" day.
    db.add(
        RunLog(
            id=_uid(),
            user_id=user.id,
            training_plan_id=plan.id,
            date=datetime.combine(this_monday, datetime.min.time()),
            distance_km=6.2,
            duration_minutes=36,
            workout_type="easy",
        )
    )
    db.commit()

    today = build_today(plan, user.id, db)
    assert today["available"] is True
    assert today["current_week"] == 2
    assert today["total_weeks"] == 6
    assert today["phase"] == "build"
    assert len(today["week"]) == 7
    # Exactly one day is flagged as today; every day has the strip fields.
    today_days = [d for d in today["week"] if d["is_today"]]
    assert len(today_days) == 1
    for d in today["week"]:
        assert set(d) >= {"day_name", "workout_type", "status", "planned_km"}
    assert today["today"] is not None
    assert today["today"]["workout_type"] == "easy"
    assert today["week_planned_km"] > 0
    json.dumps(today)


def test_build_today_no_start_date(db):
    user, plan = _make_plan(db)
    plan.start_date = None
    db.commit()
    today = build_today(plan, user.id, db)
    assert today["available"] is False
    assert "reason" in today


# --------------------------------------------------------------------------
# _build_signal_snapshot + build_signal_history
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


def test_build_signal_history_reads_snapshots(db):
    user, plan = _make_plan(db)
    plan.adaptation_history = [
        {"date": "2026-05-01", "type": "adjust", "multiplier": 1.04},  # no snapshot
        {
            "date": "2026-05-10",
            "type": "adjust",
            "direction": "increase",
            "multiplier": 1.07,
            "signals_snapshot": {
                "multiplier": 1.07,
                "phase": "build",
                "signals": {"volume": {"factor": 1.08, "weight": 0.33}},
                "form": {"ctl": 40, "atl": 35, "tsb": 5, "tsb_form": "fresh"},
            },
        },
    ]
    db.commit()
    result = build_signal_history(plan)
    assert result["available"] is True
    # Only the event with a snapshot is surfaced; chronological (oldest-first).
    assert len(result["snapshots"]) == 1
    snap = result["snapshots"][0]
    assert snap["multiplier"] == 1.07
    assert snap["direction"] == "increase"
    assert snap["signals"]["volume"]["factor"] == 1.08


def test_build_signal_history_empty(db):
    user, plan = _make_plan(db)
    assert build_signal_history(plan) == {"available": False, "snapshots": []}


# --------------------------------------------------------------------------
# build_readiness_trend
# --------------------------------------------------------------------------


def test_build_readiness_trend(db):
    user, plan = _make_plan(db)
    real_today = date.today()
    for i in range(8):
        db.add(
            ReadinessLog(
                id=_uid(),
                user_id=user.id,
                log_date=real_today - timedelta(days=i),
                sleep=4,
                soreness=2,
                energy=4,
                stress=2,
                score=75 - i,
                status="ready",
            )
        )
    db.commit()

    trend = build_readiness_trend(user.id, db, days=30)
    assert trend["available"] is True
    assert len(trend["logs"]) == 8
    # logs are oldest-first for charting
    assert trend["logs"][0]["date"] <= trend["logs"][-1]["date"]
    assert trend["avg_7d"] is not None
    assert trend["trend"] in {"improving", "declining", "stable"}
    assert set(trend["logs"][0]["components"]) == {
        "sleep",
        "soreness",
        "energy",
        "stress",
    }


def test_build_readiness_trend_empty(db):
    user, plan = _make_plan(db)
    trend = build_readiness_trend(user.id, db)
    assert trend["available"] is False
    assert trend["logs"] == []


# --------------------------------------------------------------------------
# build_training_age
# --------------------------------------------------------------------------


def test_build_training_age(db):
    user, plan = _make_plan(db)
    real_today = date.today()
    this_monday = real_today - timedelta(days=real_today.weekday())
    # 3 consecutive weeks of runs ending this week → streak of 3.
    for wk in range(3):
        wk_monday = this_monday - timedelta(weeks=wk)
        for d in range(3):
            db.add(
                RunLog(
                    id=_uid(),
                    user_id=user.id,
                    training_plan_id=plan.id,
                    date=datetime.combine(
                        wk_monday + timedelta(days=d), datetime.min.time()
                    ),
                    distance_km=8.0,
                    duration_minutes=40,
                    workout_type="easy",
                )
            )
    db.commit()

    age = build_training_age(user.id, db)
    assert age["available"] is True
    assert age["weeks_since_first_run"] >= 3
    assert age["total_runs"] == 9  # 3 runs/week × 3 weeks
    assert age["current_streak_weeks"] == 3
    assert age["longest_streak_weeks"] == 3
    assert age["avg_runs_per_week"] > 0
    json.dumps(age)


def test_build_training_age_empty(db):
    user, plan = _make_plan(db)
    assert build_training_age(user.id, db) == {"available": False}
