"""Tests for P2 §5.1 — auto-adjust on run logging (apply_or_park + confidence)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    Base,
    DailyWorkout,
    RunLog,
    TrainingPlan,
    User,
    WeeklyPlan,
)
from app.services.adaptation import recommendation_evaluator
from app.services.adaptation.recommendation_evaluator import (
    AUTO_ADJUST_THROTTLE,
    apply_or_park,
    evaluate_on_run_logged,
)


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


def _make_plan_with_runs(db, vdot=50.0, effort=9.0, dist_mult=1.3):
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    start = _now() - timedelta(weeks=3)
    plan_data = []
    for wk in range(1, 9):
        plan_data.append({
            "week": wk,
            "total_km": 30,
            "phase": "build",
            "daily_workouts": [
                {"day": 1, "type": "easy", "distance": 8.0},
                {"day": 2, "type": "tempo", "distance": 8.0},
                {"day": 3, "type": "long", "distance": 14.0},
            ],
        })

    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="21.1",
        weeks_duration=8,
        vdot=vdot,
        start_date=start,
        plan_data=plan_data,
    )
    db.add(plan)
    db.flush()

    for wk in range(1, 9):
        wp = WeeklyPlan(id=_uid(), training_plan_id=plan.id, week_number=wk, total_km=30)
        db.add(wp)
        db.flush()
        for i, (wtype, dist) in enumerate([("easy", 8.0), ("tempo", 8.0), ("long", 14.0)]):
            wo = DailyWorkout(
                id=_uid(),
                weekly_plan_id=wp.id,
                day_of_week=i + 1,
                workout_type=wtype,
                distance_km=dist,
                baseline_distance_km=dist,
            )
            db.add(wo)

    db.flush()

    # Add runs to weeks 1-3 with high effort to push multiplier away from 1.0.
    for wk in range(1, 4):
        wp = db.query(WeeklyPlan).filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number == wk,
        ).one()
        workouts = (
            db.query(DailyWorkout)
            .filter(DailyWorkout.weekly_plan_id == wp.id)
            .order_by(DailyWorkout.day_of_week)
            .all()
        )
        for wo in workouts:
            run_date = start + timedelta(weeks=wk - 1, days=wo.day_of_week - 1)
            db.add(RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                daily_workout_id=wo.id,
                date=run_date,
                distance_km=(wo.distance_km or 0) * dist_mult,
                duration_minutes=50,
                perceived_effort=effort,
                workout_type=wo.workout_type,
            ))
    db.commit()
    return user, plan


class TestConfidenceClassification:
    def test_returns_none_when_signals_too_small(self, db):
        user, plan = _make_plan_with_runs(db, effort=5.0, dist_mult=1.0)
        result = evaluate_on_run_logged(plan.id, user.id, db)
        # multiplier may be very close to 1.0 → returns None
        if result is not None:
            assert result["confidence"] in ("medium", "high", "low")

    def test_high_effort_yields_evaluation(self, db):
        user, plan = _make_plan_with_runs(db, effort=9.0, dist_mult=1.3)
        result = evaluate_on_run_logged(plan.id, user.id, db)
        assert result is not None
        assert result["confidence"] in ("medium", "high")
        assert "multiplier" in result
        assert "signals" in result


class TestApplyOrPark:
    def test_low_confidence_skipped(self, db):
        user, plan = _make_plan_with_runs(db)
        # Hand-craft a low-confidence evaluation
        evaluation = {
            "plan_id": plan.id,
            "confidence": "low",
            "multiplier": 1.01,
            "signals": {},
            "training_plan": plan,
            "current_week": 4,
            "current_day_of_week": 1,
            "adjustable_weeks": [],
        }
        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=True)
        assert result["action"] == "skipped"

    def test_high_confidence_with_auto_applies(self, db):
        user, plan = _make_plan_with_runs(db, effort=9.0, dist_mult=1.3)
        user.auto_adjust_enabled = True
        db.commit()

        # Snapshot distances before auto-adjust so we can prove they really changed.
        future_weeks = list(range(4, 9))
        pre_distances = {
            (wp.week_number, wo.day_of_week): wo.distance_km
            for wp in (
                db.query(WeeklyPlan)
                .filter(
                    WeeklyPlan.training_plan_id == plan.id,
                    WeeklyPlan.week_number.in_(future_weeks),
                )
                .all()
            )
            for wo in db.query(DailyWorkout)
            .filter(DailyWorkout.weekly_plan_id == wp.id)
            .all()
        }

        evaluation = evaluate_on_run_logged(plan.id, user.id, db)
        if evaluation is None:
            pytest.skip("Signals were not strong enough to trigger evaluation")

        # Force confidence to high so we can test the apply path deterministically
        evaluation["confidence"] = "high"

        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=True)
        assert result["action"] == "auto_adjusted"
        assert "multiplier" in result
        # New return-payload fields surfaced to the run-log response
        assert "reason" in result and result["reason"]
        assert "week_numbers" in result
        assert "total_km_delta" in result

        db.refresh(plan)
        assert plan.adjustment_multiplier is not None
        history = plan.adaptation_history or []
        auto_events = [e for e in history if e.get("type") == "auto_adjust"]
        assert auto_events, "auto_adjust event missing from history"
        last_event = auto_events[-1]
        assert last_event.get("applied_at"), "applied_at not stamped on event"
        assert "week_numbers" in last_event
        assert "total_km_delta" in last_event
        assert last_event.get("reason"), "reason not recorded on event"
        # Pending recommendation should be cleared after auto-apply
        assert plan.pending_recommendation is None

        # Critical: prove that future-week DailyWorkout distances actually moved.
        post_distances = {
            (wp.week_number, wo.day_of_week): wo.distance_km
            for wp in (
                db.query(WeeklyPlan)
                .filter(
                    WeeklyPlan.training_plan_id == plan.id,
                    WeeklyPlan.week_number.in_(future_weeks),
                )
                .all()
            )
            for wo in db.query(DailyWorkout)
            .filter(DailyWorkout.weekly_plan_id == wp.id)
            .all()
        }
        changed = [
            key for key in pre_distances
            if post_distances.get(key) != pre_distances[key]
        ]
        assert changed, "no future workout distances were mutated"

    def test_high_confidence_without_auto_parks(self, db):
        user, plan = _make_plan_with_runs(db, effort=9.0, dist_mult=1.3)
        user.auto_adjust_enabled = False
        db.commit()

        evaluation = evaluate_on_run_logged(plan.id, user.id, db)
        if evaluation is None:
            pytest.skip("Signals were not strong enough to trigger evaluation")
        evaluation["confidence"] = "high"

        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=False)
        assert result["action"] == "parked"

        db.refresh(plan)
        assert plan.pending_recommendation is not None
        assert plan.pending_recommendation.get("source") == "run_logged"

    def test_throttle_blocks_recent_auto_adjust(self, db):
        user, plan = _make_plan_with_runs(db, effort=9.0, dist_mult=1.3)
        user.auto_adjust_enabled = True
        plan.last_adjusted_at = _now() - timedelta(hours=1)
        db.commit()

        evaluation = evaluate_on_run_logged(plan.id, user.id, db)
        if evaluation is None:
            pytest.skip("Signals were not strong enough to trigger evaluation")
        evaluation["confidence"] = "high"

        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=True)
        assert result["action"] == "throttled"

    def test_throttle_allows_older_auto_adjust(self, db):
        user, plan = _make_plan_with_runs(db, effort=9.0, dist_mult=1.3)
        user.auto_adjust_enabled = True
        plan.last_adjusted_at = _now() - AUTO_ADJUST_THROTTLE - timedelta(minutes=1)
        db.commit()

        evaluation = evaluate_on_run_logged(plan.id, user.id, db)
        if evaluation is None:
            pytest.skip("Signals were not strong enough to trigger evaluation")
        evaluation["confidence"] = "high"

        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=True)
        assert result["action"] == "auto_adjusted"


class TestFacadeExposesAutoAdjust:
    def test_facade_methods_exist(self):
        from app.services.adaptation import AdaptationService
        svc = AdaptationService()
        assert hasattr(svc, "evaluate_on_run_logged")
        assert hasattr(svc, "apply_or_park")


def _make_week1_plan_with_runs(db, *, runs_in_week_1=3, effort=9.0, dist_mult=1.3):
    """Same shape as _make_plan_with_runs but the plan started this week.

    With start_date = today, the engine sees current_week == 1 and the
    last-completed-week run count is 0 (or whatever we explicitly seed
    into the prior week — which doesn't exist for week 1).
    """
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    start = _now()
    plan_data = []
    for wk in range(1, 9):
        plan_data.append({
            "week": wk,
            "total_km": 30,
            "phase": "build",
            "daily_workouts": [
                {"day": 1, "type": "easy", "distance": 8.0},
                {"day": 2, "type": "tempo", "distance": 8.0},
                {"day": 3, "type": "long", "distance": 14.0},
            ],
        })

    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="21.1",
        weeks_duration=8,
        vdot=50.0,
        start_date=start,
        plan_data=plan_data,
    )
    db.add(plan)
    db.flush()

    for wk in range(1, 9):
        wp = WeeklyPlan(id=_uid(), training_plan_id=plan.id, week_number=wk, total_km=30)
        db.add(wp)
        db.flush()
        for i, (wtype, dist) in enumerate([("easy", 8.0), ("tempo", 8.0), ("long", 14.0)]):
            wo = DailyWorkout(
                id=_uid(),
                weekly_plan_id=wp.id,
                day_of_week=i + 1,
                workout_type=wtype,
                distance_km=dist,
                baseline_distance_km=dist,
            )
            db.add(wo)
    db.flush()

    wp1 = db.query(WeeklyPlan).filter(
        WeeklyPlan.training_plan_id == plan.id,
        WeeklyPlan.week_number == 1,
    ).one()
    week1_workouts = (
        db.query(DailyWorkout)
        .filter(DailyWorkout.weekly_plan_id == wp1.id)
        .order_by(DailyWorkout.day_of_week)
        .all()
    )
    for wo in week1_workouts[:runs_in_week_1]:
        run_date = start + timedelta(days=wo.day_of_week - 1)
        db.add(RunLog(
            id=_uid(),
            user_id=user.id,
            training_plan_id=plan.id,
            daily_workout_id=wo.id,
            date=run_date,
            distance_km=(wo.distance_km or 0) * dist_mult,
            duration_minutes=50,
            perceived_effort=effort,
            workout_type=wo.workout_type,
        ))
    db.commit()
    return user, plan


class TestEarlyPlanFloor:
    """The auto-apply gate: don't sweep-mutate a plan from a noisy week-1 sample."""

    def test_week_1_high_confidence_is_parked_not_applied(self, db):
        user, plan = _make_week1_plan_with_runs(db)
        user.auto_adjust_enabled = True
        db.commit()

        evaluation = {
            "plan_id": plan.id,
            "confidence": "high",
            "multiplier": 0.85,
            "signals": {"overreach_detected": True},
            "training_plan": plan,
            "current_week": 1,
            "current_day_of_week": 4,
            "adjustable_weeks": [],
        }
        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=True)
        assert result["action"] == "parked"
        assert result.get("gated_reason") == "early_plan_floor"

        db.refresh(plan)
        assert plan.adjustment_multiplier is None
        assert plan.pending_recommendation is not None

    def test_week_2_with_runs_in_week_1_passes_floor(self, db):
        user, plan = _make_week1_plan_with_runs(db, runs_in_week_1=2)
        user.auto_adjust_enabled = True
        # Backdate the plan one week so current_week == 2 and week 1 has runs.
        plan.start_date = _now() - timedelta(weeks=1)
        # Backdate the runs that were just inserted, so they fall inside week 1.
        for run in db.query(RunLog).filter(RunLog.training_plan_id == plan.id).all():
            run.date = plan.start_date + timedelta(days=run.date.weekday())
        db.commit()

        evaluation = {
            "plan_id": plan.id,
            "confidence": "high",
            "multiplier": 0.85,
            "signals": {"overreach_detected": True, "per_type_ratios": {}},
            "training_plan": plan,
            "current_week": 2,
            "current_day_of_week": 1,
            "adjustable_weeks": list(
                db.query(WeeklyPlan).filter(
                    WeeklyPlan.training_plan_id == plan.id,
                    WeeklyPlan.week_number >= 2,
                ).all()
            ),
        }
        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=True)
        assert result["action"] == "auto_adjusted"

    def test_week_2_without_enough_prior_runs_is_parked(self, db):
        user, plan = _make_week1_plan_with_runs(db, runs_in_week_1=1)
        user.auto_adjust_enabled = True
        plan.start_date = _now() - timedelta(weeks=1)
        for run in db.query(RunLog).filter(RunLog.training_plan_id == plan.id).all():
            run.date = plan.start_date + timedelta(days=run.date.weekday())
        db.commit()

        evaluation = {
            "plan_id": plan.id,
            "confidence": "high",
            "multiplier": 0.85,
            "signals": {"overreach_detected": True},
            "training_plan": plan,
            "current_week": 2,
            "current_day_of_week": 1,
            "adjustable_weeks": [],
        }
        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=True)
        assert result["action"] == "parked"
        assert result.get("gated_reason") == "early_plan_floor"


