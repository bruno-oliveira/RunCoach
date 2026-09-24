"""Push-notification endpoints: subscribe this device, choose categories, test.

A browser push subscription is per *device*, while preferences are per
*runner* — so the device endpoints carry the subscription's ``endpoint`` and
the preference endpoint does not. Everything answers ``configured: false``
rather than erroring when the server has no VAPID key, so the settings panel
can simply hide the switch on a deploy without push.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.application.push_notification_service import (
    KIND_TEST,
    get_push_notifier,
)
from app.core.coaching import notification_prefs as prefs
from app.dependencies import get_current_user, get_db
from app.domain.notifications import PushMessage
from app.infrastructure.notifications.webpush import (
    b64url_decode,
    get_push_sender,
    is_allowed_endpoint,
)
from app.models import PushSubscription, User
from app.rate_limit import push_subscribe_limiter, push_test_limiter

logger = logging.getLogger(__name__)

push_router = APIRouter(prefix="/api/push", tags=["push"])


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(..., min_length=40, max_length=200)
    auth: str = Field(..., min_length=10, max_length=100)


class SubscribeRequest(BaseModel):
    endpoint: str = Field(..., min_length=10, max_length=2048)
    keys: SubscriptionKeys


class UnsubscribeRequest(BaseModel):
    endpoint: str = Field(..., min_length=10, max_length=2048)


class PrefsUpdate(BaseModel):
    after_run: Optional[bool] = None
    plan_changes: Optional[bool] = None
    morning_brief: Optional[bool] = None
    week_review: Optional[bool] = None
    coaching_nudges: Optional[bool] = None


def _config(user: User, db: Session) -> Dict[str, Any]:
    sender = get_push_sender()
    devices = (
        db.query(PushSubscription.id)
        .filter(PushSubscription.user_id == user.id)
        .count()
    )
    return {
        "configured": sender.configured,
        "public_key": sender.public_key,
        "devices": devices,
        "prefs": prefs.resolve(user.notification_prefs),
        "categories": [
            {"key": key, "label": meta["label"], "help": meta["help"]}
            for key, meta in prefs.CATEGORIES.items()
        ],
    }


@push_router.get("/config")
def push_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Whether push works here, the VAPID key to subscribe with, and prefs."""
    return _config(current_user, db)


@push_router.post("/subscribe")
def push_subscribe(
    payload: SubscribeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Register (or re-home) this browser's subscription for the current runner."""
    push_subscribe_limiter.check(request)
    if not get_push_sender().configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications are not configured on this server.",
        )
    if not is_allowed_endpoint(payload.endpoint):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported push service.",
        )
    try:
        if len(b64url_decode(payload.keys.p256dh)) != 65:
            raise ValueError
        if len(b64url_decode(payload.keys.auth)) != 16:
            raise ValueError
    except (ValueError, TypeError) as bad_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid subscription keys."
        ) from bad_keys

    existing = (
        db.query(PushSubscription)
        .filter(PushSubscription.endpoint == payload.endpoint)
        .first()
    )
    if existing is None:
        existing = PushSubscription(endpoint=payload.endpoint)
        db.add(existing)
    # A shared family laptop that signs in as someone else re-homes the device
    # rather than keeping the previous runner's notifications flowing to it.
    existing.user_id = current_user.id
    existing.p256dh = payload.keys.p256dh
    existing.auth = payload.keys.auth
    existing.failure_count = 0
    existing.user_agent = (request.headers.get("user-agent") or "")[:255] or None
    db.commit()
    return {"ok": True, **_config(current_user, db)}


@push_router.post("/unsubscribe")
def push_unsubscribe(
    payload: UnsubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Forget this browser (only if it's the current runner's)."""
    db.query(PushSubscription).filter(
        PushSubscription.endpoint == payload.endpoint,
        PushSubscription.user_id == current_user.id,
    ).delete(synchronize_session=False)
    db.commit()
    return {"ok": True, **_config(current_user, db)}


@push_router.patch("/prefs")
def push_prefs(
    payload: PrefsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Switch notification categories on or off for this runner."""
    current_user.notification_prefs = prefs.merge(
        current_user.notification_prefs, payload.model_dump(exclude_none=True)
    )
    db.commit()
    return _config(current_user, db)


@push_router.post("/test")
def push_test(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Send a test notification to every device this runner has subscribed."""
    push_test_limiter.check(request)
    delivered = get_push_notifier(db).notify(
        current_user,
        PushMessage(
            title="RunCoach notifications are on",
            body="This is where your coach will reach you — after runs, "
            "when the plan moves, and on race-week mornings.",
            url="/",
            tag="test",
        ),
        category=None,
        kind=KIND_TEST,
        key=uuid.uuid4().hex,
    )
    db.commit()
    return {"ok": True, "delivered": delivered}
