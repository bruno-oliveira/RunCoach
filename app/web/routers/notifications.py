"""Outbound coaching nudges: the scheduled trigger and the way out.

Two surfaces, deliberately unlike each other:

* ``POST /api/notifications/run`` is for a scheduler, not a browser. It carries
  a shared secret in a header and is invisible (404) until ``CRON_SECRET`` is
  configured, so a fresh deploy has no reachable way to mail anyone. It runs
  *after* ``/api/scheduled/sync`` — see that module for why the order matters.
* ``/unsubscribe`` is for a runner holding an email, who has no session and
  shouldn't need one. It is authenticated by an HMAC of their user id, and the
  GET only *offers* to unsubscribe — mail clients and security scanners
  prefetch links, so the change itself has to be a POST.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.application.outbound_nudge_service import (
    OutboundNudgeService,
    verify_unsubscribe_token,
)
from app.dependencies import get_db, require_cron_secret
from app.infrastructure.notifications import get_mailer
from app.models import User
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

notifications_router = APIRouter(tags=["notifications"])
templates = create_templates()


@notifications_router.post(
    "/api/notifications/run", dependencies=[Depends(require_cron_secret)]
)
def run_outbound_nudges(
    dry_run: bool = False,
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
) -> dict:
    """Evaluate every opted-in runner and send at most one nudge each.

    Idempotent enough to be safe on a schedule: the stored rate limit and
    signature mean a second run minutes later sends nothing.

    **Run `/api/scheduled/sync` first.** The `gone_quiet` guard reads how long
    it has been since a logged run, so nudging before importing can tell a
    runner they have gone quiet when they came back yesterday.
    """
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
