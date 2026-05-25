"""Tests for the Coach's Note assembler (app/application/coach_narrative_service).

Verifies the fact-pack assembly and the AI/rules source split with a *fake*
narrator — no network. Availability is gated by build_coach_summary (the same
3-linked-runs threshold as the rest of the Coach hub), so we reuse the frozen
adaptation clock + WeeklyPlan/DailyWorkout setup from the coach-summary tests.
"""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.application.coach_narrative_service import build_coach_note
from app.models import Base, DailyWorkout, RunLog, TrainingPlan, User, WeeklyPlan

MON = date(2026, 5, 18)  # isoweekday 1 — matches the coach-summary test clock


def _uid() -> str:
    return str(uuid.uuid4())


class _FakeNarrator:
    """Records the fact pack it was handed and returns a canned note."""

    def __init__(self, note):
        self.note = note
        self.calls: list[dict] = []

    def generate_note(self, context):
        self.calls.append(context)
        return self.note


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
    """Freeze the adaptation clock so build_coach_summary availability is stable."""

    def fake_today():
        return MON

    for mod in (
        "app.contexts.plan.adaptation._helpers",
        "app.contexts.plan.adaptation.plan_adjuster",
    ):
        monkeypatch.setattr(f"{mod}.today_date", fake_today)


def _make_plan(db, *, current_week=3, weeks=8):
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


def _log_runs(db, user, plan, weeks=(1, 2)):
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
                    distance_km=8.0,
                    duration_minutes=42,
                    avg_pace_min_km=5.25,
                    workout_type="easy",
                    perceived_effort=5,
                )
            )
    db.commit()


def test_coach_note_ai_source(db):
    user, plan = _make_plan(db)
    _log_runs(db, user, plan)
    narrator = _FakeNarrator("You're crushing it. Today: easy run.")

    result = build_coach_note(plan, user.id, db, narrator)

    assert result["available"] is True
    assert result["source"] == "ai"
    assert result["note"] == "You're crushing it. Today: easy run."
    assert isinstance(result["recognition"]["chips"], list)
    assert "today" in result
    # The narrator was handed a structured fact pack.
    assert len(narrator.calls) == 1
    ctx = narrator.calls[0]
    assert set(ctx) >= {"today", "training_age", "journey", "stance", "week_pulse"}
    assert "current_streak_weeks" in ctx["training_age"]
    assert "vdot_now" in ctx["journey"]


def test_coach_note_rules_fallback(db):
    user, plan = _make_plan(db)
    _log_runs(db, user, plan)
    narrator = _FakeNarrator(None)  # AI unavailable → deterministic floor

    result = build_coach_note(plan, user.id, db, narrator)

    assert result["available"] is True
    assert result["source"] == "rules"
    assert isinstance(result["note"], str) and result["note"].strip()


def test_coach_note_insufficient_data_skips_narrator(db):
    user, plan = _make_plan(db)
    # One run — below the 3-run gate; the narrator must not be called.
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
            duration_minutes=42,
            workout_type="easy",
        )
    )
    db.commit()
    narrator = _FakeNarrator("should not be used")

    result = build_coach_note(plan, user.id, db, narrator)

    assert result["available"] is False
    assert "reason" in result
    assert narrator.calls == []
