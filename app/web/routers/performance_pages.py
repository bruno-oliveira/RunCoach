"""Performance training page endpoints (HTML responses)."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies import get_optional_user
from app.models import User
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["performance-pages"])
templates = create_templates()


@router.get("/performance-training", response_class=HTMLResponse)
def performance_training_page(
    request: Request,
    current_user: User = Depends(get_optional_user),
) -> HTMLResponse:
    """Redirect to unified home with time-goal mode."""
    return RedirectResponse(url="/?mode=time", status_code=302)
