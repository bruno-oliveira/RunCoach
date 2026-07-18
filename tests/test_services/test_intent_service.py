"""Tests for intent-driven plan adaptation (intent_service).

Covers the life-event intents that replace the old scattered surfaces:
skip a run, feeling tired, busy week, away, sick/injured, feeling strong.
All flow through the shared ChangePlan builder, are non-compounding (scaled
from baseline), and preview must never persist.
"""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.contexts.plan.adaptation import intent_service
from app.models import Base, DailyWorkout, TrainingPlan, User, WeeklyPlan

# Wednesday of the current week → isoweekday 3, so days 1–2 are "past".
WED = date(2026, 5, 20)


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


@pytest.fixture()
def freeze_today(monkeypatch):
    holder = {"value": WED}

    def fake_today():
        return holder["value"]

    for mod in (
        "app.contexts.plan.adaptation._helpers.today_date",
        "app.contexts.plan.adaptation.intent_service.today_date",
    ):
        monkeypatch.setattr(mod, fake_today)

    def setter(d: date) -> None:
        holder["value"] = d

    return setter


def _make_plan(
    db: Session, *, today_value: date, current_week: int = 3, weeks: int = 8
) -> tuple[User, TrainingPlan]:
    """Plan whose start_date puts today into `current_week`.

    Each week: Mon easy 6, Tue easy 6, Wed tempo 8, Thu long 12.
    """
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    days_into_week = today_value.isoweekday() - 1
    days_elapsed = (current_week - 1) * 7 + days_into_week
    start_date = datetime.combine(
        today_value - timedelta(days=days_elapsed), datetime.min.time()
    )

    layout = [
        (1, "easy", 6.0),
        (2, "easy", 6.0),
        (3, "tempo", 8.0),
        (4, "long", 12.0),
    ]
    plan_data = [
        {
            "week": w + 1,
            "total_km": 32.0,
            "phase": "build",
            "daily_workouts": [
                {"day": d, "type": t, "distance": dist} for (d, t, dist) in layout
            ],
        }
        for w in range(weeks)
    ]
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=32,
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
            id=_uid(), training_plan_id=plan.id, week_number=wk, total_km=32.0
        )
        db.add(wp)
        db.flush()
        for d, t, dist in layout:
            db.add(
                DailyWorkout(
                    id=_uid(),
                    weekly_plan_id=wp.id,
                    day_of_week=d,
                    workout_type=t,
                    distance_km=dist,
                    baseline_distance_km=dist,
                )
            )
    db.commit()
    return user, plan


def _workout(db, plan, week, day) -> DailyWorkout:
    wp = (
        db.query(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan.id, WeeklyPlan.week_number == week)
        .one()
    )
    return (
        db.query(DailyWorkout)
        .filter(DailyWorkout.weekly_plan_id == wp.id, DailyWorkout.day_of_week == day)
        .one()
    )


def test_skip_run_today_rests_the_workout(db, freeze_today):
    user, plan = _make_plan(db, today_value=WED)

    result = intent_service.apply_intent(plan.id, user.id, "skip_run", {}, db)

    assert result["action"] == "skip_run"
    assert result["summary"]["workouts_changed_count"] == 1
    wo = _workout(db, plan, 3, 3)  # today = Wed, week 3
    assert wo.distance_km == 0
    assert wo.workout_type == "rest"


def test_feeling_tired_eases_remaining_week_and_demotes_quality(db, freeze_today):
    user, plan = _make_plan(db, today_value=WED)

    intent_service.apply_intent(plan.id, user.id, "feeling_tired", {}, db)

    # Past days (Mon/Tue) untouched.
    assert _workout(db, plan, 3, 1).distance_km == 6.0
    # Today's tempo demoted to easy and scaled from baseline (8 * 0.85).
    today_wo = _workout(db, plan, 3, 3)
    assert today_wo.workout_type == "easy"
    assert today_wo.distance_km == pytest.approx(6.8, abs=0.05)
    # Thu long scaled but stays long.
    thu = _workout(db, plan, 3, 4)
    assert thu.workout_type == "long"
    assert thu.distance_km == pytest.approx(10.2, abs=0.05)


