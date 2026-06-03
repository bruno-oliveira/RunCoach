"""Tests for workout type-swap proposals and application."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation.type_swapper import apply_swap, get_swap_proposals
from app.models import Base, DailyWorkout, RunLog, TrainingPlan, User, WeeklyPlan

_TYPES = ["easy", "tempo", "interval", "long"]


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


def _make_plan(db, *, terrain=None, with_start=True):
    user = User(id=_uid(), email=f"{_uid()[:8]}@t.com")
    db.add(user)
    db.flush()
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="21.1",
        weeks_duration=8,
        start_date=_now() - timedelta(weeks=4) if with_start else None,
        training_terrain=terrain,
        plan_data=[
            {
                "week": wk,
                "phase": "build",
                "daily_workouts": [
                    {"day": i + 1, "type": t, "distance": 8.0}
                    for i, t in enumerate(_TYPES)
                ],
            }
            for wk in range(1, 9)
        ],
    )
    db.add(plan)
    db.flush()
    workouts = {}
    for wk in range(1, 9):
        wp = WeeklyPlan(
            id=_uid(), training_plan_id=plan.id, week_number=wk, total_km=30
        )
        db.add(wp)
        db.flush()
        for i, t in enumerate(_TYPES):
            dist = 8.0 if t != "long" else 14.0
            dw = DailyWorkout(
                id=_uid(),
                weekly_plan_id=wp.id,
                day_of_week=i + 1,
                workout_type=t,
                distance_km=dist,
                baseline_distance_km=dist,
            )
            db.add(dw)
            db.flush()
            workouts[(wk, t)] = dw
    db.commit()
    return user, plan, workouts


class TestGetSwapProposals:
    def test_no_start_date(self, db):
        user, plan, _ = _make_plan(db, with_start=False)
        assert get_swap_proposals(plan.id, user.id, db) == []

    def test_insufficient_linked_runs(self, db):
        user, plan, workouts = _make_plan(db)
        db.add(
            RunLog(
                id=_uid(),
                user_id=user.id,
                training_plan_id=plan.id,
                daily_workout_id=workouts[(1, "tempo")].id,
                date=_now() - timedelta(weeks=3),
                distance_km=8.0,
                duration_minutes=45,
                quality_label="Too hard",
            )
        )
        db.commit()
        assert get_swap_proposals(plan.id, user.id, db) == []

    def test_proposes_tempo_to_easy_on_repeated_too_hard(self, db):
        user, plan, workouts = _make_plan(db)
        for wk in (1, 2, 3):
            db.add(
                RunLog(
                    id=_uid(),
                    user_id=user.id,
                    training_plan_id=plan.id,
                    daily_workout_id=workouts[(wk, "tempo")].id,
                    date=_now() - timedelta(weeks=(5 - wk)),
                    distance_km=8.0,
                    duration_minutes=40,
                    quality_label="Too hard",
                )
            )
        db.commit()

        proposals = get_swap_proposals(plan.id, user.id, db)
        tempo_props = [p for p in proposals if p["from_type"] == "tempo"]
        assert tempo_props
        p = tempo_props[0]
        assert p["to_type"] == "easy"
        assert p["pattern_count"] >= 3
        assert p["week"] >= 5  # future workout only

    def test_proposes_shorter_long_run_on_incompletion(self, db):
        user, plan, workouts = _make_plan(db)
        for wk in (1, 2, 3):
            db.add(
                RunLog(
                    id=_uid(),
                    user_id=user.id,
                    training_plan_id=plan.id,
                    daily_workout_id=workouts[(wk, "long")].id,
                    date=_now() - timedelta(weeks=(5 - wk)),
                    distance_km=5.0,  # < 70% of the 14 km planned long run
                    duration_minutes=30,
                    quality_label="Good",
                )
            )
        db.commit()

        proposals = get_swap_proposals(plan.id, user.id, db)
        assert any(p["from_type"] == "long" for p in proposals)


class TestApplySwap:
    def test_plan_not_found(self, db):
        assert apply_swap("w", "missing", "nobody", "easy", db) is None

    def test_workout_not_found(self, db):
        user, plan, _ = _make_plan(db)
        assert apply_swap("missing", plan.id, user.id, "easy", db) is None

    def test_flat_terrain_rejects_hill(self, db):
        user, plan, workouts = _make_plan(db, terrain="flat")
        wid = workouts[(6, "tempo")].id
        result = apply_swap(wid, plan.id, user.id, "hill", db)
        assert result == {
            "swapped": False,
            "reason": "Flat-terrain plans do not allow hill workout substitutions.",
        }

    def test_successful_swap_updates_type_notes_and_plan_data(self, db):
        user, plan, workouts = _make_plan(db)
        dw = workouts[(6, "tempo")]
        result = apply_swap(dw.id, plan.id, user.id, "easy", db)

        assert result["swapped"] is True
        assert result["old_type"] == "tempo"
        assert result["new_type"] == "easy"

        db.expire_all()
        refreshed = db.query(DailyWorkout).filter(DailyWorkout.id == dw.id).one()
        assert refreshed.workout_type == "easy"
        assert "Swapped from tempo" in (refreshed.notes or "")

        plan = db.query(TrainingPlan).filter(TrainingPlan.id == plan.id).one()
        wk6 = next(w for w in plan.plan_data if w["week"] == 6)
        swapped = next(w for w in wk6["daily_workouts"] if w["day"] == dw.day_of_week)
        assert swapped["type"] == "easy"

    def test_swap_to_buildable_type_regenerates_steps(self, db):
        """B8: swapping to a buildable type regenerates structured steps so the
        card no longer renders the old type's reps."""
        user, plan, workouts = _make_plan(db)
        dw = workouts[(6, "interval")]
        # Seed stale interval steps that would otherwise survive the swap.
        wk6 = next(w for w in plan.plan_data if w["week"] == 6)
        target = next(w for w in wk6["daily_workouts"] if w["day"] == dw.day_of_week)
        target["steps"] = [{"label": "interval rep", "distance_m": 400}]
        plan.plan_data = plan.plan_data
        db.commit()

        result = apply_swap(dw.id, plan.id, user.id, "easy", db)
        assert result["swapped"] is True

        plan = db.query(TrainingPlan).filter(TrainingPlan.id == plan.id).one()
        wk6 = next(w for w in plan.plan_data if w["week"] == 6)
        swapped = next(w for w in wk6["daily_workouts"] if w["day"] == dw.day_of_week)
        # Steps were regenerated for the easy run, not left as the 400 m rep.
        assert swapped.get("steps")
        assert all(s.get("label") != "interval rep" for s in swapped["steps"])

    def test_swap_to_non_buildable_type_clears_steps(self, db):
        """B8: swapping to a log-only type (fartlek) with no day-level builder
        clears the stale steps so the enricher falls back to the stored
        distance + prose."""
        user, plan, workouts = _make_plan(db)
        dw = workouts[(6, "interval")]
        wk6 = next(w for w in plan.plan_data if w["week"] == 6)
        target = next(w for w in wk6["daily_workouts"] if w["day"] == dw.day_of_week)
        target["steps"] = [{"label": "interval rep", "distance_m": 400}]
        plan.plan_data = plan.plan_data
        db.commit()

        result = apply_swap(dw.id, plan.id, user.id, "fartlek", db)
        assert result["swapped"] is True

        plan = db.query(TrainingPlan).filter(TrainingPlan.id == plan.id).one()
        wk6 = next(w for w in plan.plan_data if w["week"] == 6)
        swapped = next(w for w in wk6["daily_workouts"] if w["day"] == dw.day_of_week)
        assert swapped["type"] == "fartlek"
        assert swapped.get("steps") == []
