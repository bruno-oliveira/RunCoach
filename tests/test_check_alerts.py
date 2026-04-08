"""Tests for AdaptationService.check_alerts() — 3-week window logic."""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, User, TrainingPlan, WeeklyPlan, DailyWorkout, RunLog
from app.services.adaptation_service import AdaptationService


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


def _create_plan(db: Session, *, weeks: int = 10, weeks_ago: int | None = None):
    """Create a user + plan with weekly plans and 4 workouts per week.

    If *weeks_ago* is given the plan start_date is set that many weeks
    before today so the caller controls which week is "current".
    """
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    start = _now() - timedelta(weeks=weeks_ago) if weeks_ago else _now()

    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=weeks,
        start_date=start,
        plan_data=json.dumps([{"week": w + 1, "total_km": 30} for w in range(weeks)]),
    )
    db.add(plan)
    db.flush()

    for wk in range(1, weeks + 1):
        wp = WeeklyPlan(
            id=_uid(),
            training_plan_id=plan.id,
            week_number=wk,
            total_km=30,
        )
        db.add(wp)
        db.flush()

        for day in range(1, 5):  # 4 run days per week (Mon-Thu)
            dw = DailyWorkout(
                id=_uid(),
                weekly_plan_id=wp.id,
                day_of_week=day,
                workout_type="easy",
                distance_km=7.5,
            )
            db.add(dw)

    db.commit()
    return user, plan


def _link_workouts(db: Session, plan: TrainingPlan, user: User, weeks: list[int]):
    """Create RunLog entries linked to every workout in the given weeks."""
    weekly_plans = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number.in_(weeks),
        )
        .all()
    )
    for wp in weekly_plans:
        workouts = (
            db.query(DailyWorkout)
            .filter(DailyWorkout.weekly_plan_id == wp.id)
            .all()
        )
        for wo in workouts:
            db.add(RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                daily_workout_id=wo.id,
                date=plan.start_date + timedelta(weeks=wp.week_number - 1, days=wo.day_of_week - 1),
                distance_km=wo.distance_km,
                duration_minutes=40,
            ))
    db.commit()


def _link_partial(db: Session, plan: TrainingPlan, user: User, week: int, count: int):
    """Link only *count* workouts in a given week."""
    wp = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number == week,
        )
        .one()
    )
    workouts = (
        db.query(DailyWorkout)
        .filter(DailyWorkout.weekly_plan_id == wp.id)
        .limit(count)
        .all()
    )
    for wo in workouts:
        db.add(RunLog(
            id=_uid(),
            user_id=user.id,
            training_plan_id=plan.id,
            daily_workout_id=wo.id,
            date=plan.start_date + timedelta(weeks=wp.week_number - 1, days=wo.day_of_week - 1),
            distance_km=wo.distance_km,
            duration_minutes=40,
        ))
    db.commit()


class TestCheckAlerts:
    """Tests for the 3-week window missed-workout alert."""

    def test_no_alert_before_week_4(self, db):
        """Plans less than 4 weeks in should never trigger an alert."""
        svc = AdaptationService()
        user, plan = _create_plan(db, weeks=10, weeks_ago=2)
        # current_week = 3, not enough history
        assert svc.check_alerts(plan.id, user.id, db) is None

    def test_no_alert_when_all_completed(self, db):
        """If all workouts in the window are linked, no alert fires."""
        svc = AdaptationService()
        user, plan = _create_plan(db, weeks=10, weeks_ago=6)
        # current_week ~= 7; window = weeks 4, 5, 6 — link them all
        _link_workouts(db, plan, user, [4, 5, 6])
        result = svc.check_alerts(plan.id, user.id, db)
        assert result is None
        assert plan.adaptation_alert is None

    def test_alert_when_all_missed(self, db):
        """100% missed in 3-week window triggers an alert."""
        svc = AdaptationService()
        user, plan = _create_plan(db, weeks=10, weeks_ago=6)
        # current_week ~= 7; window = weeks 4, 5, 6 — leave all unlinked
        result = svc.check_alerts(plan.id, user.id, db)
        assert result is not None
        assert result["type"] == "missed_workouts"
        assert result["severity"] == "high"
        assert "100%" in result["message"]
        assert plan.adaptation_alert is not None

    def test_alert_at_exactly_50_percent(self, db):
        """Alert fires when exactly 50% of workouts are missed."""
        svc = AdaptationService()
        user, plan = _create_plan(db, weeks=10, weeks_ago=6)
        # window = weeks 4,5,6 → 12 workouts total (4 per week)
        # Link 2 of 4 in each week → 6 linked, 6 missed → 50%
        _link_partial(db, plan, user, 4, 2)
        _link_partial(db, plan, user, 5, 2)
        _link_partial(db, plan, user, 6, 2)
        result = svc.check_alerts(plan.id, user.id, db)
        assert result is not None
        assert result["type"] == "missed_workouts"

    def test_no_alert_below_50_percent(self, db):
        """No alert when missed percentage is below 50%."""
        svc = AdaptationService()
        user, plan = _create_plan(db, weeks=10, weeks_ago=6)
        # window = weeks 4,5,6 → 12 workouts
        # Link 3 of 4 in each week → 9 linked, 3 missed → 25%
        _link_partial(db, plan, user, 4, 3)
        _link_partial(db, plan, user, 5, 3)
        _link_partial(db, plan, user, 6, 3)
        result = svc.check_alerts(plan.id, user.id, db)
        assert result is None

    def test_clears_stale_alert(self, db):
        """A previously set alert is cleared when the threshold is no longer met."""
        svc = AdaptationService()
        user, plan = _create_plan(db, weeks=10, weeks_ago=6)

        # Trigger alert first
        svc.check_alerts(plan.id, user.id, db)
        assert plan.adaptation_alert is not None

        # Now link all window workouts
        _link_workouts(db, plan, user, [4, 5, 6])
        result = svc.check_alerts(plan.id, user.id, db)
        assert result is None
        assert plan.adaptation_alert is None


