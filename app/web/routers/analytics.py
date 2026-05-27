"""Analytics API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.application.coach_narrative_service import build_coach_note
from app.application.coach_summary_service import (
    build_adaptation_history,
    build_coach_patterns,
    build_coach_summary,
    build_readiness_trend,
    build_signal_history,
    build_today,
    build_training_age,
)
from app.contexts.plan.plan_helpers import get_plan_or_404
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.contexts.runner.fitness.adherence_service import compute_adherence_heatmap
from app.contexts.runner.fitness.gap_analysis_service import GapAnalysisService
from app.contexts.runner.fitness.insights_service import InsightsService
from app.contexts.runner.fitness.personal_records_service import PersonalRecordsService
from app.contexts.runner.fitness.race_predictor_service import RacePredictorService
from app.contexts.runner.fitness.training_load_service import TrainingLoadService
from app.contexts.runner.profile.profile_builder import build_profile
from app.contexts.runner.repositories import SQLAlchemyRunRepository
from app.core.training.vdot_calculator import VDOTCalculator
from app.dependencies import get_coach_narrator, get_current_user, get_db
from app.domain.coaching import CoachNarrator
from app.models import User
from app.utils import to_date as _to_date

logger = logging.getLogger(__name__)

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@analytics_router.get("/runs")
def get_analytics_runs(
    plan_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get runs for the analytics dashboard, optionally scoped to a plan."""
    try:
        plan_info = None
        scoped_plan_id: Optional[str] = None
        if plan_id:
            plan = SQLAlchemyPlanRepository(db).get_for_user(plan_id, current_user.id)
            if plan:
                scoped_plan_id = plan_id
                start_date = _to_date(plan.start_date)
                plan_info = {
                    "id": plan.id,
                    "start_date": start_date.isoformat() if start_date else None,
                    "weeks_duration": plan.weeks_duration,
                    "target_distance": plan.target_distance,
                    "goal_time": plan.goal_time,
                    "goal_pace": plan.goal_pace,
                }

        runs = SQLAlchemyRunRepository(db).list_for_analytics(
            current_user.id, plan_id=scoped_plan_id
        )

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
                    # The effective type: inferred for Strava runs that arrived
                    # untagged (defaulted to "easy"), the explicit tag otherwise.
                    "workout_type": run.effective_workout_type,
                    "inferred": (
                        run.effective_workout_type is not None
                        and run.effective_workout_type != run.workout_type
                    ),
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
def get_gap_trend(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get per-week gap trend data for a training plan."""
    plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)

    weekly = GapAnalysisService.analyze_gaps_weekly(plan, current_user.id, db)
    if weekly is None:
        return {
            "available": False,
            "reason": "Set a start date and log some runs first.",
        }

    return {"available": True, "weeks": weekly}


@analytics_router.get("/vdot-history")
def get_vdot_history(
    weeks: int = Query(52, ge=4, le=104),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get VDOT history for progression chart."""
    history = RacePredictorService.get_vdot_history(current_user.id, weeks=weeks, db=db)
    predictions = RacePredictorService.get_predictions_for_user(current_user.id, db)

    return {
        "history": history,
        "current_vdot": predictions.get("current_vdot"),
        "vdot_trend": predictions.get("vdot_trend"),
    }


@analytics_router.get("/workout-adherence/{plan_id}")
def get_workout_adherence(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get workout type adherence heatmap data for a plan."""
    plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    return compute_adherence_heatmap(plan, current_user.id, db)


@analytics_router.get("/training-load")
def get_training_load(
    days: int = Query(90, ge=14, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get ACWR (Acute:Chronic Workload Ratio) and training load history."""
    return TrainingLoadService.get_training_load(
        current_user.id, db, lookback_days=days
    )


@analytics_router.get("/personal-records")
def get_personal_records(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get personal records across standard race distances."""
    return PersonalRecordsService.get_personal_records(current_user.id, db)


@analytics_router.get("/pace-zones")
def get_pace_zones(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the user's VDOT-derived pace zones for classifying runs."""
    vdot = RacePredictorService.get_best_recent_vdot(current_user.id, weeks=12, db=db)
    if not vdot:
        return {"available": False}

    zones = VDOTCalculator.get_pace_zones(vdot)
    return {
        "available": True,
        "vdot": vdot,
        "zones": zones,
    }


@analytics_router.get("/insights")
def get_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get personalized training insights synthesized from all data."""
    return InsightsService.get_insights(current_user.id, db)


@analytics_router.get("/profile")
def get_runner_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the runner's synthesized profile for plan generation."""
    profile = build_profile(current_user.id, db)
    return profile.to_dict()


# ---------------------------------------------------------------------------
# Coach hub — plan-scoped, read-only views of the adaptation engine
# ---------------------------------------------------------------------------


@analytics_router.get("/coach-summary/{plan_id}")
def get_coach_summary(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The 6-signal breakdown, multiplier/direction, form, and readiness."""
    plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    return build_coach_summary(plan, current_user.id, db)


@analytics_router.get("/coach-note/{plan_id}")
def get_coach_note(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    narrator: CoachNarrator = Depends(get_coach_narrator),
):
    """The recognition-first Coach's Note (AI voice + accurate fact chips)."""
    plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    return build_coach_note(plan, current_user.id, db, narrator)


@analytics_router.get("/adaptation-history/{plan_id}")
def get_adaptation_history(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The persisted adaptation timeline, normalized newest-first."""
    plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    return build_adaptation_history(plan)


@analytics_router.get("/coach-patterns/{plan_id}")
def get_coach_patterns(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recency-weighted pace patterns + the inline week-pulse mood line."""
    plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    return build_coach_patterns(plan, current_user.id, db)


@analytics_router.get("/today/{plan_id}")
def get_today(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Today's planned workout + the current week's execution strip."""
    plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    return build_today(plan, current_user.id, db)


@analytics_router.get("/signal-history/{plan_id}")
def get_signal_history(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-event adaptation signal snapshots for trend sparklines."""
    plan = get_plan_or_404(plan_id, db, current_user, require_user_match=True)
    return build_signal_history(plan)


@analytics_router.get("/readiness-trend")
def get_readiness_trend(
    days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recent readiness check-ins with rolling averages and a trend label."""
    return build_readiness_trend(current_user.id, db, days=days)


@analytics_router.get("/training-age")
def get_training_age(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Training age and consistency streaks across all logged runs."""
    return build_training_age(current_user.id, db)