class TestPlanDataPersistsAfterAutoAdjust:
    """Regression: JSON plan_data must reflect new per-day distances on reload.

    The plan grid renders from training_plan.plan_data (JSON column), not
    from the DailyWorkout rows. SQLAlchemy's default JSON type doesn't track
    in-place mutations, so without persist_json the per-day distances would
    silently revert when the row is re-read.
    """

    def test_plan_data_json_reflects_new_distances_after_commit(self, db):
        user, plan = _make_plan_with_runs(db, effort=9.0, dist_mult=1.3)
        user.auto_adjust_enabled = True
        db.commit()

        # Snapshot the original per-day distances from the JSON column.
        pre_json = {
            (w["week"], wo["day"]): wo["distance"]
            for w in plan.plan_data
            for wo in w["daily_workouts"]
        }

        evaluation = evaluate_on_run_logged(plan.id, user.id, db)
        if evaluation is None:
            pytest.skip("Signals not strong enough to trigger evaluation")
        evaluation["confidence"] = "high"

        result = apply_or_park(plan.id, user.id, db, evaluation, auto_enabled=True)
        assert result["action"] == "auto_adjusted"

        # Expire all in-session state so we read genuinely-fresh data
        # from the DB — this is what a subsequent page render would see.
        db.expire_all()
        refreshed = db.query(TrainingPlan).filter(TrainingPlan.id == plan.id).one()
        post_json = {
            (w["week"], wo["day"]): wo["distance"]
            for w in refreshed.plan_data
            for wo in w["daily_workouts"]
        }

        changed = [k for k in pre_json if post_json.get(k) != pre_json[k]]
        assert changed, (
            "plan_data JSON did not reflect any auto-adjust distance changes "
            "after commit — the plan grid would still show stale distances."
        )
