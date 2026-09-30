"""Gap analysis: how far a runner's log is from the plan, by dimension.

`analyze_gaps` is what the analytics page and the "what should I fix?" list read,
so its preconditions and its per-dimension numbers matter. It was at ~21% coverage
— the least-covered business logic that changes what a runner is told. These
tests pin the report's shape, the volume/long-run arithmetic against known runs,
and the nullable columns the computation reads (`distance_km`, `avg_pace_min_km`).
"""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from app.contexts.runner.fitness.gap_analysis_service import GapAnalysisService
from app.core.time_utils import local_today
from app.models import RunLog, TrainingPlan, User

WEEKS = 4
PLANNED_KM = 30.0


def _plan_data(weeks: int = WEEKS) -> list[dict]:
    return [
        {
            "week": week,
            "total_km": PLANNED_KM,
            "daily_workouts": [
                {"day": 2, "type": "easy", "distance": 6.0},
                {"day": 7, "type": "long", "distance": 12.0},
            ],
        }
        for week in range(1, weeks + 1)
    ]


def _user(db: Session) -> User:
    user = User(id=str(uuid4()), email=f"{uuid4().hex[:8]}@t.com")
    db.add(user)
    db.flush()
    return user


# 13 days in: week 1 (days 0-6) and week 2 (days 7-13) are both complete, and
# week 3 has not started — so the averages cover exactly two weeks.
STARTED_DAYS_AGO = 13


def _plan(
    db: Session,
    user: User,
    *,
    days_ago: int | None = STARTED_DAYS_AGO,
    plan_data: list[dict] | None = None,
    weeks: int | None = WEEKS,
) -> TrainingPlan:
    plan = TrainingPlan(
        id=str(uuid4()),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=weeks,
        start_date=(
            local_today() - timedelta(days=days_ago) if days_ago is not None else None
        ),
        plan_data=_plan_data() if plan_data is None else plan_data,
    )
    db.add(plan)
    db.flush()
    return plan


def _run(
    db: Session,
    user: User,
    plan: TrainingPlan,
    *,
    day_offset: int,
    distance_km: float | None = 8.0,
    avg_pace_min_km: float | None = 5.5,
) -> None:
    """Log a run ``day_offset`` days after the plan's start date."""
    assert plan.start_date is not None
    db.add(
        RunLog(
            id=str(uuid4()),
            user_id=user.id,
            training_plan_id=plan.id,
            date=plan.start_date + timedelta(days=day_offset),
            distance_km=distance_km,
            duration_minutes=44.0,
            avg_pace_min_km=avg_pace_min_km,
        )
    )
    db.flush()


def test_a_plan_with_no_runs_has_nothing_to_analyse(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user)

    assert GapAnalysisService.analyze_gaps(plan, user.id, test_db) is None


def test_a_plan_with_no_start_date_has_nothing_to_analyse(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user, days_ago=None)

    assert GapAnalysisService.analyze_gaps(plan, user.id, test_db) is None


def test_a_plan_with_no_plan_data_has_nothing_to_analyse(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user, plan_data=[])
    _run(test_db, user, plan, day_offset=1)

    assert GapAnalysisService.analyze_gaps(plan, user.id, test_db) is None


def test_a_plan_that_has_not_started_has_nothing_to_analyse(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user, days_ago=-7)  # starts next week

    assert GapAnalysisService.analyze_gaps(plan, user.id, test_db) is None
    assert GapAnalysisService.analyze_gaps_weekly(plan, user.id, test_db) is None


def test_a_plan_with_no_duration_has_nothing_to_analyse(test_db: Session):
    """`weeks_duration` is nullable; there is no window to measure against."""
    user = _user(test_db)
    plan = _plan(test_db, user, weeks=None)

    assert GapAnalysisService.analyze_gaps(plan, user.id, test_db) is None


def test_the_report_covers_every_dimension(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user)
    _run(test_db, user, plan, day_offset=1)

    report = GapAnalysisService.analyze_gaps(plan, user.id, test_db)

    assert report is not None
    assert set(report) == {
        "volume_gap",
        "long_run_gap",
        "pace_gap",
        "consistency",
        "fitness_trajectory",
        "elevation_gap",
        "mountain_simulation_gap",
        "top_actions",
        "current_week",
        "total_weeks",
    }
    assert report["total_weeks"] == WEEKS
    assert 1 <= report["current_week"] <= WEEKS
    assert isinstance(report["top_actions"], list)


