"""Tests for the recalibration strategies and missed/skipped detectors.

Exercises the `recalibrate` dispatch entry point across every strategy
(time_off, ahead, missed_week, recovery_insertion, unknown) plus the
not-found / no-start-date guards, and the detect_missed_weeks /
detect_skipped_workouts helpers.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation.missed_week_handler import detect_missed_weeks
from app.contexts.plan.adaptation.recalibrator import recalibrate
from app.contexts.plan.adaptation.skipped_detector import detect_skipped_workouts
from app.models import Base, DailyWorkout, RunLog, TrainingPlan, User, WeeklyPlan

_WORKOUT_TYPES = ["easy", "tempo", "interval", "long"]


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


def _make_plan(db, *, weeks=8, weeks_ago=4, with_start=True):
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    start = _now() - timedelta(weeks=weeks_ago) if with_start else None
    plan_data = [
        {
            "week": wk,
            "total_km": 38,
            "phase": "build",
            "daily_workouts": [
                {"day": i + 1, "type": t, "distance": 8.0 if t != "long" else 14.0}
                for i, t in enumerate(_WORKOUT_TYPES)
            ],
        }
        for wk in range(1, weeks + 1)
    ]
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="21.1",
        weeks_duration=weeks,
        vdot=45.0,
        start_date=start,
        plan_data=plan_data,
    )
    db.add(plan)
    db.flush()

    for wk in range(1, weeks + 1):
        wp = WeeklyPlan(
            id=_uid(), training_plan_id=plan.id, week_number=wk, total_km=38
        )
        db.add(wp)
        db.flush()
        for i, t in enumerate(_WORKOUT_TYPES):
            dist = 8.0 if t != "long" else 14.0
            db.add(
                DailyWorkout(
                    id=_uid(),
                    weekly_plan_id=wp.id,
                    day_of_week=i + 1,
                    workout_type=t,
                    distance_km=dist,
                    baseline_distance_km=dist,
                )
            )
    db.commit()
    return user, plan


def _future_easy(db, plan):
    """Easy/long workouts in weeks strictly after the current week (>=6)."""
    return (
        db.query(DailyWorkout)
        .join(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number >= 6,
            DailyWorkout.workout_type.in_(["easy", "long"]),
        )
        .all()
    )


def _make_ascending_plan(db, *, weeks=8, weeks_ago=4):
    """Plan whose easy/long volume rises week over week, so the missed-week
    shift-back would inherit a *bigger* later week's load without a guard."""
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()
    start = _now() - timedelta(weeks=weeks_ago)

    def _dist(wk, t):
        # Easy/long climb with the week number; quality held flat.
        if t == "easy":
            return 5.0 + wk
        if t == "long":
            return 10.0 + wk
        return 8.0

    plan_data = [
        {
            "week": wk,
            "total_km": 38,
            "phase": "build",
            "daily_workouts": [
                {"day": i + 1, "type": t, "distance": _dist(wk, t)}
                for i, t in enumerate(_WORKOUT_TYPES)
            ],
        }
        for wk in range(1, weeks + 1)
    ]
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        # High current volume so the week-total growth cap stays permissive and
        # the per-workout shift-back (not the growth cap) is the binding effect.
        current_weekly_km=60,
        target_distance="21.1",
        weeks_duration=weeks,
        vdot=45.0,
        start_date=start,
        plan_data=plan_data,
    )
    db.add(plan)
    db.flush()
    for wk in range(1, weeks + 1):
        wp = WeeklyPlan(
            id=_uid(), training_plan_id=plan.id, week_number=wk, total_km=38
        )
        db.add(wp)
        db.flush()
        for i, t in enumerate(_WORKOUT_TYPES):
            dist = _dist(wk, t)
            db.add(
                DailyWorkout(
                    id=_uid(),
                    weekly_plan_id=wp.id,
                    day_of_week=i + 1,
                    workout_type=t,
                    distance_km=dist,
                    baseline_distance_km=dist,
                )
            )
    db.commit()
    return user, plan


