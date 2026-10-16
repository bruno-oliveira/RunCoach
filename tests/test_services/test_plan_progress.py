"""Tests for the shared page's plan progress block."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.runner.fitness.plan_progress import get_plan_progress
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


def _plan(db, *, weeks=4, start_offset_days=0):
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
        start_date=_now() + timedelta(days=start_offset_days),
        plan_data=plan_data,
    )
    db.add(plan)
    db.commit()
    return user, plan


class TestGetPlanProgress:
    def test_progress_metrics(self, db):
        # A Monday start, so the runs below land in the weeks they name.
        user, plan = _plan(db, weeks=4, start_offset_days=-14 - _now().weekday())
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
        assert progress["actual_weekly_km"][0] == 14.0
        assert progress["actual_weekly_km"][1] == 10.0
        assert progress["completion_pct"] > 0

    def test_no_start_and_no_creation_date_is_unavailable(self, db):
        _, plan = _plan(db)
        plan.start_date = None
        plan.created_at = None
        assert get_plan_progress(db, plan)["available"] is False
