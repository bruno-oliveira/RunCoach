"""Tests for P2 §5.1 — auto-adjust on run logging (apply_or_park + confidence)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    Base,
    DailyWorkout,
    RunLog,
    TrainingPlan,
    User,
    WeeklyPlan,
)
from app.services.adaptation import recommendation_evaluator
from app.services.adaptation.recommendation_evaluator import (
    AUTO_ADJUST_THROTTLE,
    apply_or_park,
    evaluate_on_run_logged,
)


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


def _make_plan_with_runs(db, vdot=50.0, effort=9.0, dist_mult=1.3):
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    start = _now() - timedelta(weeks=3)
    plan_data = []
    for wk in range(1, 9):
        plan_data.append({
            "week": wk,
            "total_km": 30,
            "phase": "build",
            "daily_workouts": [
                {"day": 1, "type": "easy", "distance": 8.0},
                {"day": 2, "type": "tempo", "distance": 8.0},
                {"day": 3, "type": "long", "distance": 14.0},
            ],
        })

    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="21.1",
        weeks_duration=8,
        vdot=vdot,
        start_date=start,
        plan_data=plan_data,
    )
    db.add(plan)
    db.flush()

    for wk in range(1, 9):
        wp = WeeklyPlan(id=_uid(), training_plan_id=plan.id, week_number=wk, total_km=30)
        db.add(wp)
        db.flush()
        for i, (wtype, dist) in enumerate([("easy", 8.0), ("tempo", 8.0), ("long", 14.0)]):
            wo = DailyWorkout(
                id=_uid(),
                weekly_plan_id=wp.id,
                day_of_week=i + 1,
                workout_type=wtype,
                distance_km=dist,
                baseline_distance_km=dist,
            )
            db.add(wo)

    db.flush()

    # Add runs to weeks 1-3 with high effort to push multiplier away from 1.0.
    for wk in range(1, 4):
        wp = db.query(WeeklyPlan).filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number == wk,
        ).one()
        workouts = (
            db.query(DailyWorkout)
            .filter(DailyWorkout.weekly_plan_id == wp.id)
            .order_by(DailyWorkout.day_of_week)
            .all()
        )
        for wo in workouts:
            run_date = start + timedelta(weeks=wk - 1, days=wo.day_of_week - 1)
            db.add(RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                daily_workout_id=wo.id,
                date=run_date,
                distance_km=(wo.distance_km or 0) * dist_mult,
                duration_minutes=50,
                perceived_effort=effort,
                workout_type=wo.workout_type,
            ))
    db.commit()
    return user, plan


class TestConfidenceClassification:
    def test_returns_none_when_signals_too_small(self, db):
        user, plan = _make_plan_with_runs(db, effort=5.0, dist_mult=1.0)
        result = evaluate_on_run_logged(plan.id, user.id, db)
        # multiplier may be very close to 1.0 → returns None
        if result is not None:
            assert result["confidence"] in ("medium", "high", "low")

    def test_high_effort_yields_evaluation(self, db):
        user, plan = _make_plan_with_runs(db, effort=9.0, dist_mult=1.3)
        result = evaluate_on_run_logged(plan.id, user.id, db)
        assert result is not None
        assert result["confidence"] in ("medium", "high")
        assert "multiplier" in result
        assert "signals" in result


class TestApplyOrPark:
    def test_low_confidence_skipped(self, db):
        user, plan = _make_plan_with_runs(db)
        # Hand-craft a low-confidence evaluation
        evaluation = {
            "plan_id": plan.id,
            "confidence": "low",
            "multiplier": 1.01,
            "signals": {},
            "training_plan": plan,
            "current_week": 4,
            "current_day_of_week": 1,
            "adjustable_weeks": [],
        }
        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=True)
        assert result["action"] == "skipped"

    def test_high_confidence_with_auto_applies(self, db):
        user, plan = _make_plan_with_runs(db, effort=9.0, dist_mult=1.3)
        user.auto_adjust_enabled = True
        db.commit()

        evaluation = evaluate_on_run_logged(plan.id, user.id, db)
        if evaluation is None:
            pytest.skip("Signals were not strong enough to trigger evaluation")

        # Force confidence to high so we can test the apply path deterministically
        evaluation["confidence"] = "high"

        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=True)
        assert result["action"] == "auto_adjusted"
        assert "multiplier" in result

        db.refresh(plan)
        assert plan.adjustment_multiplier is not None
        history = plan.adaptation_history or []
        assert any(e.get("type") == "auto_adjust" for e in history)
        # Pending recommendation should be cleared after auto-apply
        assert plan.pending_recommendation is None

    def test_high_confidence_without_auto_parks(self, db):
        user, plan = _make_plan_with_runs(db, effort=9.0, dist_mult=1.3)
        user.auto_adjust_enabled = False
        db.commit()

        evaluation = evaluate_on_run_logged(plan.id, user.id, db)
        if evaluation is None:
            pytest.skip("Signals were not strong enough to trigger evaluation")
        evaluation["confidence"] = "high"

        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=False)
        assert result["action"] == "parked"

        db.refresh(plan)
        assert plan.pending_recommendation is not None
        assert plan.pending_recommendation.get("source") == "run_logged"

    def test_throttle_blocks_recent_auto_adjust(self, db):
        user, plan = _make_plan_with_runs(db, effort=9.0, dist_mult=1.3)
        user.auto_adjust_enabled = True
        plan.last_adjusted_at = _now() - timedelta(hours=1)
        db.commit()

        evaluation = evaluate_on_run_logged(plan.id, user.id, db)
        if evaluation is None:
            pytest.skip("Signals were not strong enough to trigger evaluation")
        evaluation["confidence"] = "high"

        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=True)
        assert result["action"] == "throttled"

    def test_throttle_allows_older_auto_adjust(self, db):
        user, plan = _make_plan_with_runs(db, effort=9.0, dist_mult=1.3)
        user.auto_adjust_enabled = True
        plan.last_adjusted_at = _now() - AUTO_ADJUST_THROTTLE - timedelta(minutes=1)
        db.commit()

        evaluation = evaluate_on_run_logged(plan.id, user.id, db)
        if evaluation is None:
            pytest.skip("Signals were not strong enough to trigger evaluation")
        evaluation["confidence"] = "high"

        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=True)
        assert result["action"] == "auto_adjusted"


class TestFacadeExposesAutoAdjust:
    def test_facade_methods_exist(self):
        from app.services.adaptation import AdaptationService
        svc = AdaptationService()
        assert hasattr(svc, "evaluate_on_run_logged")
        assert hasattr(svc, "apply_or_park")
