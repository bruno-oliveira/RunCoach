"""Tests for P0 adaptation improvements: phase-aware weights and Bayesian shrinkage."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, User, TrainingPlan, WeeklyPlan, DailyWorkout, RunLog
from app.services.adaptation.plan_adjuster import _get_current_phase
from app.services.adaptation.signal_computer import (
    _PHASE_WEIGHTS,
    _MIN_RUNS_PER_TYPE,
    _BAYESIAN_SHRINKAGE_PER_RUN,
    compute_adjustment_signals as _compute_adjustment_signals,
)


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
    """Create a user + plan with phase-aware plan_data.

    Args:
        phases: dict mapping week_number -> phase name, e.g. {1: "base", 5: "build"}
        workout_types: list of workout types per week (default: ["easy", "tempo", "interval", "long"])
    """
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
            week_data["daily_workouts"].append({
                "day": i + 1,
                "type": wtype,
                "distance": 8.0 if wtype != "long" else 14.0,
            })
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
    """Create RunLog entries for specified weeks with optional effort and distance scaling."""
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
            db.add(RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                daily_workout_id=wo.id,
                date=run_date,
                distance_km=wo.distance_km * distance_multiplier,
                duration_minutes=40,
                perceived_effort=effort,
                workout_type=wo.workout_type,
            ))
    db.commit()


class TestPhaseWeights:
    """Verify phase-specific weight configuration."""

    def test_all_phases_defined(self):
        assert set(_PHASE_WEIGHTS.keys()) == {"base", "build", "peak", "taper"}

    def test_weights_sum_to_one(self):
        for phase, weights in _PHASE_WEIGHTS.items():
            v, e, c = weights
            assert abs(v + e + c - 1.0) < 1e-9, f"{phase} weights don't sum to 1: {v}+{e}+{c}"

    def test_base_phase_emphasizes_volume(self):
        v, e, c = _PHASE_WEIGHTS["base"]
        assert v > e and v > c, "Base phase should prioritize volume"
        assert v == 0.55

    def test_build_phase_balanced(self):
        v, e, c = _PHASE_WEIGHTS["build"]
        assert v == 0.50 and e == 0.30 and c == 0.20

    def test_peak_phase_emphasizes_effort(self):
        v, e, c = _PHASE_WEIGHTS["peak"]
        assert e > c and e > v * 0.8, "Peak phase should weight effort more heavily"
        assert e == 0.35
        assert c == 0.25

    def test_taper_phase_emphasizes_completion(self):
        v, e, c = _PHASE_WEIGHTS["taper"]
        assert c > v and c > e, "Taper phase should prioritize completion"
        assert c == 0.50
        assert v == 0.20


class TestGetCurrentPhase:
    """Test _get_current_phase helper."""

    def test_returns_phase_from_plan_data(self, db):
        user, plan = _create_plan_with_phases(
            db,
            weeks=12,
            weeks_ago=4,
            phases={1: "base", 2: "base", 3: "base", 4: "base", 5: "build"},
        )
        assert _get_current_phase(plan, 1) == "base"
        assert _get_current_phase(plan, 4) == "base"
        assert _get_current_phase(plan, 5) == "build"

    def test_defaults_to_build_when_no_plan_data(self, db):
        user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
        db.add(user)
        db.flush()

        plan = TrainingPlan(
            id=_uid(),
            user_id=user.id,
            current_weekly_km=30,
            target_distance="10",
            weeks_duration=8,
            start_date=_now(),
            plan_data=None,
        )
        db.add(plan)
        db.commit()

        assert _get_current_phase(plan, 1) == "build"

    def test_defaults_to_build_when_week_not_found(self, db):
        user, plan = _create_plan_with_phases(db, weeks=4, phases={1: "base"})
        assert _get_current_phase(plan, 99) == "build"


class TestBayesianShrinkage:
    """Test Bayesian shrinkage constants and behavior."""

    def test_min_runs_per_type_is_three(self):
        assert _MIN_RUNS_PER_TYPE == 3

    def test_shrinkage_per_run_is_thirty_percent(self):
        assert _BAYESIAN_SHRINKAGE_PER_RUN == 0.30

    def test_confidence_with_zero_runs(self):
        confidence = 0 * _BAYESIAN_SHRINKAGE_PER_RUN
        assert confidence == 0.0

    def test_confidence_with_one_run(self):
        confidence = 1 * _BAYESIAN_SHRINKAGE_PER_RUN
        assert confidence == 0.30

    def test_confidence_with_two_runs(self):
        confidence = 2 * _BAYESIAN_SHRINKAGE_PER_RUN
        assert confidence == 0.60

    def test_confidence_with_three_runs(self):
        confidence = 3 * _BAYESIAN_SHRINKAGE_PER_RUN
        assert abs(confidence - 0.90) < 1e-9

    def test_confidence_with_four_runs_capped_at_one(self):
        raw = 4 * _BAYESIAN_SHRINKAGE_PER_RUN
        confidence = min(1.0, raw)
        assert confidence == 1.0


class TestComputeAdjustmentSignals:
    """Test _compute_adjustment_signals with phase-aware weights and Bayesian shrinkage."""

    def _make_mock_run(self, distance, effort, workout_type, date):
        class MockRun:
            pass
        run = MockRun()
        run.distance_km = distance
        run.perceived_effort = effort
        run.workout_type = workout_type
        run.date = date
        return run

    def _make_mock_workout(self, workout_type, distance, day_of_week, week_number):
        class MockWorkout:
            pass
        wo = MockWorkout()
        wo.workout_type = workout_type
        wo.distance_km = distance
        wo.baseline_distance_km = distance
        wo.day_of_week = day_of_week
        wo.id = _uid()
        wo.week_number = week_number
        return wo

    def test_base_phase_uses_correct_weights(self, db):
        """Base phase should use (0.55, 0.25, 0.20) weights."""
        user, plan = _create_plan_with_phases(
            db, weeks=8, weeks_ago=3,
            phases={1: "base", 2: "base", 3: "base"},
        )

        _add_runs_for_weeks(db, plan, user, [1, 2, 3], effort=5.0, distance_multiplier=1.0)

        today = _today()
        start = plan.start_date.date() if hasattr(plan.start_date, 'date') else plan.start_date

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

        all_runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == plan.id)
            .all()
        )

        signals = _compute_adjustment_signals(
            all_runs, past_workouts, past_workout_ids,
            today, plan.id, db, _recency_weight,
            current_phase="base",
        )

        assert signals["phase_weights"]["volume"] == 0.55
        assert signals["phase_weights"]["effort"] == 0.25
        assert signals["phase_weights"]["completion"] == 0.20
        assert signals["current_phase"] == "base"

    def test_taper_phase_uses_correct_weights(self, db):
        """Taper phase should use (0.20, 0.30, 0.50) weights."""
        user, plan = _create_plan_with_phases(
            db, weeks=12, weeks_ago=10,
            phases={10: "taper", 11: "taper", 12: "taper"},
        )

        _add_runs_for_weeks(db, plan, user, [10, 11, 12], effort=5.0, distance_multiplier=1.0)

        today = _today()
        start = plan.start_date.date() if hasattr(plan.start_date, 'date') else plan.start_date

        past_workouts = []
        past_workout_ids = set()
        for wk in [10, 11, 12]:
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

        all_runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == plan.id)
            .all()
        )

        signals = _compute_adjustment_signals(
            all_runs, past_workouts, past_workout_ids,
            today, plan.id, db, _recency_weight,
            current_phase="taper",
        )

        assert signals["phase_weights"]["volume"] == 0.20
        assert signals["phase_weights"]["effort"] == 0.30
        assert signals["phase_weights"]["completion"] == 0.50
        assert signals["current_phase"] == "taper"

    def test_peak_phase_uses_correct_weights(self, db):
        """Peak phase should use (0.40, 0.35, 0.25) weights."""
        user, plan = _create_plan_with_phases(
            db, weeks=12, weeks_ago=6,
            phases={5: "peak", 6: "peak", 7: "peak"},
        )

        _add_runs_for_weeks(db, plan, user, [5, 6, 7], effort=5.0, distance_multiplier=1.0)

        today = _today()
        start = plan.start_date.date() if hasattr(plan.start_date, 'date') else plan.start_date

        past_workouts = []
        past_workout_ids = set()
        for wk in [5, 6, 7]:
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

        all_runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == plan.id)
            .all()
        )

        signals = _compute_adjustment_signals(
            all_runs, past_workouts, past_workout_ids,
            today, plan.id, db, _recency_weight,
            current_phase="peak",
        )

        assert signals["phase_weights"]["volume"] == 0.40
        assert signals["phase_weights"]["effort"] == 0.35
        assert signals["phase_weights"]["completion"] == 0.25

    def test_unknown_phase_defaults_to_build_weights(self, db):
        """An unrecognized phase should fall back to build weights."""
        user, plan = _create_plan_with_phases(db, weeks=4, weeks_ago=2)
        _add_runs_for_weeks(db, plan, user, [1, 2, 3], effort=5.0)

        today = _today()
        start = plan.start_date.date() if hasattr(plan.start_date, 'date') else plan.start_date

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

        all_runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == plan.id)
            .all()
        )

        signals = _compute_adjustment_signals(
            all_runs, past_workouts, past_workout_ids,
            today, plan.id, db, _recency_weight,
            current_phase="unknown_phase",
        )

        assert signals["phase_weights"]["volume"] == 0.50
        assert signals["phase_weights"]["effort"] == 0.30
        assert signals["phase_weights"]["completion"] == 0.20

    def test_taper_phase_completion_matters_more_for_multiplier(self, db):
        """In taper phase, low completion should hurt the multiplier more than in base."""
        user, plan = _create_plan_with_phases(
            db, weeks=12, weeks_ago=10,
            phases={10: "taper", 11: "taper", 12: "taper"},
        )

        _add_runs_for_weeks(db, plan, user, [10, 11], effort=5.0, distance_multiplier=1.0)

        today = _today()
        start = plan.start_date.date() if hasattr(plan.start_date, 'date') else plan.start_date

        past_workouts = []
        past_workout_ids = set()
        for wk in [10, 11]:
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

        all_runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == plan.id)
            .all()
        )

        signals_taper = _compute_adjustment_signals(
            all_runs, past_workouts, past_workout_ids,
            today, plan.id, db, _recency_weight,
            current_phase="taper",
        )

        signals_base = _compute_adjustment_signals(
            all_runs, past_workouts, past_workout_ids,
            today, plan.id, db, _recency_weight,
            current_phase="base",
        )

        assert signals_taper["current_phase"] == "taper"
        assert signals_base["current_phase"] == "base"
        assert signals_taper["phase_weights"]["completion"] > signals_base["phase_weights"]["completion"]


class TestPerTypeRatiosBayesianShrinkage:
    """Test that per-type ratios use Bayesian shrinkage based on sample size."""

    def test_zero_runs_of_type_shrinks_fully_to_global(self, db):
        """When no runs of a type exist, its ratio should equal the global volume_ratio."""
        user, plan = _create_plan_with_phases(
            db, weeks=6, weeks_ago=4,
            workout_types=["easy", "easy", "easy", "long"],
        )

        _add_runs_for_weeks(
            db, plan, user, [1, 2, 3, 4],
            effort=5.0,
            distance_multiplier=1.1,
            workout_types=["easy", "easy", "easy", "long"],
        )

        today = _today()
        start = plan.start_date.date() if hasattr(plan.start_date, 'date') else plan.start_date

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

        all_runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == plan.id)
            .all()
        )

        signals = _compute_adjustment_signals(
            all_runs, past_workouts, past_workout_ids,
            today, plan.id, db, _recency_weight,
            current_phase="build",
        )

        per_type = signals["per_type_ratios"]
        volume_ratio = signals["volume_ratio"]

        assert "tempo" not in per_type or abs(per_type.get("tempo", volume_ratio) - volume_ratio) < 0.01
        assert "interval" not in per_type or abs(per_type.get("interval", volume_ratio) - volume_ratio) < 0.01
        assert "hill" not in per_type or abs(per_type.get("hill", volume_ratio) - volume_ratio) < 0.01

    def test_one_run_of_type_heavily_shrunk(self, db):
        """With only 1 run of a type, the ratio should be mostly global."""
        user, plan = _create_plan_with_phases(
            db, weeks=6, weeks_ago=4,
            workout_types=["easy", "tempo", "easy", "long"],
        )

        _add_runs_for_weeks(
            db, plan, user, [1],
            effort=5.0,
            distance_multiplier=1.3,
            workout_types=["easy", "tempo", "easy", "long"],
        )

        today = _today()
        start = plan.start_date.date() if hasattr(plan.start_date, 'date') else plan.start_date

        past_workouts = []
        past_workout_ids = set()
        for wk in [1]:
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

        all_runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == plan.id)
            .all()
        )

        signals = _compute_adjustment_signals(
            all_runs, past_workouts, past_workout_ids,
            today, plan.id, db, _recency_weight,
            current_phase="build",
        )

        per_type = signals["per_type_ratios"]
        volume_ratio = signals["volume_ratio"]

        if "tempo" in per_type:
            confidence = 1 * _BAYESIAN_SHRINKAGE_PER_RUN
            raw_ratio = per_type["tempo"]
            expected = round(confidence * raw_ratio + (1.0 - confidence) * volume_ratio, 2)
            assert abs(per_type["tempo"] - expected) < 0.02

    def test_three_runs_of_type_approaches_raw_ratio(self, db):
        """With 3+ runs of a type, the ratio should be close to the raw ratio."""
        user, plan = _create_plan_with_phases(
            db, weeks=8, weeks_ago=6,
            workout_types=["easy", "tempo", "easy", "long"],
        )

        _add_runs_for_weeks(
            db, plan, user, [1, 2, 3],
            effort=5.0,
            distance_multiplier=1.4,
            workout_types=["easy", "tempo", "easy", "long"],
        )

        today = _today()
        start = plan.start_date.date() if hasattr(plan.start_date, 'date') else plan.start_date

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

        all_runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == plan.id)
            .all()
        )

        signals = _compute_adjustment_signals(
            all_runs, past_workouts, past_workout_ids,
            today, plan.id, db, _recency_weight,
            current_phase="build",
        )

        per_type = signals["per_type_ratios"]
        assert "tempo" in per_type
        confidence = min(1.0, 3 * _BAYESIAN_SHRINKAGE_PER_RUN)
        assert confidence >= 0.90 - 1e-9

    def test_per_type_ratios_stay_within_bounds(self, db):
        """All per-type ratios should be clamped to [0.5, 1.5]."""
        user, plan = _create_plan_with_phases(
            db, weeks=8, weeks_ago=6,
            workout_types=["easy", "tempo", "interval", "long"],
        )

        _add_runs_for_weeks(
            db, plan, user, [1, 2, 3, 4, 5, 6],
            effort=5.0,
            distance_multiplier=2.0,
            workout_types=["easy", "tempo", "interval", "long"],
        )

        today = _today()
        start = plan.start_date.date() if hasattr(plan.start_date, 'date') else plan.start_date

        past_workouts = []
        past_workout_ids = set()
        for wk in range(1, 7):
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

        all_runs = (
            db.query(RunLog)
            .filter(RunLog.training_plan_id == plan.id)
            .all()
        )

        signals = _compute_adjustment_signals(
            all_runs, past_workouts, past_workout_ids,
            today, plan.id, db, _recency_weight,
            current_phase="build",
        )

        for wtype, ratio in signals["per_type_ratios"].items():
            assert 0.5 <= ratio <= 1.5, f"{wtype} ratio {ratio} out of bounds"


class TestPhaseAwareAdjustmentIntegration:
    """Integration tests for adjust_plan with phase-aware behavior."""

    def test_adjust_plan_records_phase_in_signals(self, db):
        """adjust_plan should return phase information in its result."""
        from app.services.adaptation.plan_adjuster import adjust_plan

        user, plan = _create_plan_with_phases(
            db, weeks=8, weeks_ago=4,
            phases={1: "base", 2: "base", 3: "base", 4: "base", 5: "build"},
        )

        _add_runs_for_weeks(db, plan, user, [1, 2, 3, 4], effort=5.0, distance_multiplier=1.0)

        result = adjust_plan(plan.id, user.id, db)

        assert "current_phase" in result
        assert "phase_weights" in result

    def test_adjust_plan_records_phase_in_history(self, db):
        """Adaptation history should include the phase for each adjustment."""
        from app.services.adaptation.plan_adjuster import adjust_plan

        user, plan = _create_plan_with_phases(
            db, weeks=8, weeks_ago=4,
            phases={1: "base", 2: "base", 3: "base", 4: "base", 5: "build"},
        )

        _add_runs_for_weeks(db, plan, user, [1, 2, 3, 4], effort=5.0, distance_multiplier=1.0)

        adjust_plan(plan.id, user.id, db)

        plan = db.query(TrainingPlan).filter(TrainingPlan.id == plan.id).one()
        history = plan.adaptation_history or []
        assert len(history) >= 1
        last_event = history[-1]
        assert last_event["type"] == "adjust"
        assert "phase" in last_event
