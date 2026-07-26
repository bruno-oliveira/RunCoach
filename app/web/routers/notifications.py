"""Outbound coaching nudges: the scheduled trigger and the way out.

Two surfaces, deliberately unlike each other:

* ``POST /api/notifications/run`` is for a scheduler, not a browser. It carries
  a shared secret in a header and is invisible (404) until ``CRON_SECRET`` is
  configured, so a fresh deploy has no reachable way to mail anyone.
* ``/unsubscribe`` is for a runner holding an email, who has no session and
  shouldn't need one. It is authenticated by an HMAC of their user id, and the
  GET only *offers* to unsubscribe — mail clients and security scanners
  prefetch links, so the change itself has to be a POST.
"""

from __future__ import annotations

import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.application.outbound_nudge_service import (
    OutboundNudgeService,
    verify_unsubscribe_token,
)
from app.dependencies import get_db
from app.infrastructure.config import settings
from app.infrastructure.notifications import get_mailer
from app.models import User
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

notifications_router = APIRouter(tags=["notifications"])
templates = create_templates()


def _require_cron_secret(secret: Optional[str]) -> None:
    """Gate the scheduled trigger on the shared secret.

    404 rather than 401 when unconfigured: an endpoint that mails real people
    should not advertise its own existence to someone probing for it.
    """
    if not settings.cron_secret:
        raise HTTPException(status_code=404, detail="Not found")
    if not secret or not hmac.compare_digest(secret, settings.cron_secret):
        raise HTTPException(status_code=403, detail="Invalid cron secret")


@notifications_router.post("/api/notifications/run")
def run_outbound_nudges(
    dry_run: bool = False,
    limit: Optional[int] = None,
    x_cron_secret: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Evaluate every opted-in runner and send at most one nudge each.

    Idempotent enough to be safe on a schedule: the stored rate limit and
    signature mean a second run minutes later sends nothing.
    """
    _require_cron_secret(x_cron_secret)
    service = OutboundNudgeService(db, get_mailer())
    summary = service.run(dry_run=dry_run, limit=limit)
    logger.info("Outbound nudge run: %s", summary)
    return {"ok": True, "dry_run": dry_run, **summary}


def _unsubscribe_user(db: Session, user_id: str, token: str) -> Optional[User]:
    """The user this token authorises, or ``None``."""
    if not user_id or not verify_unsubscribe_token(user_id, token):
        return None
    return db.query(User).filter(User.id == user_id).first()


@notifications_router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(
    request: Request,
    u: str = "",
    t: str = "",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Offer to stop coaching emails. Changes nothing — see the POST."""
    user = _unsubscribe_user(db, u, t)
    return templates.TemplateResponse(
        request,
        "unsubscribe.html",
        {
            "request": request,
            "user": None,
            "valid": user is not None,
            "done": False,
            "user_id": u,
            "token": t,
            "email": user.email if user else "",
        },
    )


@notifications_router.post("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_confirm(
    request: Request,
    u: str = Form(default=""),
    t: str = Form(default=""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Turn coaching emails off. Idempotent; never touches anything else."""
    user = _unsubscribe_user(db, u, t)
    if user is not None:
        user.nudge_email_enabled = False
        db.commit()
        logger.info("User %s unsubscribed from coaching emails", user.id)

    return templates.TemplateResponse(
        request,
        "unsubscribe.html",
        {
            "request": request,
            "user": None,
            "valid": user is not None,
            "done": user is not None,
            "user_id": u,
            "token": t,
            "email": user.email if user else "",
        },
    )
