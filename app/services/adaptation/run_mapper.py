"""Retroactive run-to-plan mapping via greedy matching."""

import logging
from collections import defaultdict
from datetime import timedelta
from typing import Any, Dict

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import DailyWorkout, RunLog, TrainingPlan, WeeklyPlan
from app.utils import to_date as _to_date

from ._helpers import today_date

logger = logging.getLogger(__name__)


def map_runs_to_plan(
    plan_id: str,
    user_id: str,
    db: Session,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Match unlinked RunLog entries to plan DailyWorkouts by week.

    Assigns every run between the plan start_date and today to its
    corresponding training week, then greedily matches runs to the best
    available workout within that week.

    Args:
        plan_id: Training plan ID.
        user_id: User ID.
        db: Database session.
        dry_run: If True, return proposed mappings without persisting.

    Returns:
        Dict with ``mapped`` count and ``proposals`` list.
    """
    training_plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.user_id == user_id,
    ).first()

    if not training_plan:
        return {"mapped": 0, "proposals": [], "error": "Plan not found"}

    if not training_plan.start_date:
        return {"mapped": 0, "proposals": [], "error": "Plan has no start date. Set a start date first."}

    start_date = _to_date(training_plan.start_date)
    today = today_date()
    tomorrow = today + timedelta(days=1)
    num_weeks = training_plan.weeks_duration
    plan_end_date = start_date + timedelta(weeks=num_weeks)
    upper_bound = min(tomorrow, plan_end_date + timedelta(days=1))
    logger.info(
        "map_runs_to_plan: plan=%s, start_date=%s, today=%s, weeks=%d",
        plan_id, start_date, today, num_weeks,
    )

    # 1. Build available workouts by week
    all_workouts = (
        db.query(DailyWorkout, WeeklyPlan.week_number)
        .join(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan_id)
        .all()
    )

    already_linked_ids = set(
        row[0] for row in
        db.query(RunLog.daily_workout_id)
        .filter(
            RunLog.training_plan_id == plan_id,
            RunLog.daily_workout_id.isnot(None),
        )
        .all()
    )

    workouts_by_week: Dict[int, list] = defaultdict(list)
    for workout, week_number in all_workouts:
        if workout.id in already_linked_ids:
            continue
        workout_date = start_date + timedelta(
            weeks=(week_number - 1),
            days=(workout.day_of_week - 1),
        )
        if workout_date > today:
            continue
        workouts_by_week[week_number].append((workout, workout_date))

    logger.info(
        "map_runs_to_plan: %d total workouts, %d already linked, "
        "%d available across %d weeks",
        len(all_workouts), len(already_linked_ids),
        sum(len(v) for v in workouts_by_week.values()),
        len(workouts_by_week),
    )

    # 2. Get all mappable runs (start_date to today)
    unlinked_runs = (
        db.query(RunLog)
        .filter(
            RunLog.user_id == user_id,
            RunLog.date >= start_date,
            RunLog.date < upper_bound,
            or_(
                RunLog.training_plan_id.is_(None),
                RunLog.training_plan_id != plan_id,
                and_(
                    RunLog.training_plan_id == plan_id,
                    RunLog.daily_workout_id.is_(None),
                ),
            ),
        )
        .all()
    )

    logger.info(
        "map_runs_to_plan: %d unlinked runs in [%s, %s]",
        len(unlinked_runs), start_date, today,
    )

    if not unlinked_runs:
        return {"mapped": 0, "proposals": [], "message": "No unlinked runs to map."}

    # 3. Assign each run to its training week
    runs_by_week: Dict[int, list] = defaultdict(list)
    for run in unlinked_runs:
        run_date = _to_date(run.date)
        delta_days = (run_date - start_date).days
        week_number = (delta_days // 7) + 1
        week_number = max(1, min(week_number, num_weeks))
        runs_by_week[week_number].append(run)

    # 4. Per-week greedy matching
    proposals = _greedy_match(runs_by_week, workouts_by_week)

    if not proposals:
        return {"mapped": 0, "proposals": [], "message": "No matching runs found."}

    if dry_run:
        return {"mapped": 0, "proposals": proposals, "dry_run": True}

    # 5. Persist mappings
    _persist_mappings(proposals, plan_id, db)

    return {"mapped": len(proposals), "proposals": proposals}


def _greedy_match(
    runs_by_week: Dict[int, list],
    workouts_by_week: Dict[int, list],
) -> list:
    """Score and greedily match runs to workouts per week."""

    def _match_score(date_penalty: float, dist_diff: float) -> float:
        return date_penalty * 3.0 + dist_diff

    proposals = []
    used_run_ids: set = set()

    all_week_numbers = sorted(
        set(list(runs_by_week.keys()) + list(workouts_by_week.keys()))
    )

    for wn in all_week_numbers:
        week_runs = runs_by_week.get(wn, [])
        week_workouts = workouts_by_week.get(wn, [])

        edges: list = []
        for run in week_runs:
            run_date = _to_date(run.date)
            for workout, workout_date in week_workouts:
                date_penalty = abs((run_date - workout_date).days)
                dist_diff = abs(
                    (run.distance_km or 0) - (workout.distance_km or 0)
                )
                rest_penalty = 0.0
                if workout.workout_type in ("rest", "recovery") and (run.distance_km or 0) > 1:
                    rest_penalty = 10.0
                score = _match_score(date_penalty, dist_diff) + rest_penalty
                edges.append((score, run, workout, workout_date))

        edges.sort(key=lambda e: e[0])
        matched_run_ids: set = set()
        matched_workout_ids: set = set()

        for score, run, workout, workout_date in edges:
            if run.id in matched_run_ids or workout.id in matched_workout_ids:
                continue
            matched_run_ids.add(run.id)
            matched_workout_ids.add(workout.id)
            used_run_ids.add(run.id)

            run_date = _to_date(run.date)
            proposals.append({
                "run_id": run.id,
                "workout_id": workout.id,
                "week": wn,
                "day": workout.day_of_week,
                "workout_type": workout.workout_type,
                "planned_distance": workout.distance_km,
                "actual_distance": run.distance_km,
                "run_date": str(run_date),
                "workout_date": str(workout_date),
                "match_type": "workout",
            })

        for run in week_runs:
            if run.id in matched_run_ids or run.id in used_run_ids:
                continue
            used_run_ids.add(run.id)
            run_date = _to_date(run.date)
            proposals.append({
                "run_id": run.id,
                "workout_id": None,
                "week": wn,
                "day": None,
                "workout_type": None,
                "planned_distance": None,
                "actual_distance": run.distance_km,
                "run_date": str(run_date),
                "workout_date": None,
                "match_type": "weekly_volume",
            })

    return proposals


def _persist_mappings(proposals: list, plan_id: str, db: Session) -> None:
    """Write run-to-workout mappings to the database."""
    proposal_run_ids = [p["run_id"] for p in proposals]
    runs_by_id = {
        r.id: r
        for r in db.query(RunLog).filter(RunLog.id.in_(proposal_run_ids)).all()
    }
    for p in proposals:
        run = runs_by_id.get(p["run_id"])
        if run:
            run.daily_workout_id = (
                p["workout_id"] if p["match_type"] == "workout" else None
            )
            run.training_plan_id = plan_id

    db.commit()
