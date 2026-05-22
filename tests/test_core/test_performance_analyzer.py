"""Tests for performance analysis metrics and recommendations."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation.performance_analyzer import (
    _analyze_effort_trend,
    _calculate_pace_consistency,
    _generate_recommendations,
    analyze_performance,
)
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


class TestEffortTrend:
    def test_insufficient_data(self):
        assert _analyze_effort_trend([5, 6, 7]) == "insufficient_data"

    def test_increasing(self):
        assert _analyze_effort_trend([3, 3, 7, 8]) == "increasing"

    def test_decreasing(self):
        assert _analyze_effort_trend([8, 8, 3, 3]) == "decreasing"

    def test_stable(self):
        assert _analyze_effort_trend([5, 6, 5, 6]) == "stable"


class TestPaceConsistency:
    def test_too_few_points(self):
        assert _calculate_pace_consistency([6.0]) is None

    def test_perfectly_consistent(self):
        assert _calculate_pace_consistency([6.0, 6.0, 6.0]) == 0.0

    def test_variable(self):
        cv = _calculate_pace_consistency([5.0, 6.0, 7.0])
        assert cv is not None and cv > 0


class TestRecommendations:
    def test_low_adherence(self):
        recs = _generate_recommendations(None, "stable", 30.0, None)
        assert any("complete more" in r for r in recs)

    def test_high_adherence(self):
        recs = _generate_recommendations(6.0, "stable", 95.0, None)
        assert any("Excellent adherence" in r for r in recs)

    def test_too_easy_effort(self):
        recs = _generate_recommendations(2.0, "stable", 70.0, None)
        assert any("too easy" in r for r in recs)

    def test_too_hard_effort(self):
        recs = _generate_recommendations(9.5, "stable", 70.0, None)
        assert any("pushing too hard" in r for r in recs)

    def test_optimal_effort(self):
        recs = _generate_recommendations(6.0, "stable", 70.0, None)
        assert any("optimal" in r for r in recs)

    def test_increasing_trend_warns_recovery(self):
        recs = _generate_recommendations(6.0, "increasing", 70.0, None)
        assert any("recovery" in r for r in recs)

    def test_decreasing_trend_positive(self):
        recs = _generate_recommendations(6.0, "decreasing", 70.0, None)
        assert any("adapting well" in r for r in recs)

    def test_consistent_pace_praised(self):
        recs = _generate_recommendations(6.0, "stable", 70.0, 3.0)
        assert any("consistent" in r for r in recs)

    def test_inconsistent_pace_flagged(self):
        recs = _generate_recommendations(6.0, "stable", 70.0, 20.0)
        assert any("consistent pacing" in r for r in recs)

    def test_default_when_nothing_notable(self):
        recs = _generate_recommendations(None, "insufficient_data", 70.0, None)
        assert recs == ["Keep logging runs for personalized insights"]


class TestAnalyzePerformance:
    def test_no_runs(self, db):
        user = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
        db.add(user)
        db.flush()
        plan = TrainingPlan(
            id=_uid(),
            user_id=user.id,
            current_weekly_km=20,
            target_distance="10.0",
            weeks_duration=8,
        )
        db.add(plan)
        db.commit()
        result = analyze_performance(plan.id, db)
        assert result["total_runs"] == 0
        assert result["effort_trend"] == "insufficient_data"
        assert result["recommendations"]

    def test_metrics_with_runs(self, db):
        user = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
        db.add(user)
        plan = TrainingPlan(
            id=_uid(),
            user_id=user.id,
            current_weekly_km=20,
            target_distance="10.0",
            weeks_duration=4,
        )
        db.add(plan)
        db.flush()
        wp = WeeklyPlan(id=_uid(), training_plan_id=plan.id, week_number=1, total_km=20)
        db.add(wp)
        db.flush()
        dw = DailyWorkout(
            id=_uid(),
            weekly_plan_id=wp.id,
            day_of_week=1,
            workout_type="easy",
            distance_km=5.0,
            baseline_distance_km=5.0,
        )
        db.add(dw)
        db.flush()

        for i in range(4):
            db.add(
                RunLog(
                    id=_uid(),
                    user_id=user.id,
                    training_plan_id=plan.id,
                    daily_workout_id=dw.id,
                    date=_now() - timedelta(days=10 - i),
                    distance_km=5.0,
                    duration_minutes=30,
                    perceived_effort=6,
                    avg_pace_min_km=6.0,
                )
            )
        db.commit()

        result = analyze_performance(plan.id, db)
        assert result["total_runs"] == 4
        assert result["avg_effort"] == 6.0
        assert result["adherence_rate"] > 0
        # All runs are the "easy" type with identical pace → CV 0, consistent.
        assert result["pace_consistency"] == 0.0
        assert "easy" in result["pace_consistency_by_type"]
