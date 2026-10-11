"""Performance training page endpoints (HTML responses)."""

import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies import get_optional_user
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["performance-pages"])


@router.get("/performance-training", response_class=HTMLResponse)
def performance_training_page(
    request: Request,
    current_user: User = Depends(get_optional_user),
) -> Response:
    """Redirect to unified home with time-goal mode."""
    return RedirectResponse(url="/?mode=time", status_code=302)