def test_feeling_strong_bumps_future_weeks(db, freeze_today):
    user, plan = _make_plan(db, today_value=WED)

    result = intent_service.apply_intent(plan.id, user.id, "feeling_strong", {}, db)

    assert result["summary"]["workouts_changed_count"] > 0
    # Current week (3) is not bumped; week 4 easy run grows from baseline.
    assert _workout(db, plan, 4, 1).distance_km > 6.0
    assert _workout(db, plan, 3, 1).distance_km == 6.0


def test_away_range_rests_each_training_day(db, freeze_today):
    user, plan = _make_plan(db, today_value=WED)
    # Wed (today) through next Tue → covers wk3 d3,d4 and wk4 d1,d2.
    params = {
        "start_date": WED.isoformat(),
        "end_date": (WED + timedelta(days=6)).isoformat(),
    }

    result = intent_service.apply_intent(plan.id, user.id, "away", params, db)

    assert result["summary"]["workouts_changed_count"] == 4
    assert _workout(db, plan, 3, 3).workout_type == "rest"
    assert _workout(db, plan, 4, 2).workout_type == "rest"
    # A day outside the window is untouched.
    assert _workout(db, plan, 4, 3).workout_type == "tempo"


def test_preview_does_not_persist(db, freeze_today):
    user, plan = _make_plan(db, today_value=WED)

    preview = intent_service.preview_intent(plan.id, user.id, "skip_run", {}, db)
    assert preview["mode"] == "preview"
    assert preview["would_change"] is True

    # Nothing committed: today's run is still its original tempo / 8 km.
    wo = _workout(db, plan, 3, 3)
    assert wo.distance_km == 8.0
    assert wo.workout_type == "tempo"


def test_intents_are_non_compounding(db, freeze_today):
    user, plan = _make_plan(db, today_value=WED)

    intent_service.apply_intent(plan.id, user.id, "feeling_tired", {}, db)
    first = _workout(db, plan, 3, 4).distance_km
    intent_service.apply_intent(plan.id, user.id, "feeling_tired", {}, db)
    second = _workout(db, plan, 3, 4).distance_km

    # Re-declaring re-computes from baseline rather than stacking 0.85².
    assert first == pytest.approx(second, abs=0.05)


def test_unknown_intent_is_a_safe_noop(db, freeze_today):
    user, plan = _make_plan(db, today_value=WED)
    result = intent_service.apply_intent(plan.id, user.id, "nonsense", {}, db)
    assert result["would_change"] is False
    assert _workout(db, plan, 3, 3).distance_km == 8.0


def _make_full_week_plan(
    db: Session, *, today_value: date, current_week: int = 3, weeks: int = 8
) -> tuple[User, TrainingPlan]:
    """Plan with a full 7-day week (including rest days), so the
    missed_today "reschedule" path has a real rest day to swap onto.

    Mon/Tue easy 6, Wed tempo 8 (today), Thu long 12, Fri rest, Sat easy 5,
    Sun rest.
    """
    user = User(id=_uid(), email=f"{_uid()[:8]}@test.com")
    db.add(user)
    db.flush()

    days_into_week = today_value.isoweekday() - 1
    days_elapsed = (current_week - 1) * 7 + days_into_week
    start_date = datetime.combine(
        today_value - timedelta(days=days_elapsed), datetime.min.time()
    )

    layout = [
        (1, "easy", 6.0),
        (2, "easy", 6.0),
        (3, "tempo", 8.0),
        (4, "long", 12.0),
        (5, "rest", 0.0),
        (6, "easy", 5.0),
        (7, "rest", 0.0),
    ]
    plan_data = [
        {
            "week": w + 1,
            "total_km": 37.0,
            "phase": "build",
            "daily_workouts": [
                {"day": d, "type": t, "distance": dist} for (d, t, dist) in layout
            ],
        }
        for w in range(weeks)
    ]
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=37,
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
            id=_uid(), training_plan_id=plan.id, week_number=wk, total_km=37.0
        )
        db.add(wp)
        db.flush()
        for d, t, dist in layout:
            db.add(
                DailyWorkout(
                    id=_uid(),
                    weekly_plan_id=wp.id,
                    day_of_week=d,
                    workout_type=t,
                    distance_km=dist,
                    baseline_distance_km=dist if t != "rest" else None,
                )
            )
    db.commit()
    return user, plan


