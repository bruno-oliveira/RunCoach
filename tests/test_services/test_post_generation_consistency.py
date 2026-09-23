"""Every post-generation writer leaves card, steps and rows in agreement.

Regression coverage for the September 2026 consistency review: undo and reset
restored a card's distance but not its steps, an eased tempo kept its reps,
pace recalibration never reached the steps the watch runs, a race-day swap
split the ORM from plan_data, and a type swap trusted any workout id.
"""

import copy
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.contexts.plan.adaptation import intent_service, type_swapper
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.plan_creation_helpers import persist_weekly_workouts
from app.contexts.plan.week_adjustment_service import apply_week_action, swap_week_days
from app.core.time_utils import local_today, use_timezone
from app.core.training.workouts.workout_steps import (
    _compute_distance_from_steps,
    repace_steps,
)
from app.exceptions import ConflictException
from app.infrastructure.integrations.intervals_service import IntervalsService
from app.models import DailyWorkout, TrainingPlan, User, WeeklyPlan

_QUALITY = {"tempo", "interval", "hill", "vo2max", "race_pace", "fartlek"}
_MONDAY = date(2026, 9, 21)


def _make_plan(db, *, email="runner@example.com", current_week=1) -> TrainingPlan:
    user = User(email=email, google_id=f"g-{email}", name="Runner")
    db.add(user)
    db.flush()
    plan_data = TrainingPlanGenerator().generate_plan(30, 10, 10, 4, vdot=45)
    start = _MONDAY - timedelta(weeks=current_week - 1)
    plan = TrainingPlan(
        user_id=user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=10,
        max_runs_per_week=4,
        plan_data=plan_data,
        vdot=45,
        start_date=datetime.combine(start, datetime.min.time()),
    )
    db.add(plan)
    db.flush()
    persist_weekly_workouts(plan, plan_data, db)
    db.flush()
    for week in plan_data:
        for card in week["daily_workouts"]:
            if card.get("key_workout_id"):
                row = _row(db, plan, week["week"], card["day"])
                row.key_workout_id = card["key_workout_id"]
    db.commit()
    return plan


def _row(db, plan, week, day) -> DailyWorkout:
    return (
        db.query(DailyWorkout)
        .join(WeeklyPlan)
        .filter(
            WeeklyPlan.training_plan_id == plan.id,
            WeeklyPlan.week_number == week,
            DailyWorkout.day_of_week == day,
        )
        .one()
    )


def _card(plan, week, day):
    wk = next(w for w in plan.plan_data if w["week"] == week)
    return next(c for c in wk["daily_workouts"] if c["day"] == day)


def _first_quality_week(plan_data):
    for week in plan_data:
        if any(c["type"] in _QUALITY for c in week["daily_workouts"]):
            return week["week"]
    raise AssertionError("generated plan has no quality session")


def _assert_cards_match_steps(plan, week):
    wk = next(w for w in plan.plan_data if w["week"] == week)
    for card in wk["daily_workouts"]:
        steps = card.get("steps") or []
        if not steps or not card.get("distance"):
            continue
        assert _compute_distance_from_steps(steps) == pytest.approx(
            card["distance"], abs=0.2
        ), card
    assert wk["total_km"] == pytest.approx(
        sum(c.get("distance") or 0 for c in wk["daily_workouts"]), abs=0.05
    )


@pytest.fixture
def frozen_monday(monkeypatch):
    """Make "today" the Monday the test plans are anchored to."""
    monkeypatch.setattr(
        "app.contexts.plan.adaptation._helpers.local_today", lambda: _MONDAY
    )
    return _MONDAY


def test_eased_hard_session_loses_its_reps_and_undo_restores_them(
    test_db, frozen_monday
):
    probe = TrainingPlanGenerator().generate_plan(30, 10, 10, 4, vdot=45)
    week = _first_quality_week(probe)
    plan = _make_plan(test_db, current_week=week)
    hard_day = next(c["day"] for c in _card_week(plan, week) if c["type"] in _QUALITY)
    original = copy.deepcopy(_card(plan, week, hard_day))
    original_key = _row(test_db, plan, week, hard_day).key_workout_id

    intent_service.apply_intent(plan.id, plan.user_id, "feeling_tired", {}, test_db)
    test_db.refresh(plan)

    eased = _card(plan, week, hard_day)
    assert eased["type"] == "easy"
    assert "key_workout_id" not in eased
    assert _row(test_db, plan, week, hard_day).key_workout_id is None
    _assert_cards_match_steps(plan, week)

    intent_service.undo_last_change(plan.id, plan.user_id, test_db)
    test_db.refresh(plan)

    restored = _card(plan, week, hard_day)
    for field in ("type", "distance", "steps", "description"):
        assert restored.get(field) == original.get(field), field
    assert _row(test_db, plan, week, hard_day).key_workout_id == original_key


def _card_week(plan, week):
    return next(w for w in plan.plan_data if w["week"] == week)["daily_workouts"]


