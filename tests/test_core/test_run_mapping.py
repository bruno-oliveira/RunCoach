"""Tests for run-to-plan mapping logic in AdaptationService."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, TrainingPlan, User, WeeklyPlan
from app.services.adaptation import AdaptationService


def _make_user(db: Session) -> User:
    """Create and persist a test user."""
    user = User(id=str(uuid.uuid4()), email="test@example.com", name="Test Runner")
    db.add(user)
    db.flush()
    return user


def _make_plan(
    db: Session,
    user_id: str,
    start_date: datetime,
    weeks_duration: int,
) -> TrainingPlan:
    """Create and persist a training plan."""
    plan = TrainingPlan(
        id=str(uuid.uuid4()),
        user_id=user_id,
        target_distance="10",
        current_weekly_km=30.0,
        weeks_duration=weeks_duration,
        start_date=start_date,
        plan_data="[]",
    )
    db.add(plan)
    db.flush()
    return plan


def _make_week(
    db: Session,
    plan_id: str,
    week_number: int,
    total_km: float,
) -> WeeklyPlan:
    """Create and persist a weekly plan."""
    week = WeeklyPlan(
        id=str(uuid.uuid4()),
        training_plan_id=plan_id,
        week_number=week_number,
        total_km=total_km,
    )
    db.add(week)
    db.flush()
    return week


def _make_workout(
    db: Session,
    weekly_plan_id: str,
    day_of_week: int,
    workout_type: str,
    distance_km: float,
) -> DailyWorkout:
    """Create and persist a daily workout."""
    workout = DailyWorkout(
        id=str(uuid.uuid4()),
        weekly_plan_id=weekly_plan_id,
        day_of_week=day_of_week,
        workout_type=workout_type,
        distance_km=distance_km,
    )
    db.add(workout)
    db.flush()
    return workout


def _make_run(
    db: Session,
    user_id: str,
    date: datetime,
    distance_km: float,
    duration_minutes: float = 30.0,
) -> RunLog:
    """Create and persist a run log entry."""
    run = RunLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        date=date,
        distance_km=distance_km,
        duration_minutes=duration_minutes,
        avg_pace_min_km=duration_minutes / distance_km if distance_km else None,
    )
    db.add(run)
    db.flush()
    return run


class TestRunToPlanMapping:
    """Tests for AdaptationService.map_runs_to_plan."""

    def test_swapped_day_runs_match_by_distance(self, test_db: Session):
        """Runs done on adjacent swapped days should map to workouts by distance.

        When a user swaps two workouts scheduled on adjacent days (e.g., does
        the tempo on Monday and the easy on Tuesday), the scoring function
        (date_penalty * 3.0 + dist_diff) should prefer the 1-day-off exact
        distance match (score 3.0) over the same-day 5km-off match (score 5.0).
        """
        service = AdaptationService()
        user = _make_user(test_db)

        # Plan starts Monday 2026-01-05
        plan = _make_plan(
            test_db, user.id,
            start_date=datetime(2026, 1, 5, 0, 0),
            weeks_duration=1,
        )
        week = _make_week(test_db, plan.id, week_number=1, total_km=31.0)

        # Workouts: Mon easy 5km, Tue tempo 10km, Sat long 16km
        wo_mon_easy = _make_workout(test_db, week.id, day_of_week=1, workout_type="easy", distance_km=5.0)
        wo_tue_tempo = _make_workout(test_db, week.id, day_of_week=2, workout_type="tempo", distance_km=10.0)
        wo_sat_long = _make_workout(test_db, week.id, day_of_week=6, workout_type="long", distance_km=16.0)

        # User swapped Mon/Tue: ran 10km Monday (the tempo), 5km Tuesday (the easy)
        run_mon = _make_run(test_db, user.id, datetime(2026, 1, 5, 7, 30), distance_km=10.0)
        run_tue = _make_run(test_db, user.id, datetime(2026, 1, 6, 7, 30), distance_km=5.0)
        run_sat = _make_run(test_db, user.id, datetime(2026, 1, 10, 8, 0), distance_km=16.0)
        test_db.commit()

        result = service.map_runs_to_plan(plan.id, user.id, test_db, dry_run=True)

        proposals = result["proposals"]
        assert len(proposals) == 3

        # Build a lookup: run_id -> matched workout_id
        mapping = {p["run_id"]: p["workout_id"] for p in proposals}

        # Monday 10km run -> Tue tempo 10km (score: 1*3+0=3 beats Mon easy 1*3+5=5)
        assert mapping[run_mon.id] == wo_tue_tempo.id
        # Tuesday 5km run -> Mon easy 5km (score: 1*3+0=3 beats Tue tempo 1*3+5=5)
        assert mapping[run_tue.id] == wo_mon_easy.id
        # Saturday 16km run -> Saturday long 16km (exact match both date and distance)
        assert mapping[run_sat.id] == wo_sat_long.id

    def test_run_on_recovery_day_maps_to_recovery_workout(self, test_db: Session):
        """A run on a recovery day should be linked to the recovery workout.

        Users who run on planned rest/recovery days should see those runs on
        their plan — not silently dropped as volume-only.
        """
        service = AdaptationService()
        user = _make_user(test_db)

        # Plan starts Monday 2026-01-05
        plan = _make_plan(
            test_db, user.id,
            start_date=datetime(2026, 1, 5, 0, 0),
            weeks_duration=1,
        )
        week = _make_week(test_db, plan.id, week_number=1, total_km=13.0)

        # Workouts: Mon easy 5km, Tue recovery 0km, Wed tempo 8km
        wo_mon_easy = _make_workout(test_db, week.id, day_of_week=1, workout_type="easy", distance_km=5.0)
        wo_tue_recovery = _make_workout(test_db, week.id, day_of_week=2, workout_type="recovery", distance_km=0.0)
        wo_wed_tempo = _make_workout(test_db, week.id, day_of_week=3, workout_type="tempo", distance_km=8.0)

        # User ran on all three days including the recovery day
        run_mon = _make_run(test_db, user.id, datetime(2026, 1, 5, 7, 0), distance_km=5.0)
        run_tue = _make_run(test_db, user.id, datetime(2026, 1, 6, 7, 0), distance_km=6.0)
        run_wed = _make_run(test_db, user.id, datetime(2026, 1, 7, 7, 0), distance_km=8.0)
        test_db.commit()

        result = service.map_runs_to_plan(plan.id, user.id, test_db, dry_run=True)

        proposals = result["proposals"]
        # All 3 runs should appear in proposals
        assert len(proposals) == 3

        mapping = {p["run_id"]: p["workout_id"] for p in proposals}

        # Monday and Wednesday runs should match their exact workouts
        assert mapping[run_mon.id] == wo_mon_easy.id
        assert mapping[run_wed.id] == wo_wed_tempo.id

        # Tuesday run should be linked to the recovery workout, NOT volume-only
        assert mapping[run_tue.id] == wo_tue_recovery.id

        # Verify no proposals are volume-only — all runs matched to workouts
        match_types = {p["run_id"]: p["match_type"] for p in proposals}
        assert all(mt == "workout" for mt in match_types.values())

    def test_multiple_weeks_mapping(self, test_db: Session):
        """Runs should map to the correct week without cross-week contamination."""
        service = AdaptationService()
        user = _make_user(test_db)

        # Plan starts Monday 2026-01-05, 2 weeks
        plan = _make_plan(
            test_db, user.id,
            start_date=datetime(2026, 1, 5, 0, 0),
            weeks_duration=2,
        )

        # Week 1: Mon easy 5km, Wed tempo 8km, Sat long 12km
        week1 = _make_week(test_db, plan.id, week_number=1, total_km=25.0)
        wo_w1_mon = _make_workout(test_db, week1.id, day_of_week=1, workout_type="easy", distance_km=5.0)
        wo_w1_wed = _make_workout(test_db, week1.id, day_of_week=3, workout_type="tempo", distance_km=8.0)
        wo_w1_sat = _make_workout(test_db, week1.id, day_of_week=6, workout_type="long", distance_km=12.0)

        # Week 2: Mon easy 5km, Wed tempo 8km, Sat long 12km
        week2 = _make_week(test_db, plan.id, week_number=2, total_km=25.0)
        wo_w2_mon = _make_workout(test_db, week2.id, day_of_week=1, workout_type="easy", distance_km=5.0)
        wo_w2_wed = _make_workout(test_db, week2.id, day_of_week=3, workout_type="tempo", distance_km=8.0)
        wo_w2_sat = _make_workout(test_db, week2.id, day_of_week=6, workout_type="long", distance_km=12.0)

        # Week 1 runs
        run_w1_mon = _make_run(test_db, user.id, datetime(2026, 1, 5, 7, 0), distance_km=5.0)
        run_w1_wed = _make_run(test_db, user.id, datetime(2026, 1, 7, 7, 0), distance_km=8.0)
        run_w1_sat = _make_run(test_db, user.id, datetime(2026, 1, 10, 8, 0), distance_km=12.0)

        # Week 2 runs
        run_w2_mon = _make_run(test_db, user.id, datetime(2026, 1, 12, 7, 0), distance_km=5.0)
        run_w2_wed = _make_run(test_db, user.id, datetime(2026, 1, 14, 7, 0), distance_km=8.0)
        run_w2_sat = _make_run(test_db, user.id, datetime(2026, 1, 17, 8, 0), distance_km=12.0)
        test_db.commit()

        result = service.map_runs_to_plan(plan.id, user.id, test_db, dry_run=True)

        proposals = result["proposals"]
        assert len(proposals) == 6

        mapping = {p["run_id"]: p["workout_id"] for p in proposals}
        week_mapping = {p["run_id"]: p["week"] for p in proposals}

        # Week 1 runs map to week 1 workouts
        assert mapping[run_w1_mon.id] == wo_w1_mon.id
        assert mapping[run_w1_wed.id] == wo_w1_wed.id
        assert mapping[run_w1_sat.id] == wo_w1_sat.id
        assert week_mapping[run_w1_mon.id] == 1
        assert week_mapping[run_w1_wed.id] == 1
        assert week_mapping[run_w1_sat.id] == 1

        # Week 2 runs map to week 2 workouts
        assert mapping[run_w2_mon.id] == wo_w2_mon.id
        assert mapping[run_w2_wed.id] == wo_w2_wed.id
        assert mapping[run_w2_sat.id] == wo_w2_sat.id
        assert week_mapping[run_w2_mon.id] == 2
        assert week_mapping[run_w2_wed.id] == 2
        assert week_mapping[run_w2_sat.id] == 2
