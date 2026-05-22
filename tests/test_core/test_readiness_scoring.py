"""Tests for readiness component scoring helpers."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.runner.fitness import readiness_scoring as rs
from app.models import Base, DailyWorkout, RunLog, TrainingPlan, User, WeeklyPlan


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


class TestPureScorers:
    def test_parse_float(self):
        assert rs.parse_float("21.1") == 21.1
        assert rs.parse_float(None) == 0.0
        assert rs.parse_float("abc") == 0.0

    def test_score_label_bands(self):
        assert rs.score_label(90) == "Strong"
        assert rs.score_label(70) == "Good"
        assert rs.score_label(50) == "Moderate"
        assert rs.score_label(30) == "Developing"
        assert rs.score_label(10) == "Needs work"

    def test_compute_weekly_volumes(self):
        start = _now().date()
        runs = [
            RunLog(date=_now(), distance_km=5.0),
            RunLog(date=_now() + timedelta(days=8), distance_km=7.0),
            RunLog(date=_now() - timedelta(days=3), distance_km=3.0),  # before start
        ]
        vols = rs.compute_weekly_volumes(runs, start, num_weeks=3)
        assert vols[0] == 5.0
        assert vols[1] == 7.0
        assert vols[2] == 0.0

    def test_score_volume(self):
        assert rs.score_volume([], [], 0)[0] == 50.0
        assert rs.score_volume([], [10], 1)[0] == 50.0  # no actual weeks
        score, detail = rs.score_volume([8.0], [10.0], 1)
        assert 0 < score <= 100
        assert "%" in detail
        assert rs.score_volume([5], [0], 1)[0] == 80.0  # no planned volume

    def test_score_long_run(self):
        # Meets 75% benchmark of a 20 km target → full score.
        assert rs.score_long_run(16.0, 18.0, "20.0")[0] == 100.0
        # Partial.
        partial = rs.score_long_run(7.5, 18.0, "20.0")[0]
        assert 0 < partial < 100

    def test_score_taper_phases(self):
        assert rs.score_taper(0, 0)[0] == 50.0
        assert rs.score_taper(0, 10)[0] == 50.0
        assert rs.score_taper(9, 10)[0] == 95.0  # taper
        assert rs.score_taper(8, 10)[0] == 85.0  # peak
        assert rs.score_taper(5, 10)[0] == 70.0  # build
        assert rs.score_taper(2, 10)[0] == 55.0  # base

    def test_vdot_for_goal_time(self):
        assert rs.vdot_for_goal_time("00:45:00", 10.0) is not None
        assert rs.vdot_for_goal_time("", 10.0) is None
        assert rs.vdot_for_goal_time("00:45:00", 0) is None

    def test_build_scenarios(self):
        assert rs.build_scenarios({}, "10.0") == []
        assert rs.build_scenarios({"current": 45.0}, "0") == []
        scenarios = rs.build_scenarios({"current": 45.0}, "10.0")
        assert len(scenarios) == 4
        assert {s["name"] for s in scenarios} == {
            "Dream",
            "Solid",
            "Tough",
            "Survival",
        }


class TestDbScorers:
    def _plan(self, db, *, weeks=8):
        user = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
        db.add(user)
        db.flush()
        plan = TrainingPlan(
            id=_uid(),
            user_id=user.id,
            current_weekly_km=30,
            target_distance="10.0",
            weeks_duration=weeks,
            start_date=_now() - timedelta(weeks=4),
        )
        db.add(plan)
        db.flush()
        for wk in range(1, weeks + 1):
            wp = WeeklyPlan(
                id=_uid(), training_plan_id=plan.id, week_number=wk, total_km=30
            )
            db.add(wp)
            db.flush()
            for d in (1, 2, 3):
                db.add(
                    DailyWorkout(
                        id=_uid(),
                        weekly_plan_id=wp.id,
                        day_of_week=d,
                        workout_type="easy",
                        distance_km=8.0,
                        baseline_distance_km=8.0,
                    )
                )
        db.commit()
        return user, plan

    def test_score_consistency(self, db):
        user, plan = self._plan(db)
        # Two completed (linked) runs.
        dw_ids = [
            r.id
            for r in db.query(DailyWorkout)
            .join(WeeklyPlan)
            .filter(WeeklyPlan.training_plan_id == plan.id)
            .limit(2)
            .all()
        ]
        runs = []
        for dwid in dw_ids:
            r = RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                daily_workout_id=dwid,
                date=_now(),
                distance_km=8.0,
                duration_minutes=48,
            )
            db.add(r)
            runs.append(r)
        db.commit()

        score, detail = rs.score_consistency(runs, plan.id, db, current_week=4)
        assert 0 < score <= 100
        assert "completed" in detail

    def test_score_consistency_not_started(self, db):
        user, plan = self._plan(db)
        assert rs.score_consistency([], plan.id, db, current_week=0)[0] == 50.0

    def test_score_vdot_no_data(self, db):
        user, plan = self._plan(db)
        score, detail, preds, info = rs.score_vdot(user.id, "10.0", db)
        assert score == 50.0
        assert info["current"] is None

    def test_score_vdot_with_data_and_goal(self, db):
        user, plan = self._plan(db)
        for i in range(5):
            db.add(
                RunLog(
                    id=_uid(),
                    user_id=user.id,
                    training_plan_id=plan.id,
                    date=_now() - timedelta(days=10 - i),
                    distance_km=10.0,
                    duration_minutes=48,
                    vdot=47,
                    workout_type="tempo",
                    perceived_effort=8,
                )
            )
        db.commit()
        score, detail, preds, info = rs.score_vdot(
            user.id, "10.0", db, goal_time="00:45:00"
        )
        assert score > 0
        assert info["current"] is not None
        assert info["needed_for_goal"] is not None
