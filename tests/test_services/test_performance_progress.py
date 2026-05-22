"""Tests for performance plan progress / today's-workout logic."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.generators.performance_plan_generator import (
    PerformancePlanGenerator,
)
from app.contexts.runner.fitness.performance_progress import (
    get_plan_progress,
    get_plan_with_data,
    get_todays_workout,
)
from app.models import Base, RunLog, TrainingPlan, User


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


def _plan(db, *, weeks=4, start_offset_days=0, plan_type="performance"):
    user = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
    db.add(user)
    db.flush()
    plan_data = [
        {
            "week": wk,
            "total_km": 30,
            "daily_workouts": [
                {"day": d, "type": "easy", "distance": 6.0} for d in (1, 2, 3, 4)
            ],
        }
        for wk in range(1, weeks + 1)
    ]
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="10.0",
        weeks_duration=weeks,
        plan_type=plan_type,
        goal_pace=5.0,
        max_heart_rate=185,
        start_date=_now() + timedelta(days=start_offset_days),
        plan_data=plan_data,
    )
    db.add(plan)
    db.commit()
    return user, plan


class TestGetTodaysWorkout:
    def test_not_started(self, db):
        _, plan = _plan(db, start_offset_days=5)
        assert get_todays_workout(db, plan)["status"] == "not_started"

    def test_workout_today(self, db):
        _, plan = _plan(db, start_offset_days=0)
        result = get_todays_workout(db, plan)
        assert result["status"] == "workout"
        assert result["week"] == 1
        assert result["already_logged"] is False

    def test_already_logged(self, db):
        user, plan = _plan(db, start_offset_days=0)
        db.add(
            RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                date=_now(),
                distance_km=6.0,
                duration_minutes=36,
            )
        )
        db.commit()
        assert get_todays_workout(db, plan)["already_logged"] is True

    def test_completed_when_past_end(self, db):
        _, plan = _plan(db, weeks=1, start_offset_days=-21)
        assert get_todays_workout(db, plan)["status"] == "completed"


class TestGetPlanProgress:
    def test_progress_metrics(self, db):
        user, plan = _plan(db, weeks=4, start_offset_days=-14)
        # Two runs in week 1, one in week 2.
        start = plan.start_date
        for days, dist in [(0, 6.0), (1, 8.0), (7, 10.0)]:
            db.add(
                RunLog(
                    id=_uid(),
                    user_id=user.id,
                    training_plan_id=plan.id,
                    date=start + timedelta(days=days),
                    distance_km=dist,
                    duration_minutes=int(dist * 6),
                    avg_pace_min_km=6.0,
                )
            )
        db.commit()

        progress = get_plan_progress(db, plan)
        assert progress["completed_count"] == 3
        assert progress["total_km_logged"] == 24.0
        assert len(progress["planned_weekly_km"]) == 4
        assert progress["actual_weekly_km"][0] == 14.0
        assert progress["actual_weekly_km"][1] == 10.0
        assert progress["completion_pct"] > 0
        assert len(progress["pace_by_week"]) == 2


class TestGetPlanWithData:
    def test_returns_full_data_for_performance_plan(self, db):
        _, plan = _plan(db)
        result = get_plan_with_data(db, plan.id, PerformancePlanGenerator())
        assert result is not None
        _, full_data = result
        assert full_data["weeks"] == 4
        assert "training_zones" in full_data
        assert full_data["goal_pace"] == 5.0

    def test_none_for_non_performance_plan(self, db):
        _, plan = _plan(db, plan_type="distance")
        assert get_plan_with_data(db, plan.id, PerformancePlanGenerator()) is None
