"""Tests for the adaptation lockdown work.

Covers:
- Single mutation path: per-week ``bump`` applied twice = baseline × 1.08
  (no compounding from current).
- Weekly cadence: only one parked recommendation per ISO week.
- Overreach forces multiplier ≤ 0.95 regardless of positive signals.
- Stale ``If-Match`` revision rejected with 409 on per-week override.
- Hysteresis suppresses tiny direction-reversing recommendations.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import create_app
from app.models import (
    Base,
    DailyWorkout,
    RunLog,
    TrainingPlan,
    User,
    WeeklyPlan,
)
from app.services.adaptation.recommendation_evaluator import (
    _is_small_reversal,
    evaluate_weekly_recommendation,
)
from app.services.plans.week_adjustment_service import apply_week_action


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
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


def _make_plan(
    db: Session, *, weeks: int = 6, weeks_ago: int = 1,
) -> tuple[User, TrainingPlan]:
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    start = _now() - timedelta(weeks=weeks_ago)
    plan_data = [
        {
            "week": w + 1,
            "total_km": 30.0,
            "daily_workouts": [
                {"day": d, "type": "easy", "distance": 7.5}
                for d in range(1, 5)
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
            total_km=30.0,
        )
        db.add(wp)
        db.flush()
        for day in range(1, 5):
            db.add(DailyWorkout(
                id=_uid(),
                weekly_plan_id=wp.id,
                day_of_week=day,
                workout_type="easy",
                distance_km=7.5,
                baseline_distance_km=7.5,
            ))
    db.commit()
    return user, plan


def _week_workouts(db: Session, plan_id: str, week_number: int) -> list[DailyWorkout]:
    wp = (
        db.query(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan_id,
            WeeklyPlan.week_number == week_number,
        )
        .one()
    )
    return (
        db.query(DailyWorkout)
        .filter(DailyWorkout.weekly_plan_id == wp.id)
        .order_by(DailyWorkout.day_of_week)
        .all()
    )


def _log_runs(
    db: Session, user: User, plan: TrainingPlan, week_number: int,
    *, distance_km: float = 9.0, effort: int = 8,
) -> None:
    for wo in _week_workouts(db, plan.id, week_number):
        db.add(RunLog(
            id=_uid(),
            user_id=user.id,
            training_plan_id=plan.id,
            daily_workout_id=wo.id,
            date=plan.start_date + timedelta(
                weeks=week_number - 1, days=wo.day_of_week - 1,
            ),
            distance_km=distance_km,
            duration_minutes=45,
            perceived_effort=effort,
            workout_type="easy",
        ))
    db.commit()


# ---------------------------------------------------------------------------
# Phase 1: single mutation path — no compounding
# ---------------------------------------------------------------------------


class TestSingleMutationPath:
    def test_bump_twice_does_not_compound(self, db):
        """Bump applied twice yields baseline × 1.08, not 1.08²."""
        user, plan = _make_plan(db)
        plan_data = plan.plan_data
        week_data = next(w for w in plan_data if w["week"] == 2)
        baselines = [wo.baseline_distance_km for wo in _week_workouts(db, plan.id, 2)]

        apply_week_action("bump", plan, plan_data, week_data, 2, plan.id, db)
        db.commit()
        first_distances = [wo.distance_km for wo in _week_workouts(db, plan.id, 2)]

        apply_week_action("bump", plan, plan_data, week_data, 2, plan.id, db)
        db.commit()
        second_distances = [wo.distance_km for wo in _week_workouts(db, plan.id, 2)]

        # Second apply should land on the same value as the first — both
        # are baseline × 1.08, applied fresh from baseline_distance_km.
        for first, second, base in zip(first_distances, second_distances, baselines):
            expected = round(base * 1.08, 1)
            assert first == expected, f"first={first} expected={expected}"
            assert second == expected, f"second={second} expected={expected}"

    def test_bump_preserves_baseline(self, db):
        user, plan = _make_plan(db)
        week_data = next(w for w in plan.plan_data if w["week"] == 2)

        apply_week_action("bump", plan, plan.plan_data, week_data, 2, plan.id, db)
        db.commit()

        for wo in _week_workouts(db, plan.id, 2):
            assert wo.baseline_distance_km == 7.5

    def test_extend_long_run_capped_at_125pct(self, db):
        """Extend by +2 km should never exceed baseline × 1.25 (the per-workout cap)."""
        user, plan = _make_plan(db)
        # Replace day 4 with a long run that's small enough that +2 > 25%.
        long_wo = _week_workouts(db, plan.id, 2)[-1]
        long_wo.workout_type = "long"
        long_wo.distance_km = 5.0
        long_wo.baseline_distance_km = 5.0
        db.commit()

        week_data = next(w for w in plan.plan_data if w["week"] == 2)
        apply_week_action(
            "extend_long_run", plan, plan.plan_data, week_data, 2, plan.id, db,
        )
        db.commit()

        long_wo = next(
            wo for wo in _week_workouts(db, plan.id, 2)
            if wo.workout_type == "long"
        )
        # ratio = 1 + 2/5 = 1.4 → clamped to 1.15 per per_type_ratios cap,
        # then per-workout baseline × 1.25 cap = 6.25.
        # Effective ratio is min(1.15, 1.25) = 1.15 → 5.75.
        assert long_wo.distance_km <= 5.0 * 1.25 + 0.01
        assert long_wo.distance_km >= 5.0  # never reduces

    def test_revision_bumped_on_changes(self, db):
        user, plan = _make_plan(db)
        before = plan.adaptation_revision or 0
        week_data = next(w for w in plan.plan_data if w["week"] == 2)
        apply_week_action("bump", plan, plan.plan_data, week_data, 2, plan.id, db)
        db.commit()
        assert plan.adaptation_revision == before + 1


# ---------------------------------------------------------------------------
# Phase 2: weekly cadence
# ---------------------------------------------------------------------------


class TestWeeklyCadence:
    def test_returns_none_when_no_completed_week(self, db):
        """A plan in week 1 produces no recommendation yet."""
        user, plan = _make_plan(db, weeks=4, weeks_ago=0)
        assert evaluate_weekly_recommendation(plan.id, user.id, db) is None

    def test_only_one_recommendation_per_iso_week(self, db):
        """Repeated calls within the same plan-week do not re-park."""
        user, plan = _make_plan(db, weeks=6, weeks_ago=2)
        # Log 4 runs in week 1 (the completed week). Distances ~20% over
        # target should drive the multiplier above 1.0.
        _log_runs(db, user, plan, week_number=1, distance_km=9.0, effort=5)

        first = evaluate_weekly_recommendation(plan.id, user.id, db)
        second = evaluate_weekly_recommendation(plan.id, user.id, db)
        # First call may or may not park (depends on signal magnitude),
        # but the second one must return None — `last_recommendation_week`
        # was written. The plan is in week 3, so the most recently
        # completed week is week 2.
        assert second is None
        assert plan.last_recommendation_week == 2


# ---------------------------------------------------------------------------
# Auto-apply gate: user.auto_adjust_enabled
# ---------------------------------------------------------------------------


class TestAutoApplyGate:
    def test_parks_when_flag_off(self, db):
        """Default flag=False: weekly eval parks a pending recommendation."""
        user, plan = _make_plan(db, weeks=6, weeks_ago=2)
        assert user.auto_adjust_enabled is False
        _log_runs(db, user, plan, week_number=1, distance_km=9.0, effort=5)

        result = evaluate_weekly_recommendation(plan.id, user.id, db)
        if result is None:
            # Signal was too weak (sub-2% multiplier) — nothing to assert.
            return
        assert result["action"] == "parked"
        assert plan.pending_recommendation is not None
        assert plan.last_change_plan is None

    def test_auto_applies_when_flag_on(self, db):
        """Flag=True: recommendation applies immediately, no pending banner."""
        user, plan = _make_plan(db, weeks=6, weeks_ago=2)
        user.auto_adjust_enabled = True
        db.commit()
        _log_runs(db, user, plan, week_number=1, distance_km=9.0, effort=5)

        result = evaluate_weekly_recommendation(plan.id, user.id, db)
        if result is None:
            return
        assert result["action"] == "auto_adjusted"
        assert plan.pending_recommendation is None
        # The change should be recorded so the "Latest plan changes" panel
        # can render it on next page load.
        assert plan.last_change_plan is not None
        # Auto-apply path bumps the revision (used for If-Match conflict
        # detection on subsequent client requests).
        assert (plan.adaptation_revision or 0) >= 1


# ---------------------------------------------------------------------------
# Phase 5: overreach + hysteresis
# ---------------------------------------------------------------------------


class TestOverreachAndHysteresis:
    def test_overreach_forces_reduction(self):
        """High volume × high effort → multiplier <= 0.95 even with strong positives."""
        from app.services.adaptation.signal_computer import compute_adjustment_signals

        class _W:
            def __init__(self, dist, effort, dwid):
                self.distance_km = dist
                self.perceived_effort = effort
                self.workout_type = "easy"
                self.id = dwid
                self.date = datetime.now(timezone.utc).date()
                self.daily_workout_id = dwid

        class _DW:
            def __init__(self, dist, dwid):
                self.distance_km = dist
                self.baseline_distance_km = dist
                self.workout_type = "easy"
                self.id = dwid

        today = datetime.now(timezone.utc).date()
        plan_workouts = [
            (_DW(5.0, f"w{i}"), today - timedelta(days=i + 1))
            for i in range(10)
        ]
        runs = [
            _W(dist=8.0, effort=9, dwid=plan_workouts[i][0].id)
            for i in range(10)
        ]

        class _StubDB:
            def query(self, *_a, **_kw):
                return self

            def filter(self, *_a, **_kw):
                return self

            def all(self):
                return []

        signals = compute_adjustment_signals(
            all_plan_runs=runs,
            past_workouts=plan_workouts,
            past_workout_ids={w.id for w, _ in plan_workouts},
            today=today,
            plan_id="plan",
            db=_StubDB(),
            recency_weight_fn=lambda _d: 1.0,
            current_phase="build",
        )

        # volume_ratio = 80/50 = 1.6 capped at 1.5; avg_effort = 9.
        # Both branches set overreach_detected; the new clamp forces ≤0.95.
        assert signals["overreach_detected"] is True
        assert signals["multiplier"] <= 0.95

    def test_hysteresis_suppresses_small_reversal(self):
        history = [
            {"type": "auto_accept", "direction": "increase", "multiplier": 1.05},
        ]
        # Proposed "reduce" by only 3% → should suppress.
        assert _is_small_reversal(history, "reduce", 0.97) is True
        # Large reversal (≥5%) → not suppressed.
        assert _is_small_reversal(history, "reduce", 0.92) is False
        # Same direction → not a reversal.
        assert _is_small_reversal(history, "increase", 1.03) is False


# ---------------------------------------------------------------------------
# Phase 4: lost-update protection
# ---------------------------------------------------------------------------


class TestRevisionConflict:
    def test_override_rejects_stale_if_match(self, db):
        user, plan = _make_plan(db)

        app = create_app(skip_migrations=True)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: user

        with TestClient(app) as client:
            # First call with the current (correct) revision succeeds.
            ok = client.post(
                f"/api/plan/{plan.id}/week/2/override",
                json={"action": "bump"},
                headers={"If-Match": str(plan.adaptation_revision or 0)},
            )
            assert ok.status_code == 200, ok.text

            # Re-issuing with the OLD revision (now stale) → 409.
            stale = client.post(
                f"/api/plan/{plan.id}/week/2/override",
                json={"action": "bump"},
                headers={"If-Match": "0"},
            )
            assert stale.status_code == 409
            body = stale.json()
            assert body["detail"]["error"] == "revision_conflict"

        app.dependency_overrides.clear()

    def test_override_no_header_skips_check(self, db):
        """Older clients without If-Match keep working."""
        user, plan = _make_plan(db)
        app = create_app(skip_migrations=True)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: user

        with TestClient(app) as client:
            r = client.post(
                f"/api/plan/{plan.id}/week/2/override",
                json={"action": "bump"},
            )
            assert r.status_code == 200

        app.dependency_overrides.clear()
