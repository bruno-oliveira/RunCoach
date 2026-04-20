"""Performance training endpoints.

Legacy endpoints redirect to the unified plan system.
The /api/performance/* endpoints remain for direct API callers.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_user, get_db, get_optional_user, get_performance_service
from app.models import User
from app.services.performance_service import PerformanceService
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["performance"])
templates = create_templates()


@router.get("/api/performance/calculate-fitness")
async def calculate_fitness(
    distance: float,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    performance_service: PerformanceService = Depends(get_performance_service),
) -> Dict[str, Any]:
    """Calculate current fitness metrics from run logs."""
    try:
        fitness = performance_service.calculate_fitness_from_runs(
            user_id=current_user.id,
            target_distance=distance
        )
        return fitness
    except Exception as e:
        logger.error(f"Error calculating fitness: {e}")
        raise HTTPException(status_code=500, detail=str(e))