class TestCooldownAfterRecalibration:
    """After recalibration, alerts are suppressed for 3 full weeks."""

    def test_suppressed_during_cooldown(self, db):
        """No alert within 3 weeks of recalibration even if workouts are missed."""
        svc = AdaptationService()
        user, plan = _create_plan(db, weeks=12, weeks_ago=7)
        # current_week ~= 8; window = 5,6,7 — all missed

        # Simulate recalibration at week 6 (2 weeks ago)
        plan.last_adjusted_at = _now() - timedelta(weeks=2)
        db.commit()

        result = svc.check_alerts(plan.id, user.id, db)
        assert result is None

    def test_clears_stale_alert_during_cooldown(self, db):
        """Stale alert from before recalibration is cleared during cooldown."""
        svc = AdaptationService()
        user, plan = _create_plan(db, weeks=12, weeks_ago=7)

        # Pre-existing alert
        plan.adaptation_alert = json.dumps({"type": "missed_workouts", "message": "old"})
        plan.last_adjusted_at = _now() - timedelta(weeks=1)
        db.commit()

        result = svc.check_alerts(plan.id, user.id, db)
        assert result is None
        db.refresh(plan)
        assert plan.adaptation_alert is None

    def test_alert_fires_after_cooldown(self, db):
        """Alert can fire again once 3+ weeks have passed since recalibration."""
        svc = AdaptationService()
        user, plan = _create_plan(db, weeks=14, weeks_ago=10)
        # current_week ~= 11; window = 8,9,10 — all missed

        # Recalibrated at week 4 (~6 weeks ago), well past cooldown
        plan.last_adjusted_at = plan.start_date + timedelta(weeks=3)
        db.commit()

        result = svc.check_alerts(plan.id, user.id, db)
        assert result is not None
        assert result["type"] == "missed_workouts"


class TestEdgeCases:
    """Edge-case coverage."""

    def test_no_start_date(self, db):
        """Plans without a start date return None."""
        svc = AdaptationService()
        user, plan = _create_plan(db, weeks=10, weeks_ago=6)
        plan.start_date = None
        db.commit()
        assert svc.check_alerts(plan.id, user.id, db) is None

    def test_plan_not_found(self, db):
        """Non-existent plan returns None."""
        svc = AdaptationService()
        assert svc.check_alerts("nonexistent", "nobody", db) is None

    def test_rest_workouts_excluded(self, db):
        """Rest/recovery workouts are not counted toward the threshold."""
        svc = AdaptationService()
        user, plan = _create_plan(db, weeks=10, weeks_ago=6)

        # Change all workouts in the window to rest — nothing to miss
        window_wps = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan.id,
                WeeklyPlan.week_number.in_([4, 5, 6]),
            )
            .all()
        )
        for wp in window_wps:
            for wo in db.query(DailyWorkout).filter(DailyWorkout.weekly_plan_id == wp.id).all():
                wo.workout_type = "rest"
        db.commit()

        result = svc.check_alerts(plan.id, user.id, db)
        assert result is None

    def test_only_looks_at_3_week_window(self, db):
        """Missed workouts outside the window don't affect the alert."""
        svc = AdaptationService()
        user, plan = _create_plan(db, weeks=10, weeks_ago=6)
        # current_week ~= 7; window = 4, 5, 6
        # Link all window workouts but leave earlier weeks unlinked
        _link_workouts(db, plan, user, [4, 5, 6])
        # Weeks 1, 2, 3 are unlinked but outside the window
        result = svc.check_alerts(plan.id, user.id, db)
        assert result is None