class TestMissedWeekDownwardOnly:
    """B9: re-entry after a missed week must never push a later week ABOVE its
    originally prescribed (baseline) load."""

    def test_shift_back_never_exceeds_baseline(self, db):
        user, plan = _make_ascending_plan(db)
        result = recalibrate(plan.id, user.id, "missed_week", db)
        assert result["ok"] is True

        db.expire_all()
        offenders = (
            db.query(DailyWorkout)
            .join(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan.id,
                DailyWorkout.workout_type.in_(["easy", "long"]),
                DailyWorkout.distance_km > DailyWorkout.baseline_distance_km + 0.01,
            )
            .all()
        )
        assert not offenders, "missed-week recalibration raised " + ", ".join(
            f"wk-workout {o.id[:6]} {o.distance_km}>{o.baseline_distance_km}"
            for o in offenders
        )


class TestRecalibrateGuards:
    def test_plan_not_found(self, db):
        result = recalibrate("nope", "nobody", "time_off", db)
        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    def test_no_start_date(self, db):
        user, plan = _make_plan(db, with_start=False)
        result = recalibrate(plan.id, user.id, "time_off", db)
        assert result["ok"] is False
        assert "start date" in result["error"].lower()

    def test_unknown_strategy(self, db):
        user, plan = _make_plan(db)
        result = recalibrate(plan.id, user.id, "bogus", db)
        assert result["ok"] is False
        assert "Unknown strategy" in result["error"]


class TestRecalibrateScaling:
    def test_time_off_reduces_future_easy_runs(self, db):
        user, plan = _make_plan(db)
        before = {w.id: w.distance_km for w in _future_easy(db, plan)}

        result = recalibrate(plan.id, user.id, "time_off", db)

        assert result["ok"] is True
        assert result["strategy"] == "time_off"
        db.expire_all()
        after = {w.id: w.distance_km for w in _future_easy(db, plan)}
        assert any(after[wid] < before[wid] for wid in before)
        # Records the event on the plan's adaptation history.
        db.refresh(plan)
        assert plan.adaptation_history[-1]["type"] == "recalibrate"
        assert plan.last_recalibrated_at is not None

    def test_ahead_increases_future_easy_runs(self, db):
        user, plan = _make_plan(db)
        before = {w.id: w.distance_km for w in _future_easy(db, plan)}

        result = recalibrate(plan.id, user.id, "ahead", db)

        assert result["ok"] is True
        db.expire_all()
        after = {w.id: w.distance_km for w in _future_easy(db, plan)}
        assert any(after[wid] > before[wid] for wid in before)

    def test_quality_workouts_are_preserved(self, db):
        user, plan = _make_plan(db)
        before = {
            w.id: w.distance_km
            for w in db.query(DailyWorkout)
            .join(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan.id,
                WeeklyPlan.week_number >= 6,
                DailyWorkout.workout_type.in_(["tempo", "interval"]),
            )
            .all()
        }

        recalibrate(plan.id, user.id, "time_off", db)

        db.expire_all()
        after = {
            w.id: w.distance_km
            for w in db.query(DailyWorkout).filter(DailyWorkout.id.in_(before)).all()
        }
        assert after == before


class TestRecalibrateStrategies:
    def test_missed_week(self, db):
        user, plan = _make_plan(db)
        result = recalibrate(plan.id, user.id, "missed_week", db)
        assert result["ok"] is True
        assert result["strategy"] == "missed_week"
        assert result["weeks_changed"] >= 1
        assert "missed week" in result["reason"].lower()

    def test_recovery_insertion(self, db):
        user, plan = _make_plan(db)
        result = recalibrate(plan.id, user.id, "recovery_insertion", db)
        assert result["ok"] is True
        assert result["strategy"] == "recovery_insertion"
        target = result["target_week"]
        db.expire_all()
        wp = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan.id,
                WeeklyPlan.week_number == target,
            )
            .one()
        )
        # Converted week carries ~60% of the original 38 km volume.
        assert wp.total_km < 38

    def test_recovery_insertion_capped_at_two(self, db):
        user, plan = _make_plan(db)
        recalibrate(plan.id, user.id, "recovery_insertion", db)
        recalibrate(plan.id, user.id, "recovery_insertion", db)
        third = recalibrate(plan.id, user.id, "recovery_insertion", db)
        assert third["ok"] is False
        assert "Maximum recovery insertions" in third["error"]