def test_missed_today_ease_lightens_and_demotes_todays_run(db, freeze_today):
    user, plan = _make_plan(db, today_value=WED)

    result = intent_service.apply_intent(
        plan.id, user.id, "missed_today", {"choice": "ease"}, db
    )

    assert result["action"] == "missed_today"
    assert result["summary"]["workouts_changed_count"] == 1
    wo = _workout(db, plan, 3, 3)  # today = Wed, week 3, tempo 8
    assert wo.workout_type == "easy"
    assert wo.distance_km == pytest.approx(4.8, abs=0.05)


def test_missed_today_skip_rests_the_workout(db, freeze_today):
    user, plan = _make_plan(db, today_value=WED)

    result = intent_service.apply_intent(
        plan.id, user.id, "missed_today", {"choice": "skip"}, db
    )

    assert result["summary"]["workouts_changed_count"] == 1
    wo = _workout(db, plan, 3, 3)
    assert wo.distance_km == 0
    assert wo.workout_type == "rest"


def test_missed_today_reschedule_falls_back_to_ease_without_rest_day(db, freeze_today):
    # Default fixture only has days 1-4, so there's no rest day left this
    # week to reschedule onto — must fall back to the ease primitive.
    user, plan = _make_plan(db, today_value=WED)

    result = intent_service.apply_intent(
        plan.id, user.id, "missed_today", {"choice": "reschedule"}, db
    )

    assert result["summary"]["workouts_changed_count"] == 1
    wo = _workout(db, plan, 3, 3)
    assert wo.workout_type == "easy"
    assert wo.distance_km == pytest.approx(4.8, abs=0.05)


def test_missed_today_reschedule_moves_to_nearest_rest_day(db, freeze_today):
    user, plan = _make_full_week_plan(db, today_value=WED)

    result = intent_service.apply_intent(
        plan.id, user.id, "missed_today", {"choice": "reschedule"}, db
    )

    assert result["summary"]["workouts_changed_count"] == 2
    wed = _workout(db, plan, 3, 3)  # vacated
    assert wed.workout_type == "rest"
    assert wed.distance_km == 0
    fri = _workout(db, plan, 3, 5)  # nearest rest day this week
    assert fri.workout_type == "tempo"
    assert fri.distance_km == 8.0
    # Thu (day 4) untouched by the swap.
    assert _workout(db, plan, 3, 4).distance_km == 12.0


def test_missed_today_unresolvable_day_is_a_safe_noop(db, freeze_today):
    user, plan = _make_plan(db, today_value=WED)

    result = intent_service.apply_intent(
        plan.id,
        user.id,
        "missed_today",
        {"choice": "skip", "date": "1999-01-01"},
        db,
    )

    assert result["would_change"] is False


def test_sick_rests_window_then_ramps_without_reinflating_rest(db, freeze_today):
    user, plan = _make_plan(db, today_value=WED)
    # 7 days from Wed → rests wk3 d3,d4 and wk4 d1,d2.
    intent_service.apply_intent(plan.id, user.id, "sick_injured", {"days": 7}, db)

    # Rested days stay rest — the return ramp must not re-inflate them.
    assert _workout(db, plan, 3, 3).workout_type == "rest"
    assert _workout(db, plan, 3, 3).distance_km == 0
    assert _workout(db, plan, 4, 1).workout_type == "rest"
    assert _workout(db, plan, 4, 1).distance_km == 0

    # A non-rested future session is ramped *below* baseline (gentle return).
    wk4_long = _workout(db, plan, 4, 4)
    assert wk4_long.workout_type == "long"
    assert 0 < wk4_long.distance_km < 12.0