def test_a_heavy_week_reads_as_on_track_volume(test_db: Session):
    """Two full weeks of planned volume → no volume deficit."""
    user = _user(test_db)
    plan = _plan(test_db, user)
    for day_offset in (0, 3, 7, 10):
        _run(test_db, user, plan, day_offset=day_offset, distance_km=15.0)

    report = GapAnalysisService.analyze_gaps(plan, user.id, test_db)

    volume = report["volume_gap"]
    assert volume["planned_weekly_avg_km"] == PLANNED_KM
    # 4 runs of 15 km over 2 weeks = 30 km/week, exactly the plan.
    assert volume["actual_weekly_avg_km"] == PLANNED_KM
    assert volume["deficit_pct"] == 0
    assert volume["verdict"] == "on_track"


def test_a_low_volume_week_reads_as_behind(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user)
    for day_offset in (0, 3, 7, 10):
        _run(test_db, user, plan, day_offset=day_offset, distance_km=3.0)

    report = GapAnalysisService.analyze_gaps(plan, user.id, test_db)

    volume = report["volume_gap"]
    # 12 km logged against two 30 km weeks → 12/30 short, an 80% deficit.
    assert volume["deficit_pct"] == 80
    assert volume["verdict"] == "far_behind"


def test_a_peak_long_run_shortfall_is_reported(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user)
    _run(test_db, user, plan, day_offset=1, distance_km=8.0)

    report = GapAnalysisService.analyze_gaps(plan, user.id, test_db)

    long_run = report["long_run_gap"]
    # The plan peaks at a 12 km long run; 8 km is a 33% shortfall.
    assert long_run["target_km"] == 12.0
    assert long_run["longest_actual_km"] == 8.0
    assert long_run["deficit_pct"] == 33.3


def test_runs_with_null_columns_do_not_break_the_analysis(test_db: Session):
    """`distance_km` and `avg_pace_min_km` are both nullable columns."""
    user = _user(test_db)
    plan = _plan(test_db, user)
    _run(test_db, user, plan, day_offset=1, distance_km=None, avg_pace_min_km=None)
    _run(test_db, user, plan, day_offset=3, distance_km=10.0, avg_pace_min_km=None)

    report = GapAnalysisService.analyze_gaps(plan, user.id, test_db)

    assert report is not None
    # The missing distance counts as 0 km — over two weeks, 10 km is 5 km/week.
    assert report["volume_gap"]["actual_weekly_avg_km"] == 5.0
    assert report["long_run_gap"]["longest_actual_km"] == 10.0
    # …and a run with no pace simply does not contribute to the pace gap.
    assert report["pace_gap"]["current_pace_min_km"] is None


def test_weekly_breakpoints_trend_up_to_the_current_week(test_db: Session):
    user = _user(test_db)
    plan = _plan(test_db, user)
    _run(test_db, user, plan, day_offset=1, distance_km=15.0)

    breakpoints = GapAnalysisService.analyze_gaps_weekly(plan, user.id, test_db)

    assert breakpoints is not None
    assert [bp["week"] for bp in breakpoints] == [1, 2]
    assert set(breakpoints[0]) == {
        "week",
        "volume_pct",
        "long_run_pct",
        "actual_km",
        "planned_km",
    }
    assert breakpoints[0]["actual_km"] == 15.0
    assert breakpoints[0]["planned_km"] == PLANNED_KM
    assert breakpoints[0]["volume_pct"] == 50.0


def test_runs_outside_the_plan_window_are_dropped_from_the_trend(test_db: Session):
    """A pre-plan run and one from a week that has not begun do not count."""
    user = _user(test_db)
    plan = _plan(test_db, user)
    _run(test_db, user, plan, day_offset=1, distance_km=15.0)  # week 1
    _run(test_db, user, plan, day_offset=-5, distance_km=99.0)  # before the plan
    _run(test_db, user, plan, day_offset=STARTED_DAYS_AGO + 1, distance_km=99.0)

    breakpoints = GapAnalysisService.analyze_gaps_weekly(plan, user.id, test_db)

    assert [bp["week"] for bp in breakpoints] == [1, 2]
    assert breakpoints[0]["actual_km"] == 15.0
    assert breakpoints[1]["actual_km"] == 0
    assert breakpoints[1]["planned_km"] == PLANNED_KM


def test_weekly_breakpoints_work_without_runs(test_db: Session):
    """The trend chart is drawn from the plan even before anything is logged."""
    user = _user(test_db)
    plan = _plan(test_db, user)

    breakpoints = GapAnalysisService.analyze_gaps_weekly(plan, user.id, test_db)

    assert breakpoints is not None
    assert len(breakpoints) == 2
    assert all(bp["actual_km"] == 0 for bp in breakpoints)
