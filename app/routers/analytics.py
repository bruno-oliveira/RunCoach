"""Analytics API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user
from app.models import TrainingPlan, User
from app.models.run_log import RunLog
from app.core.training.vdot_calculator import VDOTCalculator
from app.core.runner_profile import build_profile
from app.services.fitness.adherence_service import compute_adherence_heatmap
from app.services.fitness.gap_analysis_service import GapAnalysisService
from app.services.fitness.insights_service import InsightsService
from app.services.fitness.personal_records_service import PersonalRecordsService
from app.services.plans.plan_helpers import get_plan_or_404
from app.services.fitness.race_predictor_service import RacePredictorService
from app.services.fitness.training_load_service import TrainingLoadService
from app.utils import to_date as _to_date

logger = logging.getLogger(__name__)

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


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
    """Get workout type adherence heatmap data for a plan."""
    plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    return compute_adherence_heatmap(plan, current_user.id, db)


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


@analytics_router.get("/insights")
async def get_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get personalized training insights synthesized from all data."""
    return InsightsService.get_insights(current_user.id, db)


@analytics_router.get("/profile")
async def get_runner_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the runner's synthesized profile for plan generation."""
    profile = build_profile(current_user.id, db)
    return profile.to_dict()
