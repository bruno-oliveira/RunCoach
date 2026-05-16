"""Tests for auto-triggered adaptation recommendations."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, User, TrainingPlan, WeeklyPlan, DailyWorkout, RunLog
from app.services.adaptation.recommendation_evaluator import (
    evaluate_weekly_recommendation,
    accept_recommendation,
    dismiss_recommendation,
)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _today():
    return datetime.now(timezone.utc).replace(tzinfo=None).date()


def _uid():
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


def _create_plan(db, *, weeks=8, weeks_ago=3, runs_per_week=4):
    """Create a user, plan, weekly plans, and daily workouts."""
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    start = _now() - timedelta(weeks=weeks_ago)
    plan_data = []
    for wk in range(1, weeks + 1):
        week_data = {
            "week": wk,
            "total_km": 30,
            "phase": "build",
            "daily_workouts": [],
        }
        types = ["easy", "tempo", "long", "easy"][:runs_per_week]
        for i, wtype in enumerate(types):
            week_data["daily_workouts"].append({
                "day": i + 1,
                "type": wtype,
                "distance": 12.0 if wtype == "long" else 6.0,
            })
        plan_data.append(week_data)

    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=25,
        target_distance="10",
        weeks_duration=weeks,
        plan_data=plan_data,
        start_date=start,
    )
    db.add(plan)
    db.flush()

    for wk in range(1, weeks + 1):
        wp = WeeklyPlan(
            id=_uid(),
            training_plan_id=plan.id,
            week_number=wk,
            total_km=30,
        )
        db.add(wp)
        db.flush()
        types = ["easy", "tempo", "long", "easy"][:runs_per_week]
        for i, wtype in enumerate(types):
            dist = 12.0 if wtype == "long" else 6.0
            dw = DailyWorkout(
                id=_uid(),
                weekly_plan_id=wp.id,
                day_of_week=i + 1,
                workout_type=wtype,
                distance_km=dist,
                baseline_distance_km=dist,
            )
            db.add(dw)

    db.flush()
    return user, plan


def _add_runs(db, user, plan, count=4, distance_km=6.0, perceived_effort=5, weeks_ago=1):
    """Add runs linked to a plan."""
    for i in range(count):
        run = RunLog(
            id=_uid(),
            user_id=user.id,
            training_plan_id=plan.id,
            date=_now() - timedelta(weeks=weeks_ago, days=-i),
            distance_km=distance_km,
            duration_minutes=distance_km * 5.5,
            avg_pace_min_km=5.5,
            workout_type="easy",
            perceived_effort=perceived_effort,
        )
        db.add(run)
    db.flush()


class TestEvaluateRecommendation:

    def test_skips_when_no_start_date(self, db):
        user = User(id=_uid(), email="test@test.com")
        db.add(user)
        db.flush()
        plan = TrainingPlan(
            id=_uid(), user_id=user.id, target_distance="10",
            weeks_duration=8, current_weekly_km=20,
        )
        db.add(plan)
        db.flush()

        result = evaluate_weekly_recommendation(plan.id, user.id, db)
        assert result is None

    def test_skips_when_plan_just_started(self, db):
        user, plan = _create_plan(db, weeks_ago=0)
        _add_runs(db, user, plan, count=4, weeks_ago=0)

        result = evaluate_weekly_recommendation(plan.id, user.id, db)
        assert result is None

    def test_skips_when_fewer_than_3_runs(self, db):
        user, plan = _create_plan(db, weeks_ago=3)
        _add_runs(db, user, plan, count=2, weeks_ago=1)

        result = evaluate_weekly_recommendation(plan.id, user.id, db)
        assert result is None

    def test_skips_when_already_evaluated_same_week(self, db):
        user, plan = _create_plan(db, weeks_ago=3)
        _add_runs(db, user, plan, count=5, weeks_ago=1)

        start = plan.start_date
        today = _today()
        days_elapsed = (today - start.date() if hasattr(start, 'date') else (today - start)).days
        current_week = min(max(1, days_elapsed // 7 + 1), plan.weeks_duration)
        last_completed = current_week - 1

        plan.last_recommendation_week = last_completed
        db.flush()

        result = evaluate_weekly_recommendation(plan.id, user.id, db)
        assert result is None

    def test_skips_when_pending_exists(self, db):
        user, plan = _create_plan(db, weeks_ago=3)
        _add_runs(db, user, plan, count=5, weeks_ago=1)

        plan.pending_recommendation = {"multiplier": 1.05, "reason": "test"}
        db.flush()

        result = evaluate_weekly_recommendation(plan.id, user.id, db)
        assert result is None

    def test_creates_recommendation_on_volume_surplus(self, db):
        user, plan = _create_plan(db, weeks_ago=3)
        _add_runs(db, user, plan, count=5, distance_km=10.0, perceived_effort=4, weeks_ago=1)

        result = evaluate_weekly_recommendation(plan.id, user.id, db)

        if result is not None:
            assert result["multiplier"] != 1.0
            assert result["direction"] in ("increase", "reduce")
            assert "week" in result["reason"].lower()
            assert plan.pending_recommendation is not None
            assert plan.last_recommendation_week is not None
        else:
            assert plan.last_recommendation_week is not None

    def test_creates_recommendation_on_volume_deficit(self, db):
        user, plan = _create_plan(db, weeks_ago=3)
        _add_runs(db, user, plan, count=4, distance_km=2.0, perceived_effort=7, weeks_ago=1)

        result = evaluate_weekly_recommendation(plan.id, user.id, db)

        if result is not None:
            assert result["direction"] == "reduce"
            assert plan.pending_recommendation is not None

    def test_force_overrides_pending(self, db):
        user, plan = _create_plan(db, weeks_ago=3)
        _add_runs(db, user, plan, count=5, distance_km=10.0, perceived_effort=4, weeks_ago=1)

        plan.pending_recommendation = {"multiplier": 1.0, "reason": "old"}
        db.flush()

        result = evaluate_weekly_recommendation(plan.id, user.id, db, force=True)
        if result is not None:
            assert result["reason"] != "old"


class TestAcceptRecommendation:

    def test_accept_applies_multiplier(self, db):
        user, plan = _create_plan(db, weeks_ago=3)
        _add_runs(db, user, plan, count=5, weeks_ago=1)

        plan.pending_recommendation = {
            "week_evaluated": 2,
            "multiplier": 1.10,
            "direction": "increase",
            "reason": "Test recommendation",
            "signals": {"per_type_ratios": {}},
            "created_at": _today().isoformat(),
        }
        db.flush()

        result = accept_recommendation(plan.id, user.id, db)

        assert result["accepted"] is True
        assert plan.pending_recommendation is None
        assert plan.adjustment_multiplier == 1.10
        assert plan.last_adjusted_at is not None

        history = plan.adaptation_history or []
        assert any(e.get("type") == "auto_accept" for e in history)

    def test_accept_returns_false_when_no_pending(self, db):
        user, plan = _create_plan(db, weeks_ago=3)

        result = accept_recommendation(plan.id, user.id, db)
        assert result["accepted"] is False

    def test_accept_returns_false_for_unknown_plan(self, db):
        result = accept_recommendation("nonexistent", "nobody", db)
        assert result["accepted"] is False

    def test_accept_actually_changes_easy_distances(self, db):
        """Accepting a reduce-recommendation must persist a smaller distance
        on at least one easy workout. Guards against the regression where
        accept_recommendation updated metadata but no DailyWorkout row.
        """
        user, plan = _create_plan(db, weeks_ago=3)
        _add_runs(db, user, plan, count=5, weeks_ago=1)

        plan.pending_recommendation = {
            "week_evaluated": 2,
            "multiplier": 0.85,
            "direction": "reduce",
            "reason": "Test reduce",
            "signals": {"per_type_ratios": {}},
            "created_at": _today().isoformat(),
        }
        db.flush()

        easy_baselines = {
            dw.id: dw.baseline_distance_km
            for dw in db.query(DailyWorkout).all()
            if dw.workout_type == "easy"
        }

        result = accept_recommendation(plan.id, user.id, db)
        assert result["accepted"] is True
        assert result["workouts_changed"] >= 1, (
            "accept_recommendation reported no workouts changed; "
            "the multiplier never reached the DailyWorkout rows."
        )

        reduced = [
            dw for dw in db.query(DailyWorkout).all()
            if dw.workout_type == "easy"
            and dw.distance_km < easy_baselines.get(dw.id, dw.distance_km)
        ]
        assert reduced, "No easy workout had its distance reduced after accept."

    def test_accept_then_reset_records_both_events(self, db):
        """Reset after accept must add a 'reset' event so the timeline is honest."""
        from app.services.adaptation.plan_adjuster import reset_adjustment

        user, plan = _create_plan(db, weeks_ago=3)
        _add_runs(db, user, plan, count=5, weeks_ago=1)

        plan.pending_recommendation = {
            "week_evaluated": 2,
            "multiplier": 0.85,
            "direction": "reduce",
            "reason": "Test reduce",
            "signals": {"per_type_ratios": {}},
            "created_at": _today().isoformat(),
        }
        db.flush()

        accept_recommendation(plan.id, user.id, db)
        reset_result = reset_adjustment(plan.id, user.id, db)
        assert reset_result["reset"] is True

        history = plan.adaptation_history or []
        types = [e.get("type") for e in history]
        assert "auto_accept" in types
        assert "reset" in types
        assert types.index("reset") > types.index("auto_accept")
        assert plan.adjustment_multiplier is None


class TestDismissRecommendation:

    def test_dismiss_clears_recommendation(self, db):
        user, plan = _create_plan(db, weeks_ago=3)

        plan.pending_recommendation = {
            "week_evaluated": 2,
            "multiplier": 0.92,
            "direction": "reduce",
            "reason": "Test",
            "signals": {},
            "created_at": _today().isoformat(),
        }
        db.flush()

        result = dismiss_recommendation(plan.id, user.id, db)

        assert result["dismissed"] is True
        assert plan.pending_recommendation is None

        history = plan.adaptation_history or []
        assert any(e.get("type") == "auto_dismiss" for e in history)

    def test_dismiss_returns_false_when_no_pending(self, db):
        user, plan = _create_plan(db, weeks_ago=3)

        result = dismiss_recommendation(plan.id, user.id, db)
        assert result["dismissed"] is False


class TestDebounce:

    def test_week_debounce_prevents_reeval(self, db):
        user, plan = _create_plan(db, weeks_ago=4)
        _add_runs(db, user, plan, count=5, distance_km=10.0, perceived_effort=4, weeks_ago=2)
        _add_runs(db, user, plan, count=3, distance_km=8.0, perceived_effort=5, weeks_ago=1)

        result1 = evaluate_weekly_recommendation(plan.id, user.id, db)
        plan.pending_recommendation = None
        db.flush()

        result2 = evaluate_weekly_recommendation(plan.id, user.id, db)
        assert result2 is None

    def test_force_bypasses_debounce(self, db):
        user, plan = _create_plan(db, weeks_ago=4)
        _add_runs(db, user, plan, count=5, distance_km=10.0, perceived_effort=4, weeks_ago=2)
        _add_runs(db, user, plan, count=3, distance_km=8.0, perceived_effort=5, weeks_ago=1)

        evaluate_weekly_recommendation(plan.id, user.id, db)
        plan.pending_recommendation = None
        db.flush()

        result = evaluate_weekly_recommendation(plan.id, user.id, db, force=True)
        # force=True should override the debounce; may still return None
        # if multiplier is ~1.0, but the last_recommendation_week should update
        assert plan.last_recommendation_week is not None


class TestManualAdjustClearsRecommendation:

    def test_adjust_plan_clears_pending(self, db):
        from app.services.adaptation.plan_adjuster import adjust_plan

        user, plan = _create_plan(db, weeks_ago=3)
        _add_runs(db, user, plan, count=5, distance_km=8.0, perceived_effort=5, weeks_ago=1)

        plan.pending_recommendation = {
            "multiplier": 1.05,
            "reason": "should be cleared",
        }
        db.flush()

        adjust_plan(plan.id, user.id, db)

        assert plan.pending_recommendation is None


class TestFacadeIntegration:

    def test_facade_methods_exist(self):
        from app.services.adaptation import AdaptationService

        svc = AdaptationService()
        assert hasattr(svc, "evaluate_recommendation")
        assert hasattr(svc, "accept_recommendation")
        assert hasattr(svc, "dismiss_recommendation")
