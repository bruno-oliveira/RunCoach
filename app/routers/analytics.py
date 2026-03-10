"""Router for analytics functionality."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db, get_current_user, get_optional_user
from app.models import User
from app.models.run_log import RunLog
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])
analytics_page_router = APIRouter(tags=["analytics-page"])
templates = create_templates()


@analytics_page_router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    current_user = Depends(get_optional_user),
) -> HTMLResponse:
    """Analytics dashboard page."""
    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "user": current_user,
            "current_page": "analytics",
            "google_client_id": settings.google_client_id,
        },
    )


@analytics_router.get("/runs")
async def get_analytics_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all runs for the current user for the analytics dashboard."""
    try:
        runs = (
            db.query(RunLog)
            .filter(RunLog.user_id == current_user.id)
            .order_by(RunLog.date.asc())
            .all()
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
                    "workout_type": run.workout_type,
                    "perceived_effort": run.perceived_effort,
                    "quality_label": run.quality_label,
                    "effort_quality_score": run.effort_quality_score,
                }
                for run in runs
            ],
            "total": len(runs),
        }
    except Exception as e:
        logger.error(f"Error fetching analytics runs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve run data",
        )
