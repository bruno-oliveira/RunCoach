"""Tests for volume_feedback and pattern_feedback coaching helpers."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.runner.fitness.coaching_data import (
    fetch_pattern_candidates,
    fetch_volume_inputs,
)
from app.core.coaching.pattern_analyzer import pattern_feedback
from app.core.coaching.volume_tracker import volume_feedback
from app.models import Base, RunLog, TrainingPlan, User, WeeklyPlan


def _uid():
    return str(uuid.uuid4())


def _volume_msg(run_log, db):
    """Compose the context fetch + pure messaging (mirrors the engine path)."""
    inputs = fetch_volume_inputs(run_log, db)
    return volume_feedback(*inputs) if inputs else None


def _pattern_msg(run_log, db):
    return pattern_feedback(run_log, fetch_pattern_candidates(run_log, db))


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


def _user(db):
    u = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
    db.add(u)
    db.flush()
    return u


def _run(db, user, *, days_ago, wtype, avg, planned, plan_id=None, dist=8.0):
    r = RunLog(
        id=_uid(),
        user_id=user.id,
        training_plan_id=plan_id,
        date=_now() - timedelta(days=days_ago),
        distance_km=dist,
        duration_minutes=int(dist * avg) if avg else 40,
        workout_type=wtype,
        avg_pace_min_km=avg,
        planned_pace_min_km=planned,
    )
    db.add(r)
    db.flush()
    return r


class TestPatternFeedback:
    def test_missing_pace_returns_none(self, db):
        user = _user(db)
        r = _run(db, user, days_ago=0, wtype="easy", avg=None, planned=6.0)
        assert _pattern_msg(r, db) is None

    def test_missing_type_returns_none(self, db):
        user = _user(db)
        r = _run(db, user, days_ago=0, wtype=None, avg=5.5, planned=6.0)
        assert _pattern_msg(r, db) is None

    def test_too_few_recent_returns_none(self, db):
        user = _user(db)
        subject = _run(db, user, days_ago=0, wtype="easy", avg=5.5, planned=6.0)
        _run(db, user, days_ago=2, wtype="easy", avg=5.5, planned=6.0)
        db.commit()
        assert _pattern_msg(subject, db) is None

    def test_easy_runs_consistently_fast(self, db):
        user = _user(db)
        subject = _run(db, user, days_ago=0, wtype="easy", avg=5.5, planned=6.0)
        for d in (2, 4, 6):
            _run(db, user, days_ago=d, wtype="easy", avg=5.4, planned=6.0)
        db.commit()
        msg = _pattern_msg(subject, db)
        assert msg is not None and "faster than planned" in msg

    def test_tempo_runs_consistently_slow(self, db):
        user = _user(db)
        subject = _run(db, user, days_ago=0, wtype="tempo", avg=6.6, planned=6.0)
        for d in (2, 4, 6):
            _run(db, user, days_ago=d, wtype="tempo", avg=6.7, planned=6.0)
        db.commit()
        msg = _pattern_msg(subject, db)
        assert msg is not None and "slower than target" in msg

    def test_on_target_returns_none(self, db):
        user = _user(db)
        subject = _run(db, user, days_ago=0, wtype="easy", avg=6.0, planned=6.0)
        for d in (2, 4, 6):
            _run(db, user, days_ago=d, wtype="easy", avg=6.0, planned=6.0)
        db.commit()
        assert _pattern_msg(subject, db) is None


class TestVolumeFeedback:
    def _plan_with_week(self, db, user, *, planned_km=20.0):
        plan = TrainingPlan(
            id=_uid(),
            user_id=user.id,
            current_weekly_km=20,
            target_distance="10.0",
            weeks_duration=8,
            start_date=_now() - timedelta(days=1),
        )
        db.add(plan)
        db.flush()
        db.add(
            WeeklyPlan(
                id=_uid(),
                training_plan_id=plan.id,
                week_number=1,
                total_km=planned_km,
            )
        )
        db.flush()
        return plan

    def test_no_plan_id_returns_none(self, db):
        user = _user(db)
        r = _run(db, user, days_ago=0, wtype="easy", avg=6.0, planned=6.0)
        assert _volume_msg(r, db) is None

    def test_target_reached(self, db):
        user = _user(db)
        plan = self._plan_with_week(db, user, planned_km=20.0)
        subject = _run(
            db,
            user,
            days_ago=0,
            wtype="easy",
            avg=6.0,
            planned=6.0,
            plan_id=plan.id,
            dist=21.0,
        )
        db.commit()
        msg = _volume_msg(subject, db)
        assert msg is not None and "target reached" in msg

    def test_on_track(self, db):
        user = _user(db)
        plan = self._plan_with_week(db, user, planned_km=20.0)
        subject = _run(
            db,
            user,
            days_ago=0,
            wtype="easy",
            avg=6.0,
            planned=6.0,
            plan_id=plan.id,
            dist=16.0,
        )
        db.commit()
        msg = _volume_msg(subject, db)
        assert msg is not None and "on track" in msg

    def test_behind(self, db):
        user = _user(db)
        plan = self._plan_with_week(db, user, planned_km=20.0)
        subject = _run(
            db,
            user,
            days_ago=0,
            wtype="easy",
            avg=6.0,
            planned=6.0,
            plan_id=plan.id,
            dist=5.0,
        )
        db.commit()
        msg = _volume_msg(subject, db)
        assert msg is not None and "still to go" in msg

    def test_no_weekly_plan_returns_none(self, db):
        user = _user(db)
        plan = TrainingPlan(
            id=_uid(),
            user_id=user.id,
            current_weekly_km=20,
            target_distance="10.0",
            weeks_duration=8,
            start_date=_now() - timedelta(days=1),
        )
        db.add(plan)
        db.flush()
        subject = _run(
            db, user, days_ago=0, wtype="easy", avg=6.0, planned=6.0, plan_id=plan.id
        )
        db.commit()
        assert _volume_msg(subject, db) is None


class TestVolumeHighlightVocabularySync:
    """B10: the weekly-summary highlight must match the vocabulary
    volume_tracker actually emits (the old behind/ahead/exceed parse was dead).
    """

    @staticmethod
    def _data(volume_texts):
        return {
            "sentiments": ["info"] * len(volume_texts),
            "run_count": len(volume_texts),
            "pace_texts": [],
            "hr_texts": [],
            "effort_texts": [],
            "volume_texts": volume_texts,
            "pattern_texts": [],
        }

    @staticmethod
    def _all_highlights(summary):
        return [summary["summary"], *summary["highlights"]]

    def test_behind_messages_drive_falling_behind_highlight(self):
        from app.contexts.runner.fitness.feedback_service import _build_week_summary

        texts = [volume_feedback(2, 8.0, 30.0), volume_feedback(2, 9.0, 30.0)]
        summary = _build_week_summary(self._data(texts), 2)
        assert summary is not None
        assert any(
            "falling behind" in h.lower() for h in self._all_highlights(summary)
        ), f"behind highlight never fired for {texts}"

    def test_target_reached_messages_drive_exceeding_highlight(self):
        from app.contexts.runner.fitness.feedback_service import _build_week_summary

        texts = [volume_feedback(2, 31.0, 30.0), volume_feedback(2, 32.0, 30.0)]
        summary = _build_week_summary(self._data(texts), 2)
        assert summary is not None
        assert any("exceeding" in h.lower() for h in self._all_highlights(summary)), (
            f"exceeding highlight never fired for {texts}"
        )
