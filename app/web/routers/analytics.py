"""Analytics API endpoints.

One remains. The dashboard these once fed was replaced by the server-rendered
Coach page (``coach_pages.py``), which reads its data in-process, so the
endpoints that existed only to feed that dashboard's JavaScript went with it.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.contexts.runner.fitness.home_stats_service import HomeStatsService
from app.dependencies import get_current_user, get_db
from app.models import User

logger = logging.getLogger(__name__)

analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@analytics_router.get("/home-stats")
def get_home_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pace + HR-zone evolution for the signed-in home page's discreet panel."""
    try:
        return HomeStatsService.build(current_user, db)
    except Exception as e:
        logger.error(f"Error building home stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build home stats",
        )
