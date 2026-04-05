"""Router for analytics functionality."""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db, get_current_user, get_optional_user
from app.models import DailyWorkout, TrainingPlan, User, WeeklyPlan
from app.models.run_log import RunLog
from app.services.plan_helpers import get_plan_or_404
from app.schemas import DISTANCE_NAMES
from app.core.training.vdot_calculator import VDOTCalculator
from app.services.gap_analysis_service import GapAnalysisService
from app.services.personal_records_service import PersonalRecordsService
from app.services.race_predictor_service import RacePredictorService
from app.services.training_load_service import TrainingLoadService
from app.template_helpers import create_templates
from app.utils import to_date as _to_date

logger = logging.getLogger(__name__)

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])
analytics_page_router = APIRouter(tags=["analytics-page"])
templates = create_templates()


@analytics_page_router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    current_user=Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Analytics dashboard page."""
    plans = []
    if current_user:
        plans = (
            db.query(TrainingPlan)
            .filter(TrainingPlan.user_id == current_user.id)
            .order_by(TrainingPlan.created_at.desc())
            .all()
        )

    plan_summaries = []
    for p in plans:
        td = p.target_distance_km
        label = DISTANCE_NAMES.get(td, f"{td}km")
        plan_summaries.append({
            "id": p.id,
            "label": f"{label} — {p.weeks_duration}wk",
            "target_distance_km": td,
        })

    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "user": current_user,
            "current_page": "analytics",
            "google_client_id": settings.google_client_id,
            "plans": plan_summaries,
        },
    )


@analytics_router.get("/runs")
async def get_analytics_runs(
    plan_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get runs for the analytics dashboard, optionally scoped to a plan."""
    try:
        query = db.query(RunLog).filter(RunLog.user_id == current_user.id)

        plan_info = None
        if plan_id:
            plan = (
                db.query(TrainingPlan)
                .filter(
                    TrainingPlan.id == plan_id,
                    TrainingPlan.user_id == current_user.id,
                )
                .first()
            )
            if plan:
                query = query.filter(RunLog.training_plan_id == plan_id)
                start_date = _to_date(plan.start_date)
                plan_info = {
                    "id": plan.id,
                    "start_date": start_date.isoformat() if start_date else None,
                    "weeks_duration": plan.weeks_duration,
                    "target_distance": plan.target_distance,
                    "goal_time": plan.goal_time,
                    "goal_pace": plan.goal_pace,
                }

        runs = query.order_by(RunLog.date.asc()).limit(5000).all()

        return {
            "runs": [
                {
                    "date": run.date.isoformat() if run.date else None,
                    "distance_km": run.distance_km,
                    "duration_minutes": run.duration_minutes,
                    "avg_pace_min_km": run.avg_pace_min_km,
                    "avg_heart_rate": run.avg_heart_rate,
                    "max_heart_rate": run.max_heart_rate,
                    "avg_cadence": run.avg_cadence,
                    "elevation_gain_m": run.elevation_gain_m,
                    "workout_type": run.workout_type,
                    "perceived_effort": run.perceived_effort,
                    "quality_label": run.quality_label,
                    "effort_quality_score": run.effort_quality_score,
                    "vdot": run.vdot,
                    "training_plan_id": run.training_plan_id,
                }
                for run in runs
            ],
            "total": len(runs),
            "plan": plan_info,
        }
    except Exception as e:
        logger.error(f"Error fetching analytics runs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve run data",
        )


