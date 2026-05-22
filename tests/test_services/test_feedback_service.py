"""Tests for FeedbackService aggregation and weekly summaries."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.runner.fitness.feedback_service import (
    FeedbackService,
    _build_week_summary,
)
from app.models import Base, RunFeedback, RunLog, TrainingPlan, User, WeeklyPlan


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


def _data(**kw):
    base = {
        "sentiments": [],
        "pace_texts": [],
        "hr_texts": [],
        "effort_texts": [],
        "volume_texts": [],
        "pattern_texts": [],
        "run_count": 0,
    }
    base.update(kw)
    return base


class TestBuildWeekSummary:
    def test_warning_dominant_with_fast_pace(self):
        data = _data(
            sentiments=["warning", "warning", "info"],
            pace_texts=["Too fast for easy", "Way too fast today"],
            run_count=3,
        )
        summary = _build_week_summary(data, 1)
        assert summary["sentiment"] == "warning"
        assert "too fast" in summary["summary"].lower()

    def test_positive_dominant_default_highlight(self):
        data = _data(sentiments=["positive", "positive"], run_count=2)
        summary = _build_week_summary(data, 2)
        assert summary["sentiment"] == "positive"
        assert "Solid week" in summary["summary"]

    def test_slow_pace_highlight(self):
        data = _data(
            sentiments=["info", "info"],
            pace_texts=["A bit slow", "slower than planned"],
            run_count=2,
        )
        summary = _build_week_summary(data, 1)
        assert "slower than planned" in summary["summary"]

    def test_hard_effort_highlight(self):
        data = _data(
            sentiments=["warning"],
            effort_texts=["Felt too hard", "too hard again"],
            run_count=2,
        )
        summary = _build_week_summary(data, 1)
        assert "Effort consistently high" in summary["summary"]

    def test_volume_behind_highlight(self):
        data = _data(
            sentiments=["info"],
            volume_texts=["behind plan", "short this week"],
            run_count=2,
        )
        summary = _build_week_summary(data, 1)
        assert "falling behind" in summary["summary"]

    def test_pattern_text_appended(self):
        data = _data(
            sentiments=["info"],
            pattern_texts=["Pattern: easy runs too fast"],
            run_count=1,
        )
        summary = _build_week_summary(data, 1)
        assert "Pattern" in summary["summary"]

    def test_returns_none_when_nothing_notable(self):
        data = _data(sentiments=["info"], run_count=1)
        assert _build_week_summary(data, 1) is None


class TestDbRetrieval:
    def _plan_and_runs(self, db):
        user = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
        db.add(user)
        db.flush()
        plan = TrainingPlan(
            id=_uid(),
            user_id=user.id,
            current_weekly_km=30,
            target_distance="10.0",
            weeks_duration=8,
            start_date=_now() - timedelta(weeks=1),
        )
        db.add(plan)
        db.flush()
        db.add(
            WeeklyPlan(id=_uid(), training_plan_id=plan.id, week_number=1, total_km=30)
        )
        runs = []
        for i in range(2):
            r = RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                # Both inside week 1 of the plan (start is 1 week ago).
                date=plan.start_date + timedelta(days=1 + i),
                distance_km=8.0,
                duration_minutes=48,
            )
            db.add(r)
            runs.append(r)
        db.flush()
        return user, plan, runs

    def test_get_feedback_for_run(self, db):
        user, plan, runs = self._plan_and_runs(db)
        fb = RunFeedback(
            run_log_id=runs[0].id,
            user_id=user.id,
            pace_feedback="Nice pace",
            overall_sentiment="positive",
        )
        db.add(fb)
        db.commit()
        found = FeedbackService.get_feedback_for_run(runs[0].id, db)
        assert found is not None and found.pace_feedback == "Nice pace"
        assert FeedbackService.get_feedback_for_run("missing", db) is None

    def test_get_feedback_for_plan(self, db):
        user, plan, runs = self._plan_and_runs(db)
        for r in runs:
            db.add(
                RunFeedback(run_log_id=r.id, user_id=user.id, overall_sentiment="info")
            )
        db.commit()
        result = FeedbackService.get_feedback_for_plan(plan.id, user.id, db)
        assert len(result) == 2
        # Unknown plan → empty.
        assert FeedbackService.get_feedback_for_plan("x", user.id, db) == []

    def test_weekly_feedback_summary(self, db):
        user, plan, runs = self._plan_and_runs(db)
        for r in runs:
            db.add(
                RunFeedback(
                    run_log_id=r.id,
                    user_id=user.id,
                    pace_feedback="Too fast for an easy run",
                    overall_sentiment="warning",
                )
            )
        db.commit()
        summaries = FeedbackService.get_weekly_feedback_summary(plan.id, user.id, db)
        assert 1 in summaries
        assert summaries[1]["run_count"] == 2

    def test_weekly_summary_no_runs(self, db):
        user = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
        db.add(user)
        db.flush()
        plan = TrainingPlan(
            id=_uid(),
            user_id=user.id,
            current_weekly_km=30,
            target_distance="10.0",
            weeks_duration=8,
            start_date=_now(),
        )
        db.add(plan)
        db.commit()
        assert FeedbackService.get_weekly_feedback_summary(plan.id, user.id, db) == {}
