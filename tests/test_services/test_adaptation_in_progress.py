"""Tests for the week-in-progress lock + recommendation anchoring.

Covers:
- The current week is locked once it has started (today past Monday, or
  any run logged within it). Adjustments target `current_week + 1`.
- A fresh current week (Monday + no logs) IS adjustable.
- `accept_recommendation` anchors on `rec["week_evaluated"] + 1`,
  collapsing the Sunday-vs-Monday "cliff" but never reaching into a
  started week.
- After a growth-cap pass, sum(daily distances) == weekly chip for every
  adjusted week (JSON drift fix).
"""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation.plan_adjuster import adjust_plan
from app.contexts.plan.adaptation.recommendation_evaluator import (
    accept_recommendation,
)
from app.models import (
    Base,
    DailyWorkout,
    RunLog,
    TrainingPlan,
    User,
    WeeklyPlan,
)


def _uid() -> str:
    return str(uuid.uuid4())


# A Monday we can freeze the clock to. May 18, 2026 == isoweekday 1.
MON = date(2026, 5, 18)
WED = date(2026, 5, 20)  # isoweekday 3
SUN = date(2026, 5, 24)  # isoweekday 7


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


@pytest.fixture()
def freeze_today(monkeypatch):
    """Freeze `today_date` across the adaptation modules. Returns a setter."""
    holder = {"value": MON}

    def fake_today():
        return holder["value"]

    monkeypatch.setattr(
        "app.contexts.plan.adaptation._helpers.today_date",
        fake_today,
    )
    monkeypatch.setattr(
        "app.contexts.plan.adaptation.plan_adjuster.today_date",
        fake_today,
    )
    monkeypatch.setattr(
        "app.contexts.plan.adaptation.recommendation_evaluator.today_date",
        fake_today,
    )

    def setter(d: date) -> None:
        holder["value"] = d

    return setter


def _make_plan(
    db: Session,
    *,
    today_value: date,
    current_week: int = 3,
    weeks: int = 8,
) -> tuple[User, TrainingPlan]:
    """Build a plan whose `start_date` puts `today_value` into `current_week`.

    Uses 4 easy workouts per week (Mon–Thu) with baseline 7.5 km each
    (weekly total 30 km). Easy-only keeps the multiplier path simple —
    no key/tempo workouts to be protected.
    """
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    days_into_week = today_value.isoweekday() - 1
    days_elapsed = (current_week - 1) * 7 + days_into_week
    start_date = datetime.combine(
        today_value - timedelta(days=days_elapsed),
        datetime.min.time(),
    )

    plan_data = [
        {
            "week": w + 1,
            "total_km": 30.0,
            "phase": "build",
            "daily_workouts": [
                {"day": d, "type": "easy", "distance": 7.5} for d in range(1, 5)
            ],
        }
        for w in range(weeks)
    ]
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=weeks,
        vdot=45.0,
        start_date=start_date,
        plan_data=plan_data,
    )
    db.add(plan)
    db.flush()

    for wk in range(1, weeks + 1):
        wp = WeeklyPlan(
            id=_uid(),
            training_plan_id=plan.id,
            week_number=wk,
            total_km=30.0,
        )
        db.add(wp)
        db.flush()
        for day in range(1, 5):
            db.add(
                DailyWorkout(
                    id=_uid(),
                    weekly_plan_id=wp.id,
                    day_of_week=day,
                    workout_type="easy",
                    distance_km=7.5,
                    baseline_distance_km=7.5,
                )
            )
    db.commit()
    return user, plan


def _log_runs_in_week(
    db: Session,
    user: User,
    plan: TrainingPlan,
    week_number: int,
    *,
    distance_km: float = 9.0,
    effort: int = 8,
) -> None:
    """Log all 4 runs in a week with elevated distance & effort.

    Elevated distance (9 km vs 7.5 baseline) and high effort drive the
    adjustment multiplier well away from 1.0 so the test can assert the
    direction without flakiness from the signal stack.
    """
    wp = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number == week_number,
        )
        .one()
    )
    workouts = (
        db.query(DailyWorkout)
        .filter(DailyWorkout.weekly_plan_id == wp.id)
        .order_by(DailyWorkout.day_of_week)
        .all()
    )
    for wo in workouts:
        run_date = plan.start_date + timedelta(
            weeks=week_number - 1,
            days=wo.day_of_week - 1,
        )
        db.add(
            RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                daily_workout_id=wo.id,
                date=run_date,
                distance_km=distance_km,
                duration_minutes=45,
                perceived_effort=effort,
                workout_type=wo.workout_type,
            )
        )
    db.commit()