def test_reset_week_restores_steps_not_just_distance(test_db, frozen_monday):
    plan = _make_plan(test_db)
    target_week = 3
    week_data = next(w for w in plan.plan_data if w["week"] == target_week)
    apply_week_action(
        "bump", plan, plan.plan_data, week_data, target_week, plan.id, test_db
    )
    test_db.commit()

    week_data = next(w for w in plan.plan_data if w["week"] == target_week)
    apply_week_action(
        "reset_week", plan, plan.plan_data, week_data, target_week, plan.id, test_db
    )
    test_db.commit()
    test_db.refresh(plan)

    _assert_cards_match_steps(plan, target_week)
    for card in _card_week(plan, target_week):
        row = _row(test_db, plan, target_week, card["day"])
        assert card["distance"] == row.distance_km


def test_race_day_swap_is_refused_and_changes_nothing(test_db, frozen_monday):
    plan = _make_plan(test_db)
    last = plan.weeks_duration
    race_day = next(c["day"] for c in _card_week(plan, last) if c["type"] == "race")
    other = 1 if race_day != 1 else 2
    rows_before = {
        r.id: r.day_of_week
        for r in test_db.query(DailyWorkout)
        .join(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan.id, WeeklyPlan.week_number == last)
    }

    with pytest.raises(ConflictException):
        swap_week_days(plan, last, other, race_day, test_db)

    test_db.rollback()
    rows_after = {
        r.id: r.day_of_week
        for r in test_db.query(DailyWorkout)
        .join(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan.id, WeeklyPlan.week_number == last)
    }
    assert rows_after == rows_before


def test_day_swap_moves_rows_and_cards_together(test_db, frozen_monday):
    plan = _make_plan(test_db)
    revision = plan.adaptation_revision or 0
    first, second = 2, 4
    type_first = _card(plan, 2, first)["type"]
    type_second = _card(plan, 2, second)["type"]

    swap_week_days(plan, 2, first, second, test_db)
    test_db.commit()
    test_db.refresh(plan)

    assert _card(plan, 2, second)["type"] == type_first
    assert _card(plan, 2, first)["type"] == type_second
    assert _row(test_db, plan, 2, second).workout_type == type_first
    assert _row(test_db, plan, 2, first).workout_type == type_second
    assert plan.adaptation_revision == revision + 1


def test_type_swap_cannot_touch_another_runners_workout(test_db, frozen_monday):
    mine = _make_plan(test_db, email="me@example.com")
    theirs = _make_plan(test_db, email="them@example.com")
    victim = _row(test_db, theirs, 2, 2)
    before = victim.workout_type

    result = type_swapper.apply_swap(victim.id, mine.id, mine.user_id, "tempo", test_db)

    assert result is None
    test_db.refresh(victim)
    assert victim.workout_type == before


def test_ease_today_softens_only_today(test_db, frozen_monday):
    plan = _make_plan(test_db)
    today_row = _row(test_db, plan, 1, 1)
    if not (today_row.distance_km or 0) > 0:
        pytest.skip("generated week 1 starts with a rest day")
    tomorrow_before = [
        (_row(test_db, plan, 1, d).distance_km or 0) for d in range(2, 8)
    ]
    base = today_row.distance_km

    intent_service.apply_intent(plan.id, plan.user_id, "ease_today", {}, test_db)

    test_db.refresh(today_row)
    assert today_row.distance_km == pytest.approx(round(base * 0.75, 1), abs=0.3)
    assert [
        (_row(test_db, plan, 1, d).distance_km or 0) for d in range(2, 8)
    ] == tomorrow_before


def test_repace_steps_moves_zone_paces_and_keeps_fixed_ones():
    old = {"T": {"pace_str": "4:40/km"}, "E": {"pace_str": "5:40/km"}}
    new = {"T": {"pace_str": "4:30/km"}, "E": {"pace_str": "5:30/km"}}
    steps = [
        {"kind": "run", "pace_zone": "T", "pace_str": "4:40/km"},
        # A backyard loop pace comes from the loop budget, not the zone.
        {"kind": "run", "pace_zone": "E", "pace_str": "7:05/km"},
        {"kind": "rest", "pace_zone": None, "pace_str": None},
    ]

    assert repace_steps(steps, old, new) == 1
    assert steps[0]["pace_str"] == "4:30/km"
    assert steps[1]["pace_str"] == "7:05/km"


def test_use_timezone_binds_a_stored_zone_outside_requests():
    zone = "Etc/GMT-14"
    with use_timezone(zone):
        assert local_today() == datetime.now(ZoneInfo(zone)).date()


@pytest.mark.parametrize(
    ("raw", "expected"), [(7, 7), (6.6, 7), (0, None), (None, None), ("x", None)]
)
def test_intervals_rpe_reaches_imported_runs(raw, expected):
    activity = {
        "id": "i1",
        "start_date_local": "2026-09-20T07:00:00",
        "icu_distance": 10000,
        "moving_time": 3000,
        "icu_rpe": raw,
    }
    run = IntervalsService.map_activity_to_run_log(activity, "user-1")
    assert run.perceived_effort == expected
