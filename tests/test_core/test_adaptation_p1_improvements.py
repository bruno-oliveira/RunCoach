"""Tests for P1 adaptation improvements: continuous completion factor, importance-weighted volume, dynamic multiplier range."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation.signal_computer import (
    _CONSECUTIVE_THRESHOLD,
    _EXPANDED_MAX,
    _EXPANDED_MIN,
    _IMPORTANCE_WEIGHTS,
    _STANDARD_MAX,
    _STANDARD_MIN,
    _count_consecutive_direction,
)
from app.contexts.plan.adaptation.signal_computer import (
    compute_adjustment_signals as _compute_adjustment_signals,
)
from app.models import Base, DailyWorkout, RunLog, TrainingPlan, User, WeeklyPlan


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _today():
    return datetime.now(timezone.utc).replace(tzinfo=None).date()


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


def _create_plan_with_phases(
    db: Session,
    *,
    weeks: int = 12,
    weeks_ago: int = 0,
    phases: dict | None = None,
    workout_types: list[str] | None = None,
):
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    start = _now() - timedelta(weeks=weeks_ago) if weeks_ago else _now()

    if phases is None:
        phases = {}
    if workout_types is None:
        workout_types = ["easy", "tempo", "interval", "long"]

    plan_data = []
    for wk in range(1, weeks + 1):
        phase = phases.get(wk, "build")
        week_data = {
            "week": wk,
            "total_km": 35,
            "phase": phase,
            "daily_workouts": [],
        }
        for i, wtype in enumerate(workout_types):
            week_data["daily_workouts"].append(
                {
                    "day": i + 1,
                    "type": wtype,
                    "distance": 8.0 if wtype != "long" else 14.0,
                }
            )
        plan_data.append(week_data)

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
            id=_uid(),
            training_plan_id=plan.id,
            week_number=wk,
            total_km=35,
        )
        db.add(wp)
        db.flush()

        for i, wtype in enumerate(workout_types):
            dw = DailyWorkout(
                id=_uid(),
                weekly_plan_id=wp.id,
                day_of_week=i + 1,
                workout_type=wtype,
                distance_km=8.0 if wtype != "long" else 14.0,
                baseline_distance_km=8.0 if wtype != "long" else 14.0,
            )
            db.add(dw)

    db.commit()
    return user, plan


def _add_runs_for_weeks(
    db: Session,
    plan: TrainingPlan,
    user: User,
    weeks: list[int],
    *,
    effort: float | None = None,
    distance_multiplier: float = 1.0,
    workout_types: list[str] | None = None,
):
    if workout_types is None:
        workout_types = ["easy", "tempo", "interval", "long"]

    for wk in weeks:
        wp = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan.id,
                WeeklyPlan.week_number == wk,
            )
            .one()
        )
        workouts = (
            db.query(DailyWorkout)
            .filter(DailyWorkout.weekly_plan_id == wp.id)
            .order_by(DailyWorkout.day_of_week)
            .all()
        )
        for i, wo in enumerate(workouts):
            if i >= len(workout_types):
                continue
            if wo.workout_type != workout_types[i]:
                continue
            run_date = plan.start_date + timedelta(
                weeks=wp.week_number - 1, days=wo.day_of_week - 1
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


def _build_signals_context(
    db,
    plan,
    user,
    weeks,
    *,
    effort=5.0,
    distance_multiplier=1.0,
    current_phase="build",
    workout_types=None,
):
    """Helper to build all inputs needed for compute_adjustment_signals."""
    if workout_types is None:
        workout_types = ["easy", "tempo", "interval", "long"]

    _add_runs_for_weeks(
        db,
        plan,
        user,
        weeks,
        effort=effort,
        distance_multiplier=distance_multiplier,
        workout_types=workout_types,
    )

    today = _today()
    start = (
        plan.start_date.date() if hasattr(plan.start_date, "date") else plan.start_date
    )

    past_workouts = []
    past_workout_ids = set()
    for wk in weeks:
        wp = (
            db.query(WeeklyPlan)
            .filter(
                WeeklyPlan.training_plan_id == plan.id,
                WeeklyPlan.week_number == wk,
            )
            .one()
        )
        workouts = (
            db.query(DailyWorkout).filter(DailyWorkout.weekly_plan_id == wp.id).all()
        )
        for wo in workouts:
            sched_date = start + timedelta(weeks=wk - 1, days=wo.day_of_week - 1)
            if sched_date <= today:
                past_workouts.append((wo, sched_date))
                past_workout_ids.add(wo.id)

    def _recency_weight(scheduled_date):
        weeks_ago = max(0, (today - scheduled_date).days) / 7.0
        return 2.0 ** (-weeks_ago / 3.0)

    all_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan.id).all()

    signals = _compute_adjustment_signals(
        all_runs,
        past_workouts,
        past_workout_ids,
        today,
        plan.id,
        db,
        _recency_weight,
        current_phase=current_phase,
    )
    return signals


class TestImportanceWeights:
    """Verify importance weight constants."""

    def test_all_expected_types_present(self):
        expected = {
            "long",
            "tempo",
            "interval",
            "vo2max",
            "race_pace",
            "hill",
            "fartlek",
            "easy",
            "recovery",
        }
        assert set(_IMPORTANCE_WEIGHTS.keys()) == expected

    def test_long_has_highest_weight(self):
        assert _IMPORTANCE_WEIGHTS["long"] == 1.5

    def test_tempo_interval_vo2max_race_pace_equal(self):
        val = _IMPORTANCE_WEIGHTS["tempo"]
        assert _IMPORTANCE_WEIGHTS["interval"] == val
        assert _IMPORTANCE_WEIGHTS["vo2max"] == val
        assert _IMPORTANCE_WEIGHTS["race_pace"] == val
        assert val == 1.3

    def test_easy_has_baseline_weight(self):
        assert _IMPORTANCE_WEIGHTS["easy"] == 1.0

    def test_recovery_has_lowest_weight(self):
        assert _IMPORTANCE_WEIGHTS["recovery"] == 0.5

    def test_hill_weight_between_easy_and_tempo(self):
        assert (
            _IMPORTANCE_WEIGHTS["recovery"]
            < _IMPORTANCE_WEIGHTS["hill"]
            < _IMPORTANCE_WEIGHTS["tempo"]
        )

    def test_fartlek_weight_between_easy_and_hill(self):
        assert (
            _IMPORTANCE_WEIGHTS["easy"]
            < _IMPORTANCE_WEIGHTS["fartlek"]
            < _IMPORTANCE_WEIGHTS["hill"]
        )


class TestContinuousCompletionFactor:
    """Test continuous completion factor mapping."""

    def test_zero_completion_yields_090(self, db):
        user, plan = _create_plan_with_phases(db, weeks=4, weeks_ago=2)
        _add_runs_for_weeks(db, plan, user, [1], effort=5.0, distance_multiplier=1.0)

        today = _today()
        start = (
            plan.start_date.date()
            if hasattr(plan.start_date, "date")
            else plan.start_date
        )

        past_workouts = []
        past_workout_ids = set()
        for wk in [1, 2]:
            wp = (
                db.query(WeeklyPlan)
                .filter(
                    WeeklyPlan.training_plan_id == plan.id,
                    WeeklyPlan.week_number == wk,
                )
                .one()
            )
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == wp.id)
                .all()
            )
            for wo in workouts:
                sched_date = start + timedelta(weeks=wk - 1, days=wo.day_of_week - 1)
                if sched_date <= today:
                    past_workouts.append((wo, sched_date))
                    past_workout_ids.add(wo.id)

        def _recency_weight(scheduled_date):
            weeks_ago = max(0, (today - scheduled_date).days) / 7.0
            return 2.0 ** (-weeks_ago / 3.0)

        all_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan.id).all()

        signals = _compute_adjustment_signals(
            all_runs,
            past_workouts,
            past_workout_ids,
            today,
            plan.id,
            db,
            _recency_weight,
            current_phase="build",
        )

        rate = signals["completion_rate"]
        factor = signals["completion_factor"]
        expected = round(0.90 + 0.15 * rate, 2)
        assert abs(factor - expected) < 0.01

    def test_full_completion_yields_105(self, db):
        user, plan = _create_plan_with_phases(db, weeks=4, weeks_ago=2)
        _add_runs_for_weeks(db, plan, user, [1, 2], effort=5.0, distance_multiplier=1.0)

        today = _today()
        start = (
            plan.start_date.date()
            if hasattr(plan.start_date, "date")
            else plan.start_date
        )

        past_workouts = []
        past_workout_ids = set()
        for wk in [1, 2]:
            wp = (
                db.query(WeeklyPlan)
                .filter(
                    WeeklyPlan.training_plan_id == plan.id,
                    WeeklyPlan.week_number == wk,
                )
                .one()
            )
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == wp.id)
                .all()
            )
            for wo in workouts:
                sched_date = start + timedelta(weeks=wk - 1, days=wo.day_of_week - 1)
                if sched_date <= today:
                    past_workouts.append((wo, sched_date))
                    past_workout_ids.add(wo.id)

        def _recency_weight(scheduled_date):
            weeks_ago = max(0, (today - scheduled_date).days) / 7.0
            return 2.0 ** (-weeks_ago / 3.0)

        all_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan.id).all()

        signals = _compute_adjustment_signals(
            all_runs,
            past_workouts,
            past_workout_ids,
            today,
            plan.id,
            db,
            _recency_weight,
            current_phase="build",
        )

        rate = signals["completion_rate"]
        factor = signals["completion_factor"]
        expected = round(0.90 + 0.15 * rate, 2)
        assert abs(factor - expected) < 0.01

    def test_completion_factor_is_smooth_not_stepped(self, db):
        """Completion factor should change smoothly, not in discrete steps."""
        user, plan = _create_plan_with_phases(db, weeks=8, weeks_ago=4)

        today = _today()
        start = (
            plan.start_date.date()
            if hasattr(plan.start_date, "date")
            else plan.start_date
        )

        past_workouts = []
        past_workout_ids = set()
        for wk in [1, 2, 3]:
            wp = (
                db.query(WeeklyPlan)
                .filter(
                    WeeklyPlan.training_plan_id == plan.id,
                    WeeklyPlan.week_number == wk,
                )
                .one()
            )
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == wp.id)
                .all()
            )
            for wo in workouts:
                sched_date = start + timedelta(weeks=wk - 1, days=wo.day_of_week - 1)
                if sched_date <= today:
                    past_workouts.append((wo, sched_date))
                    past_workout_ids.add(wo.id)

        def _recency_weight(scheduled_date):
            weeks_ago = max(0, (today - scheduled_date).days) / 7.0
            return 2.0 ** (-weeks_ago / 3.0)

        for multiplier in [0.5, 0.7, 0.89]:
            _add_runs_for_weeks(
                db, plan, user, [1, 2, 3], effort=5.0, distance_multiplier=multiplier
            )

            all_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan.id).all()

            signals = _compute_adjustment_signals(
                all_runs,
                past_workouts,
                past_workout_ids,
                today,
                plan.id,
                db,
                _recency_weight,
                current_phase="build",
            )

            rate = signals["completion_rate"]
            factor = signals["completion_factor"]
            expected = round(0.90 + 0.15 * rate, 2)
            assert abs(factor - expected) < 0.01, (
                f"Failed at multiplier={multiplier}: factor={factor}, expected={expected}"
            )

    def test_completion_factor_range(self, db):
        """Factor should range from 0.90 (0% completion) to 1.05 (100% completion)."""
        user, plan = _create_plan_with_phases(db, weeks=4, weeks_ago=2)
        _add_runs_for_weeks(db, plan, user, [1], effort=5.0, distance_multiplier=1.0)

        today = _today()
        start = (
            plan.start_date.date()
            if hasattr(plan.start_date, "date")
            else plan.start_date
        )

        past_workouts = []
        past_workout_ids = set()
        for wk in [1, 2, 3, 4]:
            wp = (
                db.query(WeeklyPlan)
                .filter(
                    WeeklyPlan.training_plan_id == plan.id,
                    WeeklyPlan.week_number == wk,
                )
                .one()
            )
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == wp.id)
                .all()
            )
            for wo in workouts:
                sched_date = start + timedelta(weeks=wk - 1, days=wo.day_of_week - 1)
                if sched_date <= today:
                    past_workouts.append((wo, sched_date))
                    past_workout_ids.add(wo.id)

        def _recency_weight(scheduled_date):
            weeks_ago = max(0, (today - scheduled_date).days) / 7.0
            return 2.0 ** (-weeks_ago / 3.0)

        all_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan.id).all()

        signals = _compute_adjustment_signals(
            all_runs,
            past_workouts,
            past_workout_ids,
            today,
            plan.id,
            db,
            _recency_weight,
            current_phase="build",
        )

        assert 0.90 <= signals["completion_factor"] <= 1.05


class TestImportanceWeightedVolume:
    """Test that volume ratio accounts for workout importance."""

    def test_missing_long_run_penalizes_more_than_missing_easy(self):
        """When long runs are missed, volume ratio should be lower than when easy runs are missed."""

        class MockWorkout:
            def __init__(self, wtype, dist):
                self.workout_type = wtype
                self.distance_km = dist
                self.baseline_distance_km = dist
                self.id = _uid()

        class MockRun:
            def __init__(self, wtype, dist, daily_workout_id):
                self.workout_type = wtype
                self.distance_km = dist
                self.perceived_effort = 5.0
                self.date = _today()
                self.daily_workout_id = daily_workout_id

            @property
            def effective_workout_type(self):
                return self.workout_type

        today = _today()

        def _recency_weight(scheduled_date):
            return 1.0

        planned_workouts = [
            (MockWorkout("easy", 8.0), today),
            (MockWorkout("tempo", 8.0), today),
            (MockWorkout("interval", 8.0), today),
            (MockWorkout("long", 14.0), today),
        ]
        planned_ids = {wo[0].id for wo in planned_workouts}

        runs_all = [
            MockRun(wt, dist, wo[0].id)
            for (wt, dist), wo in zip(
                [("easy", 8.0), ("tempo", 8.0), ("interval", 8.0), ("long", 14.0)],
                planned_workouts,
            )
        ]
        runs_no_long = [
            MockRun(wt, dist, wo[0].id)
            for (wt, dist), wo in zip(
                [("easy", 8.0), ("tempo", 8.0), ("interval", 8.0)],
                planned_workouts,
            )
        ]

        def _make_db(completed_runs):
            class MockDB:
                def query(self, *args):
                    class MockQuery:
                        def __init__(self):
                            self._completed = completed_runs

                        def filter(self, *args):
                            return self

                        def all(self):
                            return [(r.daily_workout_id,) for r in self._completed]

                    return MockQuery()

            return MockDB()

        signals_all = _compute_adjustment_signals(
            runs_all,
            planned_workouts,
            planned_ids,
            today,
            "plan1",
            _make_db(runs_all),
            _recency_weight,
            current_phase="build",
        )

        signals_no_long = _compute_adjustment_signals(
            runs_no_long,
            planned_workouts,
            planned_ids,
            today,
            "plan1",
            _make_db(runs_no_long),
            _recency_weight,
            current_phase="build",
        )

        assert signals_no_long["volume_ratio"] < signals_all["volume_ratio"]

    def test_extra_long_run_boosts_ratio_more_than_extra_easy(self, db):
        """Doing extra long distance should boost volume ratio more than extra easy distance."""
        user, plan = _create_plan_with_phases(db, weeks=6, weeks_ago=4)

        signals_long_boost = _build_signals_context(
            db,
            plan,
            user,
            [1, 2, 3],
            effort=5.0,
            distance_multiplier=1.3,
            workout_types=["easy", "tempo", "interval", "long"],
        )

        signals_easy_boost = _build_signals_context(
            db,
            plan,
            user,
            [1, 2, 3],
            effort=5.0,
            distance_multiplier=1.3,
            workout_types=["easy", "tempo", "interval", "long"],
        )

        assert signals_long_boost["volume_ratio"] > 1.0
        assert signals_easy_boost["volume_ratio"] > 1.0

    def test_recovery_runs_count_less(self, db):
        """Recovery runs should contribute less to volume signal."""
        user, plan = _create_plan_with_phases(
            db,
            weeks=6,
            weeks_ago=4,
            workout_types=["easy", "recovery", "tempo", "long"],
        )

        _build_signals_context(
            db,
            plan,
            user,
            [1, 2, 3],
            effort=5.0,
            distance_multiplier=1.0,
            workout_types=["easy", "recovery", "tempo", "long"],
        )

        assert "recovery" in _IMPORTANCE_WEIGHTS
        assert _IMPORTANCE_WEIGHTS["recovery"] < _IMPORTANCE_WEIGHTS["easy"]


class TestDynamicMultiplierRange:
    """Test dynamic multiplier range expansion based on consecutive adjustments."""

    def test_constants_defined(self):
        assert _CONSECUTIVE_THRESHOLD == 3
        assert _EXPANDED_MIN == 0.70
        assert _EXPANDED_MAX == 1.25
        assert _STANDARD_MIN == 0.85
        assert _STANDARD_MAX == 1.15

    def test_no_history_uses_standard_range(self, db):
        user, plan = _create_plan_with_phases(db, weeks=4, weeks_ago=2)

        signals = _build_signals_context(
            db, plan, user, [1, 2, 3], effort=5.0, distance_multiplier=1.0
        )

        assert signals["consecutive_same_direction"] == 0
        assert signals["expanded_range"] is False
        assert _STANDARD_MIN <= signals["multiplier"] <= _STANDARD_MAX

    def test_fewer_than_threshold_uses_standard_range(self, db):
        user, plan = _create_plan_with_phases(db, weeks=4, weeks_ago=2)

        history = [
            {"type": "adjust", "direction": "reduced", "multiplier": 0.90},
            {"type": "adjust", "direction": "reduced", "multiplier": 0.88},
        ]

        today = _today()
        start = (
            plan.start_date.date()
            if hasattr(plan.start_date, "date")
            else plan.start_date
        )

        past_workouts = []
        past_workout_ids = set()
        for wk in [1, 2, 3]:
            wp = (
                db.query(WeeklyPlan)
                .filter(
                    WeeklyPlan.training_plan_id == plan.id,
                    WeeklyPlan.week_number == wk,
                )
                .one()
            )
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == wp.id)
                .all()
            )
            for wo in workouts:
                sched_date = start + timedelta(weeks=wk - 1, days=wo.day_of_week - 1)
                if sched_date <= today:
                    past_workouts.append((wo, sched_date))
                    past_workout_ids.add(wo.id)

        def _recency_weight(scheduled_date):
            weeks_ago = max(0, (today - scheduled_date).days) / 7.0
            return 2.0 ** (-weeks_ago / 3.0)

        all_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan.id).all()

        signals = _compute_adjustment_signals(
            all_runs,
            past_workouts,
            past_workout_ids,
            today,
            plan.id,
            db,
            _recency_weight,
            current_phase="build",
            adaptation_history=history,
        )

        assert signals["consecutive_same_direction"] == 2
        assert signals["expanded_range"] is False

    def test_three_consecutive_reductions_expands_range(self, db):
        user, plan = _create_plan_with_phases(db, weeks=4, weeks_ago=2)

        history = [
            {"type": "adjust", "direction": "reduced", "multiplier": 0.90},
            {"type": "adjust", "direction": "reduced", "multiplier": 0.88},
            {"type": "adjust", "direction": "reduced", "multiplier": 0.86},
        ]

        today = _today()
        start = (
            plan.start_date.date()
            if hasattr(plan.start_date, "date")
            else plan.start_date
        )

        past_workouts = []
        past_workout_ids = set()
        for wk in [1, 2, 3]:
            wp = (
                db.query(WeeklyPlan)
                .filter(
                    WeeklyPlan.training_plan_id == plan.id,
                    WeeklyPlan.week_number == wk,
                )
                .one()
            )
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == wp.id)
                .all()
            )
            for wo in workouts:
                sched_date = start + timedelta(weeks=wk - 1, days=wo.day_of_week - 1)
                if sched_date <= today:
                    past_workouts.append((wo, sched_date))
                    past_workout_ids.add(wo.id)

        def _recency_weight(scheduled_date):
            weeks_ago = max(0, (today - scheduled_date).days) / 7.0
            return 2.0 ** (-weeks_ago / 3.0)

        all_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan.id).all()

        signals = _compute_adjustment_signals(
            all_runs,
            past_workouts,
            past_workout_ids,
            today,
            plan.id,
            db,
            _recency_weight,
            current_phase="build",
            adaptation_history=history,
        )

        assert signals["consecutive_same_direction"] == 3
        assert signals["expanded_range"] is True
        assert _EXPANDED_MIN <= signals["multiplier"] <= _EXPANDED_MAX

    def test_three_consecutive_increases_expands_range(self, db):
        user, plan = _create_plan_with_phases(db, weeks=4, weeks_ago=2)

        history = [
            {"type": "adjust", "direction": "increased", "multiplier": 1.05},
            {"type": "adjust", "direction": "increased", "multiplier": 1.08},
            {"type": "adjust", "direction": "increased", "multiplier": 1.10},
        ]

        today = _today()
        start = (
            plan.start_date.date()
            if hasattr(plan.start_date, "date")
            else plan.start_date
        )

        past_workouts = []
        past_workout_ids = set()
        for wk in [1, 2, 3]:
            wp = (
                db.query(WeeklyPlan)
                .filter(
                    WeeklyPlan.training_plan_id == plan.id,
                    WeeklyPlan.week_number == wk,
                )
                .one()
            )
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == wp.id)
                .all()
            )
            for wo in workouts:
                sched_date = start + timedelta(weeks=wk - 1, days=wo.day_of_week - 1)
                if sched_date <= today:
                    past_workouts.append((wo, sched_date))
                    past_workout_ids.add(wo.id)

        def _recency_weight(scheduled_date):
            weeks_ago = max(0, (today - scheduled_date).days) / 7.0
            return 2.0 ** (-weeks_ago / 3.0)

        all_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan.id).all()

        signals = _compute_adjustment_signals(
            all_runs,
            past_workouts,
            past_workout_ids,
            today,
            plan.id,
            db,
            _recency_weight,
            current_phase="build",
            adaptation_history=history,
        )

        assert signals["consecutive_same_direction"] == 3
        assert signals["expanded_range"] is True

    def test_mixed_directions_resets_counter(self, db):
        user, plan = _create_plan_with_phases(db, weeks=4, weeks_ago=2)

        history = [
            {"type": "adjust", "direction": "reduced", "multiplier": 0.90},
            {"type": "adjust", "direction": "increased", "multiplier": 1.02},
            {"type": "adjust", "direction": "reduced", "multiplier": 0.92},
        ]

        today = _today()
        start = (
            plan.start_date.date()
            if hasattr(plan.start_date, "date")
            else plan.start_date
        )

        past_workouts = []
        past_workout_ids = set()
        for wk in [1, 2, 3]:
            wp = (
                db.query(WeeklyPlan)
                .filter(
                    WeeklyPlan.training_plan_id == plan.id,
                    WeeklyPlan.week_number == wk,
                )
                .one()
            )
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == wp.id)
                .all()
            )
            for wo in workouts:
                sched_date = start + timedelta(weeks=wk - 1, days=wo.day_of_week - 1)
                if sched_date <= today:
                    past_workouts.append((wo, sched_date))
                    past_workout_ids.add(wo.id)

        def _recency_weight(scheduled_date):
            weeks_ago = max(0, (today - scheduled_date).days) / 7.0
            return 2.0 ** (-weeks_ago / 3.0)

        all_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan.id).all()

        signals = _compute_adjustment_signals(
            all_runs,
            past_workouts,
            past_workout_ids,
            today,
            plan.id,
            db,
            _recency_weight,
            current_phase="build",
            adaptation_history=history,
        )

        assert signals["consecutive_same_direction"] == 1
        assert signals["expanded_range"] is False

    def test_kept_direction_breaks_streak(self, db):
        history = [
            {"type": "adjust", "direction": "reduced", "multiplier": 0.90},
            {"type": "adjust", "direction": "reduced", "multiplier": 0.88},
            {"type": "adjust", "direction": "kept", "multiplier": 1.00},
            {"type": "adjust", "direction": "reduced", "multiplier": 0.92},
        ]

        assert _count_consecutive_direction(history) == 1

    def test_five_consecutive_reductions_still_expanded(self, db):
        user, plan = _create_plan_with_phases(db, weeks=4, weeks_ago=2)

        history = [
            {"type": "adjust", "direction": "reduced", "multiplier": 0.90},
            {"type": "adjust", "direction": "reduced", "multiplier": 0.88},
            {"type": "adjust", "direction": "reduced", "multiplier": 0.86},
            {"type": "adjust", "direction": "reduced", "multiplier": 0.84},
            {"type": "adjust", "direction": "reduced", "multiplier": 0.82},
        ]

        today = _today()
        start = (
            plan.start_date.date()
            if hasattr(plan.start_date, "date")
            else plan.start_date
        )

        past_workouts = []
        past_workout_ids = set()
        for wk in [1, 2, 3]:
            wp = (
                db.query(WeeklyPlan)
                .filter(
                    WeeklyPlan.training_plan_id == plan.id,
                    WeeklyPlan.week_number == wk,
                )
                .one()
            )
            workouts = (
                db.query(DailyWorkout)
                .filter(DailyWorkout.weekly_plan_id == wp.id)
                .all()
            )
            for wo in workouts:
                sched_date = start + timedelta(weeks=wk - 1, days=wo.day_of_week - 1)
                if sched_date <= today:
                    past_workouts.append((wo, sched_date))
                    past_workout_ids.add(wo.id)

        def _recency_weight(scheduled_date):
            weeks_ago = max(0, (today - scheduled_date).days) / 7.0
            return 2.0 ** (-weeks_ago / 3.0)

        all_runs = db.query(RunLog).filter(RunLog.training_plan_id == plan.id).all()

        signals = _compute_adjustment_signals(
            all_runs,
            past_workouts,
            past_workout_ids,
            today,
            plan.id,
            db,
            _recency_weight,
            current_phase="build",
            adaptation_history=history,
        )

        assert signals["consecutive_same_direction"] == 5
        assert signals["expanded_range"] is True
        assert _EXPANDED_MIN <= signals["multiplier"] <= _EXPANDED_MAX


class TestCountConsecutiveDirection:
    """Test the _count_consecutive_direction helper."""

    def test_empty_history_returns_zero(self):
        assert _count_consecutive_direction([]) == 0

    def test_none_returns_zero(self):
        assert _count_consecutive_direction(None) == 0

    def test_single_reduction(self):
        history = [{"direction": "reduced"}]
        assert _count_consecutive_direction(history) == 1

    def test_single_increase(self):
        history = [{"direction": "increased"}]
        assert _count_consecutive_direction(history) == 1

    def test_two_reductions(self):
        history = [
            {"direction": "reduced"},
            {"direction": "reduced"},
        ]
        assert _count_consecutive_direction(history) == 2

    def test_three_reductions(self):
        history = [
            {"direction": "reduced"},
            {"direction": "reduced"},
            {"direction": "reduced"},
        ]
        assert _count_consecutive_direction(history) == 3

    def test_reduction_then_increase_resets(self):
        history = [
            {"direction": "reduced"},
            {"direction": "increased"},
        ]
        assert _count_consecutive_direction(history) == 1

    def test_two_reductions_then_increase(self):
        history = [
            {"direction": "reduced"},
            {"direction": "reduced"},
            {"direction": "increased"},
        ]
        assert _count_consecutive_direction(history) == 1

    def test_kept_breaks_streak(self):
        history = [
            {"direction": "reduced"},
            {"direction": "reduced"},
            {"direction": "kept"},
            {"direction": "reduced"},
        ]
        assert _count_consecutive_direction(history) == 1

    def test_older_events_ignored_after_break(self):
        history = [
            {"direction": "reduced"},
            {"direction": "reduced"},
            {"direction": "reduced"},
            {"direction": "increased"},
            {"direction": "reduced"},
        ]
        assert _count_consecutive_direction(history) == 1

    def test_non_adjust_events_skipped(self):
        """Events without a direction key are skipped, not counted."""
        history = [
            {"direction": "reduced"},
            {"direction": "reduced"},
            {"type": "recalibrate"},
        ]
        assert _count_consecutive_direction(history) == 2


class TestMountainSimulationSignal:
    """Mountain-from-flat proxy should influence multiplier when provided."""

    def test_low_simulation_score_reduces_multiplier_vs_high_score(self):
        class MockWorkout:
            def __init__(self, wid, wtype, dist):
                self.id = wid
                self.workout_type = wtype
                self.distance_km = dist
                self.baseline_distance_km = dist

        class MockRun:
            def __init__(self, wid, wtype, dist):
                self.daily_workout_id = wid
                self.workout_type = wtype
                self.distance_km = dist
                self.perceived_effort = 5.0
                self.date = _today()

            @property
            def effective_workout_type(self):
                return self.workout_type

        today = _today()

        def _recency_weight(_scheduled_date):
            return 1.0

        planned = [
            (MockWorkout(_uid(), "easy", 8.0), today),
            (MockWorkout(_uid(), "tempo", 8.0), today),
            (MockWorkout(_uid(), "long", 14.0), today),
        ]
        planned_ids = {w.id for w, _ in planned}
        runs = [MockRun(w.id, w.workout_type, w.distance_km) for w, _ in planned]

        class MockDB:
            def query(self, *_args):
                class MockQuery:
                    def filter(self, *_args):
                        return self

                    def all(self):
                        return [(r.daily_workout_id,) for r in runs]

                return MockQuery()

        base_args = [
            runs,
            planned,
            planned_ids,
            today,
            "plan1",
            MockDB(),
            _recency_weight,
        ]

        signals_low = _compute_adjustment_signals(
            *base_args,
            current_phase="build",
            mountain_simulation={"score": 40},
        )
        signals_high = _compute_adjustment_signals(
            *base_args,
            current_phase="build",
            mountain_simulation={"score": 90},
        )

        assert (
            signals_low["mountain_simulation_factor"]
            < signals_high["mountain_simulation_factor"]
        )
        assert signals_low["multiplier"] < signals_high["multiplier"]

    def test_missing_simulation_defaults_to_neutral_factor(self):
        class MockWorkout:
            def __init__(self, wid, wtype, dist):
                self.id = wid
                self.workout_type = wtype
                self.distance_km = dist
                self.baseline_distance_km = dist

        class MockRun:
            def __init__(self, wid, wtype, dist):
                self.daily_workout_id = wid
                self.workout_type = wtype
                self.distance_km = dist
                self.perceived_effort = 5.0
                self.date = _today()

            @property
            def effective_workout_type(self):
                return self.workout_type

        today = _today()

        def _recency_weight(_scheduled_date):
            return 1.0

        planned = [
            (MockWorkout(_uid(), "easy", 8.0), today),
            (MockWorkout(_uid(), "long", 14.0), today),
        ]
        planned_ids = {w.id for w, _ in planned}
        runs = [MockRun(w.id, w.workout_type, w.distance_km) for w, _ in planned]

        class MockDB:
            def query(self, *_args):
                class MockQuery:
                    def filter(self, *_args):
                        return self

                    def all(self):
                        return [(r.daily_workout_id,) for r in runs]

                return MockQuery()

        signals = _compute_adjustment_signals(
            runs,
            planned,
            planned_ids,
            today,
            "plan1",
            MockDB(),
            _recency_weight,
            current_phase="build",
        )

        assert signals["mountain_simulation_score"] is None
        assert signals["mountain_simulation_factor"] == 1.0