def _week_total_and_distances(
    db: Session,
    plan_id: str,
    week_number: int,
) -> tuple[float, list[float]]:
    wp = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number == week_number,
        )
        .one()
    )
    distances = [
        wo.distance_km
        for wo in db.query(DailyWorkout)
        .filter(DailyWorkout.weekly_plan_id == wp.id)
        .order_by(DailyWorkout.day_of_week)
        .all()
    ]
    return wp.total_km, distances


# ---------------------------------------------------------------------------
# Manual adjust: current_week lock semantics
# ---------------------------------------------------------------------------


class TestManualAdjustCurrentWeekLock:
    def test_past_monday_current_week_untouched(self, db, freeze_today):
        """Wednesday: current week 3 must stay at baseline."""
        freeze_today(WED)
        user, plan = _make_plan(db, today_value=WED, current_week=3)
        _log_runs_in_week(db, user, plan, 1, distance_km=9.0, effort=8)
        _log_runs_in_week(db, user, plan, 2, distance_km=9.0, effort=8)

        wk3_before = _week_total_and_distances(db, plan.id, 3)

        result = adjust_plan(plan.id, user.id, db)
        assert result["adjusted"] is True

        wk3_after = _week_total_and_distances(db, plan.id, 3)
        assert wk3_after == wk3_before, "current week was modified mid-stream"

        wk4_before_total = 30.0
        wk4_total, _ = _week_total_and_distances(db, plan.id, 4)
        assert wk4_total != wk4_before_total, "week 4 should have been adjusted"

    def test_fresh_monday_current_week_is_adjustable(self, db, freeze_today):
        """Monday + no logs in current week: current week IS adjusted."""
        freeze_today(MON)
        user, plan = _make_plan(db, today_value=MON, current_week=3)
        _log_runs_in_week(db, user, plan, 1, distance_km=9.0, effort=8)
        _log_runs_in_week(db, user, plan, 2, distance_km=9.0, effort=8)

        wk3_before = _week_total_and_distances(db, plan.id, 3)

        result = adjust_plan(plan.id, user.id, db)
        assert result["adjusted"] is True

        wk3_total_after, _ = _week_total_and_distances(db, plan.id, 3)
        assert wk3_total_after != wk3_before[0], (
            "fresh-Monday current week should have been adjusted"
        )

    def test_monday_with_log_locks_current_week(self, db, freeze_today):
        """Monday but a run already logged for today: current week locked."""
        freeze_today(MON)
        user, plan = _make_plan(db, today_value=MON, current_week=3)
        _log_runs_in_week(db, user, plan, 1, distance_km=9.0, effort=8)
        _log_runs_in_week(db, user, plan, 2, distance_km=9.0, effort=8)
        # Single Monday run inside current week → in-progress.
        wp3 = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan.id,
                WeeklyPlan.week_number == 3,
            )
            .one()
        )
        mon_wo = (
            db.query(DailyWorkout)
            .filter(
                DailyWorkout.weekly_plan_id == wp3.id,
                DailyWorkout.day_of_week == 1,
            )
            .one()
        )
        db.add(
            RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                daily_workout_id=mon_wo.id,
                date=datetime.combine(MON, datetime.min.time()),
                distance_km=8.0,
                duration_minutes=40,
                perceived_effort=7,
                workout_type="easy",
            )
        )
        db.commit()

        wk3_before = _week_total_and_distances(db, plan.id, 3)
        result = adjust_plan(plan.id, user.id, db)
        assert result["adjusted"] is True
        assert _week_total_and_distances(db, plan.id, 3) == wk3_before


# ---------------------------------------------------------------------------
# accept_recommendation: anchored on week_evaluated + 1
# ---------------------------------------------------------------------------


