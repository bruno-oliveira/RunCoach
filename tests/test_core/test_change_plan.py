"""Tests for the ChangePlan flow: preview vs apply, easy-run regression,
no-change paths, mark-seen.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation import AdaptationService
from app.contexts.plan.adaptation.plan_adjuster import (
    adjust_plan,
    preview_adjust_plan,
    preview_reset_adjustment,
    reset_adjustment,
)
from app.models import Base, DailyWorkout, RunLog, TrainingPlan, User, WeeklyPlan


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


def _create_plan(db, *, weeks=8, weeks_ago=4):
    """Make a user + plan with easy/tempo/interval/long workouts per week."""
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    start = _now() - timedelta(weeks=weeks_ago)
    workout_types = ["easy", "tempo", "interval", "long"]

    plan_data = []
    for wk in range(1, weeks + 1):
        plan_data.append(
            {
                "week": wk,
                "total_km": 35,
                "phase": "build",
                "daily_workouts": [
                    {"day": i + 1, "type": t, "distance": 8.0 if t != "long" else 14.0}
                    for i, t in enumerate(workout_types)
                ],
            }
        )

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
            id=_uid(), training_plan_id=plan.id, week_number=wk, total_km=35
        )
        db.add(wp)
        db.flush()
        for i, t in enumerate(workout_types):
            db.add(
                DailyWorkout(
                    id=_uid(),
                    weekly_plan_id=wp.id,
                    day_of_week=i + 1,
                    workout_type=t,
                    distance_km=8.0 if t != "long" else 14.0,
                    baseline_distance_km=8.0 if t != "long" else 14.0,
                )
            )
    db.commit()
    return user, plan


def _add_runs(db, plan, user, weeks, *, effort=5.0, distance_multiplier=1.0):
    types = ["easy", "tempo", "interval", "long"]
    for wk in weeks:
        wp = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan.id,
                WeeklyPlan.week_number == wk,
            )
            .one()
        )
        wos = (
            db.query(DailyWorkout)
            .filter(
                DailyWorkout.weekly_plan_id == wp.id,
            )
            .order_by(DailyWorkout.day_of_week)
            .all()
        )
        for i, wo in enumerate(wos):
            if i >= len(types):
                continue
            run_date = plan.start_date + timedelta(
                weeks=wp.week_number - 1,
                days=wo.day_of_week - 1,
            )
            db.add(
                RunLog(
                    id=_uid(),
                    user_id=user.id,
                    training_plan_id=plan.id,
                    daily_workout_id=wo.id,
                    date=run_date,
                    distance_km=wo.distance_km * distance_multiplier,
                    duration_minutes=40,
                    perceived_effort=effort,
                    workout_type=wo.workout_type,
                )
            )
    db.commit()


def _easy_workouts_for_week(db, plan, week):
    wp = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number == week,
        )
        .one()
    )
    return (
        db.query(DailyWorkout)
        .filter(
            DailyWorkout.weekly_plan_id == wp.id,
            DailyWorkout.workout_type == "easy",
        )
        .all()
    )


# Default future week to inspect (week 5 is "current" for weeks_ago=4 setups).
FUTURE_WEEK = 6


class TestPreviewVsApply:
    def test_preview_does_not_mutate_db(self, db):
        user, plan = _create_plan(db)
        _add_runs(db, plan, user, [1, 2, 3], effort=5.0, distance_multiplier=1.4)

        easy_before = _easy_workouts_for_week(db, plan, week=FUTURE_WEEK)
        distances_before = [w.distance_km for w in easy_before]

        result = preview_adjust_plan(plan.id, user.id, db)

        assert result["mode"] == "preview"
        # Pull fresh from DB (post-rollback)
        easy_after = _easy_workouts_for_week(db, plan, week=FUTURE_WEEK)
        distances_after = [w.distance_km for w in easy_after]
        assert distances_after == distances_before

        plan_after = db.query(TrainingPlan).filter(TrainingPlan.id == plan.id).one()
        assert plan_after.last_change_plan is None
        assert plan_after.adjustment_multiplier is None

    def test_apply_persists_last_change_plan(self, db):
        user, plan = _create_plan(db)
        _add_runs(db, plan, user, [1, 2, 3], effort=5.0, distance_multiplier=1.4)

        result = adjust_plan(plan.id, user.id, db)
        assert "change_plan" in result
        cp = result["change_plan"]
        assert cp["mode"] == "applied"
        assert cp["seen"] is False

        db.expire_all()
        plan_after = db.query(TrainingPlan).filter(TrainingPlan.id == plan.id).one()
        assert plan_after.last_change_plan is not None
        assert plan_after.last_change_plan["mode"] == "applied"
        assert plan_after.last_change_plan["action"] == "adjust"


class TestEasyRunScaling:
    def test_easy_runs_scaled_by_multiplier(self, db):
        user, plan = _create_plan(db)
        _add_runs(db, plan, user, [1, 2, 3], effort=5.0, distance_multiplier=1.4)

        result = adjust_plan(plan.id, user.id, db)
        mult = result["multiplier"]
        # The signal stack may push the multiplier either way; verify
        # that whatever direction it picked, the easy runs reflect it.
        assert abs(mult - 1.0) >= 0.02, (
            f"multiplier too close to neutral to test scaling: {mult}"
        )

        # Look at week 6 (definitely future — week 5 is current)
        wp6 = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan.id,
                WeeklyPlan.week_number == 6,
            )
            .one()
        )
        easy = (
            db.query(DailyWorkout)
            .filter(
                DailyWorkout.weekly_plan_id == wp6.id,
                DailyWorkout.workout_type == "easy",
            )
            .one()
        )
        assert easy.distance_km != easy.baseline_distance_km, (
            "easy run distance_km did not change after adjust_plan"
        )
        # Allow either the global multiplier or a per-type multiplier
        # (signal_computer may emit per_type_ratios that diverge from the
        # global value within the 0.85–1.15 band).
        baseline = easy.baseline_distance_km
        ratio = easy.distance_km / baseline
        assert 0.85 <= ratio <= 1.15, f"easy run ratio out of 0.85–1.15 band: {ratio}"

        cp = result["change_plan"]
        flat = [wo for week in cp["weeks"] for wo in week["workouts"]]
        easy_changed = [
            wo for wo in flat if wo["type"] == "easy" and wo["status"] == "changed"
        ]
        assert easy_changed, (
            f"no easy workouts marked as 'changed' in ChangePlan: {flat}"
        )

    def test_protected_workouts_are_listed_with_reason(self, db):
        user, plan = _create_plan(db)
        _add_runs(db, plan, user, [1, 2, 3], effort=5.0, distance_multiplier=1.4)
        result = adjust_plan(plan.id, user.id, db)
        cp = result["change_plan"]
        flat = [wo for week in cp["weeks"] for wo in week["workouts"]]
        protected = [wo for wo in flat if wo["status"] == "protected"]
        assert protected, "expected at least one protected workout entry"
        for wo in protected:
            assert wo["reason"], f"protected workout missing reason: {wo}"


class TestNoChangePaths:
    def test_insufficient_runs(self, db):
        user, plan = _create_plan(db)
        # No runs at all — total_runs < 3 triggers insufficient-data path
        result = adjust_plan(plan.id, user.id, db)
        assert "change_plan" in result
        cp = result["change_plan"]
        assert cp["would_change"] is False
        assert cp["no_change_reasons"]


class TestMarkSeen:
    def test_mark_seen_flips_flag(self, db):
        user, plan = _create_plan(db)
        _add_runs(db, plan, user, [1, 2, 3], effort=5.0, distance_multiplier=1.4)
        adjust_plan(plan.id, user.id, db)

        svc = AdaptationService()
        out = svc.mark_change_plan_seen(plan.id, user.id, db)
        assert out["ok"] is True

        db.expire_all()
        plan_after = db.query(TrainingPlan).filter(TrainingPlan.id == plan.id).one()
        assert plan_after.last_change_plan["seen"] is True

    def test_mark_seen_noop_when_no_plan(self, db):
        user, plan = _create_plan(db)
        svc = AdaptationService()
        out = svc.mark_change_plan_seen(plan.id, user.id, db)
        assert out.get("noop") is True


class TestResetAdjustment:
    def test_reset_preview_does_not_mutate(self, db):
        user, plan = _create_plan(db)
        _add_runs(db, plan, user, [1, 2, 3], effort=5.0, distance_multiplier=1.4)
        adjust_plan(plan.id, user.id, db)

        # After adjust, easy runs are scaled up. Now preview reset.
        easy = _easy_workouts_for_week(db, plan, week=FUTURE_WEEK)
        adjusted_distances = [w.distance_km for w in easy]
        assert adjusted_distances[0] != 8.0, "expected adjusted distance"

        result = preview_reset_adjustment(plan.id, user.id, db)
        assert result["mode"] == "preview"

        # Confirm distances unchanged after preview
        db.expire_all()
        easy_after = _easy_workouts_for_week(db, plan, week=FUTURE_WEEK)
        assert [w.distance_km for w in easy_after] == adjusted_distances

    def test_reset_apply_restores_baseline(self, db):
        user, plan = _create_plan(db)
        _add_runs(db, plan, user, [1, 2, 3], effort=5.0, distance_multiplier=1.4)
        adjust_plan(plan.id, user.id, db)

        result = reset_adjustment(plan.id, user.id, db)
        assert result["reset"] is True

        db.expire_all()
        easy_after = _easy_workouts_for_week(db, plan, week=FUTURE_WEEK)
        for wo in easy_after:
            assert wo.distance_km == wo.baseline_distance_km

    def test_reset_recovers_corrupted_baseline(self, db):
        """A baseline frozen to an already-adjusted distance (legacy backfill)
        must not be treated as the true original. Reset normalizes first, so
        it restores the genuine distance recovered from the "(Adjusted: xN)"
        note rather than the inflated value."""
        user, plan = _create_plan(db)

        # Corrupt one easy workout: baseline == inflated distance, stale note.
        easy = _easy_workouts_for_week(db, plan, week=FUTURE_WEEK)[0]
        easy.distance_km = 9.2  # 8.0 * 1.15
        easy.baseline_distance_km = 9.2
        easy.notes = "Easy run (Adjusted: x1.15)"
        plan.adjustment_multiplier = 1.15  # so reset is not a no-op
        db.commit()
        easy_id = easy.id

        result = reset_adjustment(plan.id, user.id, db)
        assert result["reset"] is True

        db.expire_all()
        restored = db.query(DailyWorkout).filter(DailyWorkout.id == easy_id).one()
        assert restored.distance_km == 8.0
        assert restored.baseline_distance_km == 8.0
        assert "Adjusted" not in (restored.notes or "")
