"""Tests for P1 §3.3 — per-run VDOT recalibration gating + WeeklyPlan timestamp."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation.vdot_recalibrator import (
    check_vdot_recalibration,
    recalibrate_zones_only,
)
from app.contexts.runner.enrichment.run_enrichment_service import (
    _maybe_recalibrate_plan_zones,
)
from app.models import (
    Base,
    DailyWorkout,
    RunLog,
    TrainingPlan,
    User,
    WeeklyPlan,
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


def _make_plan(db, vdot=50.0):
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="21.1",
        weeks_duration=8,
        vdot=vdot,
        start_date=_now() - timedelta(weeks=2),
        plan_data=[
            {
                "week": wk,
                "total_km": 30,
                "phase": "build",
                "daily_workouts": [
                    {
                        "day": 1,
                        "type": "tempo",
                        "distance": 8.0,
                        "zone": "zone_3",
                        "target_pace": 5.0,
                    }
                ],
            }
            for wk in range(1, 9)
        ],
    )
    db.add(plan)
    db.flush()

    for wk in range(1, 9):
        wp = WeeklyPlan(
            id=_uid(), training_plan_id=plan.id, week_number=wk, total_km=30
        )
        db.add(wp)
        db.flush()
        db.add(
            DailyWorkout(
                id=_uid(),
                weekly_plan_id=wp.id,
                day_of_week=1,
                workout_type="tempo",
                distance_km=8.0,
                baseline_distance_km=8.0,
            )
        )
    db.commit()
    return user, plan


class TestRecalibrationGating:
    def test_returns_none_for_easy_run(self, db):
        user, plan = _make_plan(db)
        run = RunLog(
            id=_uid(),
            user_id=user.id,
            training_plan_id=plan.id,
            workout_type="easy",
            distance_km=10.0,
            duration_minutes=55.0,
        )
        result = _maybe_recalibrate_plan_zones(run, user.id, db)
        assert result is None

    def test_returns_none_for_recovery_run(self, db):
        user, plan = _make_plan(db)
        run = RunLog(
            id=_uid(),
            user_id=user.id,
            training_plan_id=plan.id,
            workout_type="recovery",
            distance_km=5.0,
            duration_minutes=30.0,
        )
        result = _maybe_recalibrate_plan_zones(run, user.id, db)
        assert result is None

    def test_returns_none_when_no_plan(self, db):
        user, _ = _make_plan(db)
        run = RunLog(
            id=_uid(),
            user_id=user.id,
            training_plan_id=None,
            workout_type="tempo",
            distance_km=10.0,
            duration_minutes=45.0,
        )
        result = _maybe_recalibrate_plan_zones(run, user.id, db)
        assert result is None

    def test_calls_recalibrator_for_tempo(self, db):
        user, plan = _make_plan(db)
        run = RunLog(
            id=_uid(),
            user_id=user.id,
            training_plan_id=plan.id,
            workout_type="tempo",
            distance_km=10.0,
            duration_minutes=45.0,
        )
        with patch(
            "app.contexts.plan.adaptation.vdot_recalibrator.recalibrate_zones_only",
            return_value={"recalibrated": True, "old_vdot": 50.0, "new_vdot": 52.0},
        ) as mock_recal:
            result = _maybe_recalibrate_plan_zones(run, user.id, db)
            mock_recal.assert_called_once()
            assert result == {"recalibrated": True, "old_vdot": 50.0, "new_vdot": 52.0}

    def test_calls_recalibrator_for_race_effort_class(self, db):
        user, plan = _make_plan(db)
        run = RunLog(
            id=_uid(),
            user_id=user.id,
            training_plan_id=plan.id,
            workout_type="easy",
            effort_class="race_effort",
            distance_km=10.0,
            duration_minutes=45.0,
        )
        with patch(
            "app.contexts.plan.adaptation.vdot_recalibrator.recalibrate_zones_only",
            return_value={"recalibrated": True, "old_vdot": 50.0, "new_vdot": 52.0},
        ) as mock_recal:
            result = _maybe_recalibrate_plan_zones(run, user.id, db)
            mock_recal.assert_called_once()
            assert result is not None


class TestRecalibrationStampsWeeklyPlans:
    def test_updates_pace_zones_updated_at_on_future_weeks(self, db):
        user, plan = _make_plan(db, vdot=50.0)

        with patch(
            "app.contexts.runner.fitness.race_predictor_service.RacePredictorService.get_best_recent_vdot",
            return_value=53.0,
        ):
            result = recalibrate_zones_only(plan, user.id, db)

        assert result is not None
        assert result["new_vdot"] == 53.0
        assert result["pace_updates"] > 0
        assert result.get("weekly_plans_updated", 0) > 0

        # All future weeks should have pace_zones_updated_at set
        all_weeks = (
            db.query(WeeklyPlan).filter(WeeklyPlan.training_plan_id == plan.id).all()
        )
        future_weeks = [w for w in all_weeks if w.pace_zones_updated_at is not None]
        assert len(future_weeks) >= 1


class TestBackwardsCompatibleAlias:
    def test_check_vdot_recalibration_delegates(self, db):
        user, plan = _make_plan(db, vdot=50.0)
        with patch(
            "app.contexts.runner.fitness.race_predictor_service.RacePredictorService.get_best_recent_vdot",
            return_value=50.2,  # delta < threshold
        ):
            result = check_vdot_recalibration(plan, user.id, db)
        # delta < 1.0 → no recalibration
        assert result is None