class TestAcceptRecommendationAnchor:
    def _park_recommendation(
        self,
        plan: TrainingPlan,
        db,
        *,
        week_evaluated: int,
        multiplier: float,
    ) -> None:
        plan.pending_recommendation = {
            "week_evaluated": week_evaluated,
            "multiplier": multiplier,
            "direction": "increase" if multiplier > 1.0 else "reduce",
            "reason": "test",
            "signals": {},
            "created_at": "2026-05-18",
        }
        db.commit()

    def test_fresh_monday_accept_adjusts_current_week(self, db, freeze_today):
        """Monday + no logs in week 3, rec from week 2 → week 3 adjusted."""
        freeze_today(MON)
        user, plan = _make_plan(db, today_value=MON, current_week=3)
        self._park_recommendation(plan, db, week_evaluated=2, multiplier=1.10)

        wk3_total_before, _ = _week_total_and_distances(db, plan.id, 3)
        result = accept_recommendation(plan.id, user.id, db)
        assert result["accepted"] is True

        wk3_total_after, _ = _week_total_and_distances(db, plan.id, 3)
        assert wk3_total_after != wk3_total_before, (
            "fresh-Monday accept should adjust week 3 (rec.week_evaluated+1)"
        )

    def test_in_progress_monday_accept_locks_current_week(
        self,
        db,
        freeze_today,
    ):
        """Monday but a run already logged today: week 3 locked, week 4+ moved."""
        freeze_today(MON)
        user, plan = _make_plan(db, today_value=MON, current_week=3)

        wp3 = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan.id,
                WeeklyPlan.week_number == 3,
            )
            .one()
        )
        mon_wo = (
            db.query(DailyWorkout)
            .filter(
                DailyWorkout.weekly_plan_id == wp3.id,
                DailyWorkout.day_of_week == 1,
            )
            .one()
        )
        db.add(
            RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                daily_workout_id=mon_wo.id,
                date=datetime.combine(MON, datetime.min.time()),
                distance_km=8.0,
                duration_minutes=40,
                perceived_effort=7,
                workout_type="easy",
            )
        )
        db.commit()

        self._park_recommendation(plan, db, week_evaluated=2, multiplier=1.10)

        wk3_before = _week_total_and_distances(db, plan.id, 3)
        wk4_total_before, _ = _week_total_and_distances(db, plan.id, 4)
        result = accept_recommendation(plan.id, user.id, db)
        assert result["accepted"] is True
        assert _week_total_and_distances(db, plan.id, 3) == wk3_before
        wk4_total_after, _ = _week_total_and_distances(db, plan.id, 4)
        assert wk4_total_after != wk4_total_before

    def test_past_monday_accept_locks_current_week(self, db, freeze_today):
        """Wednesday accept: week 3 locked regardless of rec.week_evaluated."""
        freeze_today(WED)
        user, plan = _make_plan(db, today_value=WED, current_week=3)
        self._park_recommendation(plan, db, week_evaluated=2, multiplier=1.10)

        wk3_before = _week_total_and_distances(db, plan.id, 3)
        result = accept_recommendation(plan.id, user.id, db)
        assert result["accepted"] is True
        assert _week_total_and_distances(db, plan.id, 3) == wk3_before

    def test_stale_recommendation_does_not_reach_past_weeks(
        self,
        db,
        freeze_today,
    ):
        """rec.week_evaluated=1 + current_week=5 in-progress → first=6."""
        freeze_today(WED)
        user, plan = _make_plan(db, today_value=WED, current_week=5)
        self._park_recommendation(plan, db, week_evaluated=1, multiplier=1.10)

        # Weeks 1–5 must remain at baseline (already-run or current).
        before_per_week = {
            wk: _week_total_and_distances(db, plan.id, wk) for wk in range(1, 6)
        }
        result = accept_recommendation(plan.id, user.id, db)
        assert result["accepted"] is True
        for wk in range(1, 6):
            assert _week_total_and_distances(db, plan.id, wk) == before_per_week[wk], (
                f"week {wk} should not have been touched"
            )
        wk6_total, _ = _week_total_and_distances(db, plan.id, 6)
        assert wk6_total != 30.0, "week 6 should be the first adjustable week"


# ---------------------------------------------------------------------------
# JSON / ORM reconciliation
# ---------------------------------------------------------------------------


class TestWeeklyTotalReconciliation:
    def test_orm_and_json_match_after_adjust(self, db, freeze_today):
        """After adjust_plan, JSON per-workout distances sum to JSON total_km
        AND match the ORM, for every adjusted week."""
        freeze_today(WED)
        user, plan = _make_plan(
            db,
            today_value=WED,
            current_week=3,
            weeks=8,
        )
        _log_runs_in_week(db, user, plan, 1, distance_km=9.0, effort=8)
        _log_runs_in_week(db, user, plan, 2, distance_km=9.0, effort=8)

        result = adjust_plan(plan.id, user.id, db)
        assert result["adjusted"] is True

        db.expire_all()
        plan = db.query(TrainingPlan).filter(TrainingPlan.id == plan.id).one()
        plan_data = plan.plan_data
        for wk in range(4, 9):  # week 4..8: adjustable
            week_data = next(w for w in plan_data if w["week"] == wk)
            json_sum = round(
                sum(wo["distance"] for wo in week_data["daily_workouts"]),
                1,
            )
            assert json_sum == week_data["total_km"], (
                f"week {wk}: JSON daily sum {json_sum} != total_km "
                f"{week_data['total_km']}"
            )

            wp = (
                db.query(WeeklyPlan)
                .filter(
                    WeeklyPlan.training_plan_id == plan.id,
                    WeeklyPlan.week_number == wk,
                )
                .one()
            )
            orm_distances = {
                wo.day_of_week: wo.distance_km
                for wo in db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == wp.id)
                .all()
            }
            for wo in week_data["daily_workouts"]:
                assert wo["distance"] == orm_distances[wo["day"]], (
                    f"week {wk} day {wo['day']}: JSON {wo['distance']} != "
                    f"ORM {orm_distances[wo['day']]}"
                )
            assert wp.total_km == week_data["total_km"]
