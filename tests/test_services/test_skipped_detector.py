"""Skipped vs rescheduled classification.

This module had no test coverage before the stimulus-aware rule landed, which is
how a week-level volume heuristic survived while mislabelling exactly the
sessions a runner most needs to do. The rule these tests pin:

* *volume-defined* sessions (easy, long, medium_long) are judged on the week —
  "rescheduled" when the week still met >= 80 % of its planned volume — and
* *intensity-defined* sessions (``QUALITY_STIMULUS_TYPES``) are judged on
  whether the week delivered quality work at all, so extra easy miles can no
  longer excuse a missed interval.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest
from sqlalchemy.orm import Session

from app.contexts.plan.adaptation.skipped_detector import detect_skipped_workouts
from app.models import DailyWorkout, RunLog, TrainingPlan, User, WeeklyPlan

# Far enough back that every workout the helpers below build is in the past for
# ``local_today``, whichever zone the suite runs in.
PLAN_START = datetime.now() - timedelta(days=56)

PLAN_ID = "skip-plan-1"


@pytest.fixture
def owner(test_db: Session) -> User:
    user = User(id="skip-owner", email="skip@example.com", name="Skip Owner")
    test_db.add(user)
    test_db.commit()
    return user


def _build_week(
    test_db: Session,
    owner: User,
    planned: List[tuple],
    total_km: float,
    runs: List[Dict[str, Any]],
) -> TrainingPlan:
    """A one-week plan: ``planned`` is a list of ``(day, type, km)`` cards.

    ``runs`` entries are ``{day_offset, distance_km, workout_type, linked_to}``,
    where ``linked_to`` names the planned day the run is attached to (omitted
    means the run is unlinked — the case this module classifies).
    """
    plan = TrainingPlan(
        id=PLAN_ID,
        user_id=owner.id,
        current_weekly_km=total_km,
        target_distance="10",
        weeks_duration=4,
        vdot=45.0,
        start_date=PLAN_START,
        plan_data=[
            {
                "week": 1,
                "total_km": total_km,
                "phase": "build",
                "daily_workouts": [
                    {"day": day, "type": wtype, "distance": km}
                    for (day, wtype, km) in planned
                ],
            }
        ],
    )
    test_db.add(plan)
    test_db.commit()

    week = WeeklyPlan(
        id="skip-wp-1",
        training_plan_id=plan.id,
        week_number=1,
        total_km=total_km,
    )
    test_db.add(week)
    test_db.flush()

    workout_ids = {}
    for day, wtype, km in planned:
        workout = DailyWorkout(
            id=f"skip-wo-{day}",
            weekly_plan_id=week.id,
            day_of_week=day,
            workout_type=wtype,
            distance_km=km,
            baseline_distance_km=km,
        )
        test_db.add(workout)
        workout_ids[day] = workout.id
    test_db.flush()

    for spec in runs:
        linked_day = spec.get("linked_to")
        test_db.add(
            RunLog(
                id=spec["id"],
                user_id=owner.id,
                training_plan_id=plan.id,
                daily_workout_id=workout_ids.get(linked_day),
                date=PLAN_START + timedelta(days=spec["day_offset"]),
                distance_km=spec["distance_km"],
                duration_minutes=spec["distance_km"] * 6,
                avg_pace_min_km=6.0,
                workout_type=spec["workout_type"],
            )
        )
    test_db.commit()
    return plan


def test_missed_interval_is_not_excused_by_easy_volume(test_db, owner):
    """The regression this rule exists for.

    The week hits its volume bar on easy miles alone, but no quality work was
    done. The old volume-only rule called the missed interval "rescheduled".
    """
    _build_week(
        test_db,
        owner,
        planned=[(3, "interval", 10.0)],
        total_km=10.0,
        runs=[
            {
                "id": "run-junk-miles",
                "day_offset": 3,
                "distance_km": 10.0,
                "workout_type": "easy",
            }
        ],
    )

    assert detect_skipped_workouts(PLAN_ID, test_db) == {
        "skipped": 1,
        "rescheduled": 0,
    }


def test_moved_quality_session_still_counts_as_rescheduled(test_db, owner):
    """Same missed card, but the week did deliver quality work of some kind."""
    _build_week(
        test_db,
        owner,
        planned=[(3, "interval", 10.0)],
        total_km=10.0,
        runs=[
            {
                "id": "run-moved-quality",
                "day_offset": 3,
                "distance_km": 10.0,
                "workout_type": "tempo",
            }
        ],
    )

    assert detect_skipped_workouts(PLAN_ID, test_db) == {
        "skipped": 0,
        "rescheduled": 1,
    }


def test_one_quality_run_cannot_excuse_two_missed_quality_sessions(test_db, owner):
    """Delivered quality runs are consumed as they are credited."""
    _build_week(
        test_db,
        owner,
        planned=[(2, "interval", 10.0), (3, "tempo", 10.0)],
        total_km=20.0,
        runs=[
            {
                "id": "run-single-quality",
                "day_offset": 2,
                "distance_km": 20.0,
                "workout_type": "tempo",
            }
        ],
    )

    assert detect_skipped_workouts(PLAN_ID, test_db) == {
        "skipped": 1,
        "rescheduled": 1,
    }


@pytest.mark.parametrize(
    "distance_km, expected",
    [
        (4.0, {"skipped": 1, "rescheduled": 0}),  # 40 % of the week — missed
        (9.0, {"skipped": 0, "rescheduled": 1}),  # 90 % of the week — rescheduled
    ],
    ids=["volume_short", "volume_met"],
)
def test_volume_defined_session_keeps_the_volume_rule(
    test_db, owner, distance_km, expected
):
    """Volume-defined sessions are unchanged: the week's volume is the measure."""
    _build_week(
        test_db,
        owner,
        planned=[(2, "easy", 10.0)],
        total_km=10.0,
        runs=[
            {
                "id": "run-easy",
                "day_offset": 2,
                "distance_km": distance_km,
                "workout_type": "easy",
            }
        ],
    )

    assert detect_skipped_workouts(PLAN_ID, test_db) == expected


def test_long_run_stays_volume_judged(test_db, owner):
    """The deliberate boundary: a long run is volume-defined, not intensity.

    It is usually the week's largest single contributor, so dropping it pulls
    the week under the volume bar on its own — the proxy the quality rule
    replaces does not fail here.
    """
    _build_week(
        test_db,
        owner,
        planned=[(6, "long", 30.0)],
        total_km=30.0,
        runs=[
            {
                "id": "run-long-missed",
                "day_offset": 6,
                "distance_km": 30.0,
                "workout_type": "easy",
            }
        ],
    )

    assert detect_skipped_workouts(PLAN_ID, test_db) == {
        "skipped": 0,
        "rescheduled": 1,
    }


def test_linked_workouts_are_never_classified(test_db, owner):
    """A workout the runner logged against keeps its card — nothing to judge."""
    _build_week(
        test_db,
        owner,
        planned=[(3, "interval", 10.0)],
        total_km=10.0,
        runs=[
            {
                "id": "run-linked",
                "day_offset": 3,
                "distance_km": 10.0,
                "workout_type": "interval",
                "linked_to": 3,
            }
        ],
    )

    assert detect_skipped_workouts(PLAN_ID, test_db) == {
        "skipped": 0,
        "rescheduled": 0,
    }


def test_unknown_plan_is_zeroed(test_db):
    assert detect_skipped_workouts("no-such-plan", test_db) == {
        "skipped": 0,
        "rescheduled": 0,
    }
