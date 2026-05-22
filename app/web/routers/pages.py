"""Static page endpoints (home, privacy)."""

from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.contexts.runner.dashboard_service import has_runner_profile
from app.dependencies import get_db, get_optional_user
from app.infrastructure.config import settings
from app.models import User
from app.template_helpers import create_templates

router = APIRouter(tags=["pages"])
templates = create_templates()


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    has_profile = bool(current_user) and has_runner_profile(current_user, db)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id or "",
            "has_profile": has_profile,
        },
    )


@router.get("/privacy", response_class=HTMLResponse)
def privacy_policy(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "privacy.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id or "",
        },
    )