class TestDetectors:
    def test_detect_missed_weeks_flags_empty_weeks(self, db):
        user, plan = _make_plan(db)
        start = plan.start_date
        # Log a run only in week 1; weeks 2..current-1 are "missed".
        db.add(
            RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                date=start + timedelta(days=2),
                distance_km=8.0,
                duration_minutes=48,
            )
        )
        db.commit()

        missed = detect_missed_weeks(plan.id, user.id, db)
        assert 1 not in missed
        assert 2 in missed

    def test_detect_missed_weeks_no_plan(self, db):
        assert detect_missed_weeks("missing", "nobody", db) == []

    def test_detect_skipped_workouts_counts_unlinked(self, db):
        user, plan = _make_plan(db)
        # No runs logged at all → every past workout is unlinked, and with
        # zero actual volume each past week counts as skipped.
        result = detect_skipped_workouts(plan.id, db)
        assert result["skipped"] > 0
        assert result["rescheduled"] == 0

    def test_detect_skipped_workouts_rescheduled_when_volume_met(self, db):
        user, plan = _make_plan(db)
        start = plan.start_date
        # Hit week-1 volume (>=80% of 38 km) without linking to a workout, so
        # the unlinked week-1 workouts count as "rescheduled", not skipped.
        db.add(
            RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                date=start + timedelta(days=1),
                distance_km=40.0,
                duration_minutes=240,
            )
        )
        db.commit()
        result = detect_skipped_workouts(plan.id, db, since=start - timedelta(days=1))
        assert result["rescheduled"] >= 1

    def test_detect_skipped_workouts_no_plan(self, db):
        assert detect_skipped_workouts("missing", db) == {
            "skipped": 0,
            "rescheduled": 0,
        }


def _quality_runs(db, user, plan, *, avg_pace, planned_pace, count, wtype="tempo"):
    """Add `count` recent quality runs with given actual/planned pace."""
    today = _now()
    for i in range(count):
        db.add(
            RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                date=today - timedelta(days=i * 3),
                distance_km=8.0,
                duration_minutes=8.0 * avg_pace,
                avg_pace_min_km=avg_pace,
                planned_pace_min_km=planned_pace,
                workout_type=wtype,
            )
        )
    db.commit()


class TestPaceHitRecalibration:
    """Audit E5 — recalibrate VDOT from quality-session pace hit-rate."""

    def test_faster_than_target_implies_higher_vdot(self, db):
        from app.contexts.plan.adaptation.vdot_recalibrator import (
            _pace_hit_implied_vdot,
        )

        user, plan = _make_plan(db)
        _quality_runs(db, user, plan, avg_pace=3.7, planned_pace=4.0, count=5)
        implied = _pace_hit_implied_vdot(plan.id, user.id, db, 50.0)
        assert implied is not None and implied > 50.0

    def test_slower_than_target_implies_lower_vdot(self, db):
        from app.contexts.plan.adaptation.vdot_recalibrator import (
            _pace_hit_implied_vdot,
        )

        user, plan = _make_plan(db)
        _quality_runs(db, user, plan, avg_pace=4.5, planned_pace=4.0, count=5)
        implied = _pace_hit_implied_vdot(plan.id, user.id, db, 50.0)
        assert implied is not None and implied < 50.0

    def test_on_target_returns_none(self, db):
        from app.contexts.plan.adaptation.vdot_recalibrator import (
            _pace_hit_implied_vdot,
        )

        user, plan = _make_plan(db)
        _quality_runs(db, user, plan, avg_pace=4.0, planned_pace=4.0, count=5)
        assert _pace_hit_implied_vdot(plan.id, user.id, db, 50.0) is None

    def test_thin_sample_returns_none(self, db):
        from app.contexts.plan.adaptation.vdot_recalibrator import (
            _pace_hit_implied_vdot,
        )

        user, plan = _make_plan(db)
        _quality_runs(db, user, plan, avg_pace=3.5, planned_pace=4.0, count=2)
        assert _pace_hit_implied_vdot(plan.id, user.id, db, 50.0) is None
