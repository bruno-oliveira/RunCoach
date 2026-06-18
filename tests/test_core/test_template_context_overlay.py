"""Tests for P2 §5.3 + §6.3 — render-time overlay (prev-run prefix + fatigue softening)."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.plan_template_context import (
    _build_today_workout_overlay,
    _coaching_prefix,
    _detect_fatigue_softening,
)
from app.models import Base, RunFeedback, RunLog, User


def _uid():
    return str(uuid.uuid4())


def _today():
    return date.today()


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


class _MockRun:
    def __init__(self, workout_type, perceived_effort):
        self.workout_type = workout_type
        self.perceived_effort = perceived_effort


class TestCoachingPrefix:
    def test_hard_workout_yesterday(self):
        assert _coaching_prefix(_MockRun("tempo", 8)).startswith(
            "After yesterday's hard tempo"
        )

    def test_none_for_easy_high_effort(self):
        assert _coaching_prefix(_MockRun("easy", 8)) is None


class TestDetectFatigueSoftening:
    def _seed_runs(self, db, *, efforts, warning_count):
        user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
        db.add(user)
        db.flush()
        runs = []
        for i, e in enumerate(efforts):
            run = RunLog(
                id=_uid(),
                user_id=user.id,
                date=datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(days=i),
                distance_km=10,
                duration_minutes=50,
                perceived_effort=e,
                workout_type="tempo",
            )
            db.add(run)
            runs.append(run)
        db.flush()
        for i in range(warning_count):
            db.add(
                RunFeedback(
                    id=_uid(),
                    run_log_id=runs[i].id,
                    user_id=user.id,
                    overall_sentiment="warning",
                )
            )
        db.commit()
        return user, runs

    def test_high_effort_with_warnings_triggers(self, db):
        user, runs = self._seed_runs(db, efforts=[8, 9, 8], warning_count=2)
        assert _detect_fatigue_softening(runs, db) is True

    def test_high_effort_without_warnings_no_trigger(self, db):
        user, runs = self._seed_runs(db, efforts=[8, 9, 8], warning_count=0)
        assert _detect_fatigue_softening(runs, db) is False

    def test_low_effort_no_trigger(self, db):
        user, runs = self._seed_runs(db, efforts=[5, 6, 5], warning_count=2)
        assert _detect_fatigue_softening(runs, db) is False

    def test_too_few_runs_no_trigger(self, db):
        user, runs = self._seed_runs(db, efforts=[9, 9], warning_count=2)
        assert _detect_fatigue_softening(runs, db) is False


class TestBuildOverlay:
    def test_overlay_empty_when_no_db(self):
        overlay = _build_today_workout_overlay(
            None,
            None,
            [],
            _today(),
            _today(),
            1,
        )
        assert overlay == {}

    def test_today_workout_overlay_keys_format(self, db):
        user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
        db.add(user)
        db.commit()
        today = _today()
        plan_data = [
            {
                "week": 1,
                "daily_workouts": [
                    {"day": today.isoweekday(), "type": "easy"},
                ],
            }
        ]
        # Add a hard tempo from yesterday so the prefix is generated.
        db.add(
            RunLog(
                id=_uid(),
                user_id=user.id,
                date=datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(days=1),
                distance_km=10,
                duration_minutes=50,
                perceived_effort=8,
                workout_type="tempo",
            )
        )
        db.commit()

        start_date = today - timedelta(days=today.isoweekday() - 1)
        overlay = _build_today_workout_overlay(
            db,
            user,
            plan_data,
            start_date,
            today,
            1,
        )

        # The key is "week-day" string
        key = f"1-{today.isoweekday()}"
        assert key in overlay
        assert overlay[key]["rationale_prefix"] is not None
        assert "tempo" in overlay[key]["rationale_prefix"]

    def test_quality_workout_softened_under_fatigue(self, db):
        user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
        db.add(user)
        db.commit()

        today = _today()
        # Three high-effort runs with two warning feedbacks → fatigue softening.
        runs = []
        for i, e in enumerate([8, 9, 8]):
            run = RunLog(
                id=_uid(),
                user_id=user.id,
                date=datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(days=i + 1),
                distance_km=10,
                duration_minutes=50,
                perceived_effort=e,
                workout_type="tempo",
            )
            db.add(run)
            runs.append(run)
        db.flush()
        db.add(
            RunFeedback(
                id=_uid(),
                run_log_id=runs[0].id,
                user_id=user.id,
                overall_sentiment="warning",
            )
        )
        db.add(
            RunFeedback(
                id=_uid(),
                run_log_id=runs[1].id,
                user_id=user.id,
                overall_sentiment="warning",
            )
        )
        db.commit()

        plan_data = [
            {
                "week": 1,
                "daily_workouts": [{"day": today.isoweekday(), "type": "tempo"}],
            }
        ]
        start_date = today - timedelta(days=today.isoweekday() - 1)
        overlay = _build_today_workout_overlay(
            db,
            user,
            plan_data,
            start_date,
            today,
            1,
        )
        key = f"1-{today.isoweekday()}"
        assert key in overlay
        assert overlay[key]["is_fatigue_softened"] is True

    def test_easy_workout_not_softened_under_fatigue(self, db):
        user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
        db.add(user)
        db.commit()

        today = _today()
        runs = []
        for i, e in enumerate([8, 9, 8]):
            run = RunLog(
                id=_uid(),
                user_id=user.id,
                date=datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(days=i + 1),
                distance_km=10,
                duration_minutes=50,
                perceived_effort=e,
                workout_type="tempo",
            )
            db.add(run)
            runs.append(run)
        db.flush()
        db.add(
            RunFeedback(
                id=_uid(),
                run_log_id=runs[0].id,
                user_id=user.id,
                overall_sentiment="warning",
            )
        )
        db.add(
            RunFeedback(
                id=_uid(),
                run_log_id=runs[1].id,
                user_id=user.id,
                overall_sentiment="warning",
            )
        )
        db.commit()

        plan_data = [
            {
                "week": 1,
                "daily_workouts": [{"day": today.isoweekday(), "type": "easy"}],
            }
        ]
        start_date = today - timedelta(days=today.isoweekday() - 1)
        overlay = _build_today_workout_overlay(
            db,
            user,
            plan_data,
            start_date,
            today,
            1,
        )
        key = f"1-{today.isoweekday()}"
        # Easy workout shouldn't be softened (even if signal would otherwise trigger)
        if key in overlay:
            assert overlay[key]["is_fatigue_softened"] is False


# ── long-run adequacy warning wiring ───────────────────────────────────────


def _fake_plan(**kw):
    from types import SimpleNamespace

    defaults = dict(
        plan_type="distance",
        target_distance="42.2",
        is_trail=False,
        target_elevation_gain_m=None,
        current_weekly_km=25.0,
        training_terrain=None,
        weeks_duration=12,
    )
    defaults.update(kw)
    tp = SimpleNamespace(**defaults)
    # mirror the model's target_distance_km property
    tp.target_distance_km = float(tp.target_distance) if tp.target_distance else 0.0
    return tp


def _plan_data_with_peak_long(peak_long_km):
    return [
        {
            "week": 1,
            "is_recovery": False,
            "daily_workouts": [
                {"day": 6, "type": "long", "distance": peak_long_km},
                {"day": 3, "type": "easy", "distance": 6.0},
            ],
        }
    ]


def test_build_long_run_warning_fires_for_underbuilt_marathon():
    from app.contexts.plan.plan_template_context import _build_long_run_warning

    warning = _build_long_run_warning(_fake_plan(), _plan_data_with_peak_long(22.0))
    assert warning is not None
    assert warning["pct_of_recommended"] < 85


def test_build_long_run_warning_quiet_when_adequate():
    from app.contexts.plan.plan_template_context import _build_long_run_warning

    warning = _build_long_run_warning(
        _fake_plan(weeks_duration=18), _plan_data_with_peak_long(33.0)
    )
    assert warning is None


def test_build_long_run_warning_skips_non_distance_plans():
    from app.contexts.plan.plan_template_context import _build_long_run_warning

    warning = _build_long_run_warning(
        _fake_plan(plan_type="performance"), _plan_data_with_peak_long(10.0)
    )
    assert warning is None
