"""Assemble the Coach page: the runner's goal, their recent running, one read.

The page used to ask the runner to pick a plan and a period before it would
say anything, and then answered with a dashboard. It now takes no input. The
goal is whichever plan is in progress today; "recent" is a fixed window; and
the judgement is ``core.coaching.training_read``.

It lives in the application layer because the read needs both contexts: what
the plan asked for (plan) and what was actually run (runner). Every run in the
window counts, whether or not it was matched to a planned day — a runner who
swapped Tuesday for Wednesday did the work.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.contexts.plan.plan_status import in_progress_plan, plan_status
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.contexts.runner.fitness.personal_records_service import PersonalRecordsService
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.contexts.runner.repositories import SQLAlchemyRunRepository
from app.contexts.runner.single_runs import planned_runs_between
from app.core.coaching.intensity_split import intensity_split
from app.core.coaching.training_read import (
    GoalTime,
    GoalWindow,
    RecentTraining,
    TrainingRead,
    Week,
    read_training,
)
from app.core.training.periodization.plan_calendar import compute_current_week
from app.core.training.physiology.vdot_calculator import VDOTCalculator
from app.models import RunLog, TrainingPlan, User
from app.utils import parse_race_time_to_seconds, to_date

# Weeks drawn in the volume strip (the last one is the week in progress).
CHART_WEEKS = 8
# The window the split and run lengths are read over.
_RECENT_DAYS = 28
# How many completed plan weeks the goal is judged on.
_GOAL_WEEKS = 3
# A prediction is for the goal's distance when it is within this many km.
_SAME_DISTANCE_KM = 1.0


@dataclass(frozen=True)
class GoalView:
    """The plan the runner is training on, as the page names it."""

    plan_id: str
    label: str
    # "Week 6 of 12", or None when the plan has no measurable position.
    position: Optional[str]
    # Completed plan weeks the findings were judged on (0 = too early).
    weeks_judged: int
    # The goal time and the time current fitness predicts, formatted; both
    # None when the goal has no time or there is no honest prediction.
    goal_time: Optional[str] = None
    predicted_time: Optional[str] = None

    @property
    def url(self) -> str:
        return f"/plan/{self.plan_id}"


@dataclass(frozen=True)
class WeekBar:
    """One bar of the weekly-volume strip."""

    label: str
    km: float
    runs: int
    # Height as a percentage of the tallest week.
    height_pct: int
    in_progress: bool


@dataclass(frozen=True)
class CoachPage:
    read: TrainingRead
    goal: Optional[GoalView]
    weeks: list[WeekBar]
    records: list[dict[str, Any]]


def build_coach_page(user: User, db: Session, today: date) -> CoachPage:
    """Everything the Coach page shows for ``user`` on their local ``today``."""
    this_monday = today - timedelta(days=today.weekday())
    chart_start = this_monday - timedelta(weeks=CHART_WEEKS - 1)
    run_repo = SQLAlchemyRunRepository(db)
    runs = [
        run
        for run in run_repo.list_recent_for_user(
            user.id, since=datetime.combine(chart_start, time.min)
        )
        if run.date is not None
    ]

    plans = SQLAlchemyPlanRepository(db).list_by_user_recent_first(user.id)
    plan = in_progress_plan(plans, today)
    window = _goal_window(plan, user, db, runs, today) if plan is not None else None
    fitness = RacePredictorService.get_predictions_for_user(user.id, db)
    goal_time = _goal_time(plan, fitness, today) if plan is not None else None

    weekly = _weekly_totals(runs, chart_start)
    read = read_training(
        RecentTraining(
            weeks=_complete_weeks(weekly),
            days_since_last_run=_days_since_last_run(runs, run_repo, user, today),
            run_lengths_km=_recent_lengths(runs, today),
            split=intensity_split(
                (run.effective_workout_type, run.distance_km)
                for run in _since(runs, today - timedelta(days=_RECENT_DAYS))
            ),
            fitness_trend=fitness.get("vdot_trend"),
        ),
        has_goal=plan is not None,
        goal=window,
        goal_time=goal_time,
    )
    return CoachPage(
        read=read,
        goal=(_goal_view(plan, window, goal_time, today) if plan is not None else None),
        weeks=_week_bars(weekly, chart_start),
        records=_records(user, db),
    )


# -- Recent running ----------------------------------------------------------


def _run_day(run: RunLog) -> date:
    # Callers hold only dated runs; the fallback keeps the type honest.
    return to_date(run.date) or date.min


def _since(runs: list[RunLog], start: date) -> list[RunLog]:
    return [run for run in runs if _run_day(run) >= start]


def _weekly_totals(runs: list[RunLog], chart_start: date) -> list[Week]:
    """Distance and run count for each of the charted weeks, oldest first."""
    km = [0.0] * CHART_WEEKS
    count = [0] * CHART_WEEKS
    for run in runs:
        index = (_run_day(run) - chart_start).days // 7
        if 0 <= index < CHART_WEEKS and run.distance_km:
            km[index] += run.distance_km
            count[index] += 1
    return [Week(km=round(km[i], 1), runs=count[i]) for i in range(CHART_WEEKS)]


def _complete_weeks(weekly: list[Week]) -> list[Week]:
    """The finished weeks, from the first one the runner ran in.

    The week in progress is left out — on a Tuesday it always looks like a
    collapse — and so are the blank weeks before a new runner's first run,
    which are not weeks they skipped.
    """
    complete = weekly[:-1]
    first_active = next(
        (index for index, week in enumerate(complete) if week.runs), len(complete)
    )
    return complete[first_active:]


def _recent_lengths(runs: list[RunLog], today: date) -> list[float]:
    recent = _since(runs, today - timedelta(days=_RECENT_DAYS))
    return [run.distance_km for run in recent if run.distance_km]


def _days_since_last_run(
    runs: list[RunLog], run_repo: SQLAlchemyRunRepository, user: User, today: date
) -> Optional[int]:
    """Days since the runner last ran, looking past the chart if it is empty."""
    latest = runs[:1] or [
        run
        for run in run_repo.list_recent_for_user(user.id, limit=1)
        if run.date is not None
    ]
    if not latest:
        return None
    return max(0, (today - _run_day(latest[0])).days)


def _week_bars(weekly: list[Week], chart_start: date) -> list[WeekBar]:
    tallest = max((week.km for week in weekly), default=0.0)
    bars = []
    for index, week in enumerate(weekly):
        start = chart_start + timedelta(weeks=index)
        bars.append(
            WeekBar(
                label=f"{start.day} {start.strftime('%b')}",
                km=week.km,
                runs=week.runs,
                height_pct=round(week.km / tallest * 100) if tallest else 0,
                in_progress=index == len(weekly) - 1,
            )
        )
    return bars


# -- The goal ----------------------------------------------------------------


def _completed_plan_weeks(plan: TrainingPlan, today: date) -> int:
    start = to_date(plan.start_date)
    if start is None:
        return 0
    current = compute_current_week(
        start, today, total_weeks=plan.weeks_duration, pre_start=0
    )
    return max(0, current - 1)


def _goal_window(
    plan: TrainingPlan, user: User, db: Session, runs: list[RunLog], today: date
) -> Optional[GoalWindow]:
    """Planned versus run over the plan's last completed weeks.

    Returns:
        None while the plan has no completed week — there is nothing to judge.
    """
    start = to_date(plan.start_date)
    completed = _completed_plan_weeks(plan, today)
    if start is None or completed == 0:
        return None
    weeks = min(_GOAL_WEEKS, completed)
    window_start = start + timedelta(weeks=completed - weeks)
    window_end = start + timedelta(weeks=completed) - timedelta(days=1)

    planned = [
        run
        for run in planned_runs_between(user.id, db, window_start, window_end)
        if run.plan_id == plan.id
    ]
    done = [run for run in _since(runs, window_start) if _run_day(run) <= window_end]
    done_km = [run.distance_km for run in done if run.distance_km]
    planned_days = {run.on_date for run in planned}
    return GoalWindow(
        weeks=weeks,
        planned_sessions=len(planned_days),
        # Days run, not days matched: a session moved to another day was done.
        done_sessions=min(len(planned_days), len({_run_day(run) for run in done})),
        planned_km=sum(run.distance_km for run in planned),
        actual_km=sum(done_km),
        planned_long_km=max(
            (run.distance_km for run in planned if run.workout_type == "long"),
            default=0.0,
        ),
        longest_km=max(done_km, default=0.0),
    )


def _goal_time(
    plan: TrainingPlan, fitness: dict[str, Any], today: date
) -> Optional[GoalTime]:
    """The plan's goal time against the time the runner's fitness predicts.

    Only for a road goal with a time. A trail or backyard goal is decided by
    climb and by hours on feet, and a flat-road prediction held against it
    would be a confident number about the wrong race.

    Returns:
        None when there is no goal time, or no prediction for that distance.
    """
    if plan.is_trail or plan.is_backyard or not plan.goal_time:
        return None
    goal_seconds = parse_race_time_to_seconds(plan.goal_time)
    predicted_seconds = next(
        (
            prediction["seconds"]
            for name, prediction in fitness.get("predictions", {}).items()
            if name != "trail"
            and prediction["seconds"]
            and abs(prediction["distance_km"] - plan.target_distance_km)
            < _SAME_DISTANCE_KM
        ),
        None,
    )
    if not goal_seconds or predicted_seconds is None:
        return None
    weeks_left = (plan.weeks_duration or 0) - _completed_plan_weeks(plan, today) - 1
    return GoalTime(
        goal_seconds=int(goal_seconds),
        predicted_seconds=int(predicted_seconds),
        weeks_to_go=max(0, weeks_left),
    )


def _goal_view(
    plan: TrainingPlan,
    window: Optional[GoalWindow],
    goal_time: Optional[GoalTime],
    today: date,
) -> GoalView:
    status = plan_status(plan, today)
    return GoalView(
        plan_id=plan.id,
        label=status.distance_display,
        position=status.label,
        weeks_judged=window.weeks if window is not None else 0,
        goal_time=_clock(goal_time.goal_seconds) if goal_time else None,
        predicted_time=_clock(goal_time.predicted_seconds) if goal_time else None,
    )


def _clock(seconds: int) -> str:
    return VDOTCalculator.format_duration(seconds)


# -- Records -----------------------------------------------------------------


def _records(user: User, db: Session) -> list[dict[str, Any]]:
    """Best time per standard distance, flattened for the page."""
    report = PersonalRecordsService.get_personal_records(user.id, db)
    records = []
    for record in report.get("distance_records", []):
        best = record["current_pr"]
        records.append(
            {
                "distance": record["distance_name"],
                "time": best["duration_formatted"],
                "pace": best["pace_formatted"],
                "date": (best["date"] or "")[:10],
            }
        )
    return records
