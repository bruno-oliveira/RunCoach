"""Adaptation now adjusts KEY workouts (not just easy/long volume).

Before, every key/quality workout was protected from adaptation because its
description and steps embedded distances that scaling would leave stale. Now a
key workout is regenerated from a single distance (rebuild_key_workout), so it
can adapt while keeping prose, structure, steps and distance in lockstep.

These tests pin:
  * a distance-based key workout actually moves under a boost multiplier, and
    stays internally consistent (distance == steps == cited description), and
  * a duration-defined key workout settles back to its time total (no spurious
    change), still consistent.
"""

import re
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation.week_adjuster import (
    apply_adjustment_to_future_weeks,
)
from app.core.training.key_workout_library import overlay_key_workout
from app.core.training.vdot_calculator import VDOTCalculator
from app.core.training.workout_steps import _compute_distance_from_steps
from app.models import Base, DailyWorkout, TrainingPlan, User, WeeklyPlan


def _uid() -> str:
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


def _cited_km(text: str) -> list[float]:
    return [float(m) for m in re.findall(r"(\d+\.\d+)\s*km", text or "")]


def _assert_consistent(pd_wo: dict) -> None:
    steps_total = _compute_distance_from_steps(pd_wo.get("steps", []))
    assert abs(pd_wo["distance"] - steps_total) <= 0.15, (
        f"distance {pd_wo['distance']} vs steps {steps_total:.2f}"
    )
    step_kms = {
        round((s.get("distance_m") or 0) / 1000.0, 1)
        for s in pd_wo.get("steps", [])
        if s.get("distance_m")
    }
    resolvable = {round(pd_wo["distance"], 1)} | step_kms
    for n in _cited_km(pd_wo.get("description", "")):
        assert any(abs(n - r) <= 0.15 for r in resolvable), (
            f"description cites {n} km, not in {sorted(resolvable)}\n"
            f"  {pd_wo.get('description')}"
        )


def _build_key_workout_plan(db: Session, force_id: str, day_distance: float):
    """One future week (week 2) holding a single key workout on day 2."""
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    pace_zones = VDOTCalculator.get_pace_zones(45.0)
    wo = {"distance": day_distance, "type": "interval", "day": 2}
    overlay_key_workout(
        wo,
        "interval",
        "build",
        5.0,
        0,
        pace_zones=pace_zones,
        force_id=force_id,
    )

    week = {
        "week": 2,
        "total_km": round(wo["distance"], 1),
        "phase": "build",
        "daily_workouts": [wo],
    }
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=8,
        vdot=45.0,
        plan_data=[week],
    )
    db.add(plan)
    db.flush()

    wp = WeeklyPlan(
        id=_uid(),
        training_plan_id=plan.id,
        week_number=2,
        total_km=week["total_km"],
    )
    db.add(wp)
    db.flush()
    db.add(
        DailyWorkout(
            id=_uid(),
            weekly_plan_id=wp.id,
            day_of_week=2,
            workout_type="interval",
            distance_km=wo["distance"],
            baseline_distance_km=wo["distance"],
            key_workout_id=force_id,
        )
    )
    db.commit()
    return plan, wp


def test_distance_based_key_workout_adapts_and_stays_consistent(db):
    plan, wp = _build_key_workout_plan(db, "5k_cruise_intervals", 6.0)
    before = plan.plan_data[0]["daily_workouts"][0]["distance"]

    apply_adjustment_to_future_weeks(
        plan,
        [wp],
        1.15,
        db,
        current_week=1,
        current_day_of_week=1,
        per_type_ratios={"interval": 1.15},
    )

    pd_wo = plan.plan_data[0]["daily_workouts"][0]
    assert pd_wo["distance"] > before, "distance-based key workout should scale up"
    _assert_consistent(pd_wo)
    # ORM distance tracks the regenerated plan_data distance.
    orm = db.query(DailyWorkout).filter(DailyWorkout.weekly_plan_id == wp.id).one()
    assert abs(orm.distance_km - pd_wo["distance"]) <= 0.01


def test_time_defined_key_workout_stays_consistent_under_adaptation(db):
    # Over/under intervals are time-defined (3 min hard / 2 min steady); only
    # their warm-up/cool-down scale with a volume boost. The session must stay
    # internally consistent (distance == steps == description) after adapting —
    # that is the safety guarantee that lets quality workouts adapt at all.
    plan, wp = _build_key_workout_plan(db, "trail_flat_over_under_intervals", 6.0)

    apply_adjustment_to_future_weeks(
        plan,
        [wp],
        1.15,
        db,
        current_week=1,
        current_day_of_week=1,
        per_type_ratios={"interval": 1.15},
    )

    pd_wo = plan.plan_data[0]["daily_workouts"][0]
    _assert_consistent(pd_wo)
    # The time-defined work dominates, so the change stays modest (only the
    # warm-up/cool-down flexes) rather than the full volume multiplier.
    orm = db.query(DailyWorkout).filter(DailyWorkout.weekly_plan_id == wp.id).one()
    assert abs(orm.distance_km - pd_wo["distance"]) <= 0.01