@analytics_router.get("/gap-trend/{plan_id}")
async def get_gap_trend(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get per-week gap trend data for a training plan."""
    plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    weekly = GapAnalysisService.analyze_gaps_weekly(plan, current_user.id, db)
    if weekly is None:
        return {"available": False, "reason": "Set a start date and log some runs first."}

    return {"available": True, "weeks": weekly}


@analytics_router.get("/vdot-history")
async def get_vdot_history(
    weeks: int = Query(52, ge=4, le=104),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get VDOT history for progression chart."""
    history = RacePredictorService.get_vdot_history(
        current_user.id, weeks=weeks, db=db
    )
    predictions = RacePredictorService.get_predictions_for_user(current_user.id, db)

    return {
        "history": history,
        "current_vdot": predictions.get("current_vdot"),
        "vdot_trend": predictions.get("vdot_trend"),
    }


@analytics_router.get("/workout-adherence/{plan_id}")
async def get_workout_adherence(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get workout type adherence heatmap data for a plan.

    Returns a grid of (week, workout_type) with completion status.
    """
    plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    start_date = _to_date(plan.start_date)
    if not start_date:
        return {"available": False, "reason": "Plan has no start date."}

    today = date.today()
    total_weeks = plan.weeks_duration or 0
    current_week = min(((today - start_date).days // 7) + 1, total_weeks)

    plan_data = json.loads(plan.plan_data) if plan.plan_data else []

    # Get all run logs mapped to this plan
    runs = (
        db.query(RunLog)
        .filter(
            RunLog.user_id == current_user.id,
            RunLog.training_plan_id == plan_id,
        )
        .all()
    )
    linked_workout_ids = {r.daily_workout_id for r in runs if r.daily_workout_id}

    # Get all daily workouts, pre-indexed by week number
    workouts_raw = (
        db.query(DailyWorkout, WeeklyPlan.week_number)
        .join(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan_id)
        .all()
    )
    workouts_by_week: dict[int, list] = {}
    for workout, wk in workouts_raw:
        workouts_by_week.setdefault(wk, []).append(workout)

    # Collect all workout types
    workout_types = set()
    for week_data in plan_data:
        for wo in week_data.get("daily_workouts", []):
            wo_type = wo.get("type", "unknown")
            if wo_type not in ("rest", "recovery"):
                workout_types.add(wo_type)

    workout_types = sorted(workout_types)

    # Build heatmap grid
    grid = []
    for week_data in plan_data:
        wk_num = week_data.get("week", 0)
        row = {"week": wk_num, "cells": {}}
        for wo_type in workout_types:
            if wk_num > current_week:
                row["cells"][wo_type] = "future"
            else:
                row["cells"][wo_type] = "skipped"

        for workout in workouts_by_week.get(wk_num, []):
            wo_type = workout.workout_type
            if wo_type in ("rest", "recovery") or wo_type not in workout_types:
                continue
            if workout.id in linked_workout_ids:
                row["cells"][wo_type] = "completed"
            elif wk_num <= current_week:
                week_start = start_date + timedelta(weeks=wk_num - 1)
                week_end = week_start + timedelta(days=7)
                week_runs = [
                    r for r in runs
                    if r.date and week_start <= _to_date(r.date) < week_end
                ]
                if week_runs:
                    row["cells"][wo_type] = "rescheduled"

        grid.append(row)

    return {
        "available": True,
        "workout_types": workout_types,
        "grid": grid,
        "current_week": current_week,
        "total_weeks": total_weeks,
    }


@analytics_router.get("/training-load")
async def get_training_load(
    days: int = Query(90, ge=14, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get ACWR (Acute:Chronic Workload Ratio) and training load history."""
    return TrainingLoadService.get_training_load(current_user.id, db, lookback_days=days)


@analytics_router.get("/personal-records")
async def get_personal_records(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get personal records across standard race distances."""
    return PersonalRecordsService.get_personal_records(current_user.id, db)


@analytics_router.get("/pace-zones")
async def get_pace_zones(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the user's VDOT-derived pace zones for classifying runs."""
    vdot = RacePredictorService.get_best_recent_vdot(
        current_user.id, weeks=12, db=db
    )
    if not vdot:
        return {"available": False}

    zones = VDOTCalculator.get_pace_zones(vdot)
    return {
        "available": True,
        "vdot": vdot,
        "zones": zones,
    }
