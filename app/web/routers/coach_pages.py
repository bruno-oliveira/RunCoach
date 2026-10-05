"""The Coach page: how the runner's training is going, and what to change."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.application.coach_read_service import build_coach_page
from app.core.time_utils import local_today
from app.dependencies import get_db, get_optional_user
from app.infrastructure.config import settings
from app.template_helpers import create_templates

router = APIRouter(tags=["coach-page"])
templates = create_templates()


@router.get("/coach", response_class=HTMLResponse)
def coach_page(
    request: Request,
    current_user=Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """The read of a runner's training. Takes no input: nothing to configure."""
    if current_user is None:
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse(
        request,
        "coach.html",
        {
            "request": request,
            "user": current_user,
            "current_page": "coach",
            "google_client_id": settings.google_client_id,
            "page": build_coach_page(current_user, db, local_today()),
        },
    )


@router.get("/analytics", include_in_schema=False)
def legacy_analytics_redirect() -> RedirectResponse:
    """The page's old address — installed apps and sent pushes still point here."""
    return RedirectResponse(url="/coach", status_code=308)
