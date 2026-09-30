"""The adherence heatmap: what each workout-type cell reports for a plan.

The grid is what the analytics page shows a runner instead of a completion
percentage, so its states matter: `completed` (the session is linked to a logged
run), `rescheduled` (something was run that week, just not linked), `skipped`
(the week has passed with nothing) and `future` (the week has not arrived). There
was no test here at all before.
"""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from app.contexts.runner.fitness.adherence_service import compute_adherence_heatmap
from app.core.time_utils import local_today
from app.models import DailyWorkout, RunLog, TrainingPlan, User, WeeklyPlan

WEEKS = 4


def _plan_data(weeks: int = WEEKS) -> list[dict]:
    return [
        {
            "week": week,
            "total_km": 30.0,
            "daily_workouts": [
                {"day": 2, "type": "easy", "distance": 6.0},
                {"day": 4, "type": "tempo", "distance": 8.0},
            ],
        }
        for week in range(1, weeks + 1)
    ]


def _user(db: Session) -> User:
    user = User(id=str(uuid4()), email=f"{uuid4().hex[:8]}@t.com")
    db.add(user)
    db.flush()
    return user


def _plan(
    db: Session, user: User, *, started_days_ago: int | None = 10
) -> TrainingPlan:
    plan = TrainingPlan(
        id=str(uuid4()),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=WEEKS,
        start_date=(
            local_today() - timedelta(days=started_days_ago)
            if started_days_ago is not None
            else None
        ),
        plan_data=_plan_data(),
    )
    db.add(plan)
    db.flush()
    return plan


def _workout(db: Session, plan: TrainingPlan, week: int, day: int, type_: str):
    weekly = WeeklyPlan(
        id=str(uuid4()), training_plan_id=plan.id, week_number=week, total_km=30.0
    )
    db.add(weekly)
    db.flush()
    workout = DailyWorkout(
        id=str(uuid4()),
        weekly_plan_id=weekly.id,
        day_of_week=day,
        workout_type=type_,
        distance_km=6.0,
    )
    db.add(workout)
    db.flush()
    return workout


def test_a_plan_without_a_start_date_is_unavailable(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user, started_days_ago=None)

    result = compute_adherence_heatmap(plan, user.id, test_db)

    assert result["available"] is False
    assert "start date" in result["reason"]


def test_the_grid_covers_every_plan_week_and_every_non_rest_type(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user)

    result = compute_adherence_heatmap(plan, user.id, test_db)

    assert result["available"] is True
    # rest/recovery never earn a column of their own.
    assert result["workout_types"] == ["easy", "tempo"]
    assert [row["week"] for row in result["grid"]] == [1, 2, 3, 4]
    for row in result["grid"]:
        assert set(row["cells"]) == {"easy", "tempo"}


def test_weeks_that_have_not_arrived_read_as_future(test_db: Session):
    user = _user(test_db)
    # 10 days in → week 2 is current, so weeks 3-4 are still ahead.
    plan = _plan(test_db, user)

    result = compute_adherence_heatmap(plan, user.id, test_db)

    assert result["current_week"] == 2
    by_week = {row["week"]: row["cells"] for row in result["grid"]}
    assert by_week[2]["easy"] == "skipped"
    assert by_week[3]["easy"] == "future"
    assert by_week[4]["tempo"] == "future"


def test_a_workout_linked_to_a_logged_run_reads_as_completed(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user)
    workout = _workout(test_db, plan, week=1, day=2, type_="easy")
    test_db.add(
        RunLog(
            id=str(uuid4()),
            user_id=user.id,
            training_plan_id=plan.id,
            daily_workout_id=workout.id,
            date=local_today() - timedelta(days=9),
            distance_km=6.0,
            duration_minutes=35.0,
        )
    )
    test_db.flush()

    result = compute_adherence_heatmap(plan, user.id, test_db)

    by_week = {row["week"]: row["cells"] for row in result["grid"]}
    assert by_week[1]["easy"] == "completed"
    # The other slot of that week is still unaccounted for.
    assert by_week[1]["tempo"] == "skipped"


def test_an_unlinked_run_in_the_week_reads_as_rescheduled(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user)
    _workout(test_db, plan, week=1, day=2, type_="easy")
    # A run inside week 1's window that is not linked to any planned workout —
    # the session happened, just not on the day it was written down.
    test_db.add(
        RunLog(
            id=str(uuid4()),
            user_id=user.id,
            training_plan_id=plan.id,
            date=local_today() - timedelta(days=8),
            distance_km=5.0,
            duration_minutes=30.0,
        )
    )
    test_db.flush()

    result = compute_adherence_heatmap(plan, user.id, test_db)

    by_week = {row["week"]: row["cells"] for row in result["grid"]}
    assert by_week[1]["easy"] == "rescheduled"


def test_a_run_with_no_date_is_ignored_rather_than_crashing(test_db: Session):
    """`RunLog.date` is a nullable column; the window check must tolerate None."""
    user = _user(test_db)
    plan = _plan(test_db, user)
    _workout(test_db, plan, week=1, day=2, type_="easy")
    test_db.add(
        RunLog(
            id=str(uuid4()),
            user_id=user.id,
            training_plan_id=plan.id,
            date=None,
            distance_km=5.0,
            duration_minutes=30.0,
        )
    )
    test_db.flush()

    result = compute_adherence_heatmap(plan, user.id, test_db)

    by_week = {row["week"]: row["cells"] for row in result["grid"]}
    # Undated runs cannot be placed in a week, so they do not mark one as done.
    assert by_week[1]["easy"] == "skipped"


def test_another_runners_runs_do_not_count(test_db: Session):
    user = _user(test_db)
    other = _user(test_db)
    plan = _plan(test_db, user)
    _workout(test_db, plan, week=1, day=2, type_="easy")
    test_db.add(
        RunLog(
            id=str(uuid4()),
            user_id=other.id,
            training_plan_id=plan.id,
            date=local_today() - timedelta(days=8),
            distance_km=5.0,
            duration_minutes=30.0,
        )
    )
    test_db.flush()

    result = compute_adherence_heatmap(plan, user.id, test_db)

    by_week = {row["week"]: row["cells"] for row in result["grid"]}
    assert by_week[1]["easy"] == "skipped"
