"""Intervals.icu OAuth and activity sync endpoints."""

import logging
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contexts.auth.auth_service import AuthService
from app.contexts.auth.repositories import SQLAlchemyUserRepository
from app.contexts.plan.adaptation import AdaptationService
from app.dependencies import (
    get_auth_service,
    get_current_user,
    get_db,
    get_intervals_service,
)
from app.infrastructure.config import settings
from app.infrastructure.integrations.intervals_post_sync_service import (
    initial_intervals_sync,
)
from app.infrastructure.integrations.intervals_service import (
    IntervalsAuthorizationError,
    IntervalsService,
)
from app.infrastructure.integrations.strava_post_sync_service import (
    auto_map_and_adjust,
)
from app.models.user import User
from app.rate_limit import intervals_callback_limiter
from app.schemas import IntervalsStatusResponse, IntervalsSyncResponse
from app.utils import TimestampAdapter
from app.web.middleware import _cookie_secure

logger = logging.getLogger(__name__)

intervals_router = APIRouter(prefix="/api/intervals", tags=["intervals"])

_OAUTH_STATE_COOKIE = "intervals_oauth_state"
_OAUTH_STATE_TTL_SECONDS = 300


@intervals_router.get("/connect")
def intervals_connect(
    response: Response,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    intervals_service: IntervalsService = Depends(get_intervals_service),
):
    """Return a one-time Intervals.icu OAuth authorization URL."""
    if not settings.intervals_client_id or not settings.intervals_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intervals.icu OAuth is not configured yet.",
        )

    nonce = secrets.token_urlsafe(16)
    state = auth_service.create_access_token(
        {"sub": current_user.id, "purpose": "intervals_oauth", "nonce": nonce},
        expires_delta=timedelta(minutes=5),
    )
    response.set_cookie(
        key=_OAUTH_STATE_COOKIE,
        value=nonce,
        max_age=_OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
    )
    return {"authorize_url": intervals_service.get_authorization_url(state)}


@intervals_router.get("/callback")
async def intervals_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    intervals_service: IntervalsService = Depends(get_intervals_service),
):
    """Store the OAuth token and start the initial activity import."""
    intervals_callback_limiter.check(request)
    if error or not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Intervals.icu authorization was cancelled or invalid.",
        )

    payload = auth_service.verify_token(state)
    cookie_nonce = request.cookies.get(_OAUTH_STATE_COOKIE)
    if (
        not payload
        or payload.get("purpose") != "intervals_oauth"
        or not cookie_nonce
        or not secrets.compare_digest(cookie_nonce, str(payload.get("nonce", "")))
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter",
        )

    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter",
        )
    user = SQLAlchemyUserRepository(db).get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    try:
        token_data = await intervals_service.exchange_code_for_token(code)
        athlete_id = str(token_data["athlete"]["id"])
        access_token = str(token_data["access_token"])
    except Exception as exchange_error:
        logger.error("Intervals.icu token exchange failed: %s", exchange_error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to exchange code with Intervals.icu",
        ) from exchange_error

    user.intervals_athlete_id = athlete_id
    user.intervals_access_token = access_token
    user.intervals_last_synced_at = None
    try:
        db.commit()
    except IntegrityError as conflict:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Intervals.icu account is already connected to another user.",
        ) from conflict

    background_tasks.add_task(initial_intervals_sync, str(user.id), intervals_service)
    redirect = RedirectResponse(url="/my-plans", status_code=status.HTTP_302_FOUND)
    redirect.delete_cookie(_OAUTH_STATE_COOKIE)
    return redirect


@intervals_router.post("/sync", response_model=IntervalsSyncResponse)
async def intervals_sync(
    force_days: Optional[int] = Query(default=None, ge=1, le=3650),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    intervals_service: IntervalsService = Depends(get_intervals_service),
):
    """Import new runs, overlapping the previous cursor by one day."""
    if not current_user.intervals_athlete_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Intervals.icu is not connected.",
        )

    if force_days is not None:
        after_timestamp = TimestampAdapter.days_ago_utc_epoch(force_days)
    elif current_user.intervals_last_synced_at:
        after_timestamp = current_user.intervals_last_synced_at - 86400
    else:
        after_timestamp = TimestampAdapter.days_ago_utc_epoch(
            settings.intervals_initial_sync_days
        )

    try:
        result = await intervals_service.sync_activities(
            current_user, db, after_timestamp=after_timestamp
        )
    except IntervalsAuthorizationError as authorization_error:
        logger.warning(
            "Intervals.icu authorization failed for user %s", current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Intervals.icu access expired or was revoked. Please reconnect.",
        ) from authorization_error
    except Exception as sync_error:
        logger.error(
            "Intervals.icu sync failed for user %s: %s",
            current_user.id,
            sync_error,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Intervals.icu sync failed. Please try again.",
        ) from sync_error

    adjustment_results = (
        auto_map_and_adjust(current_user, db, AdaptationService()) or None
    )
    return IntervalsSyncResponse(
        **result,
        adjustment_results=adjustment_results,
    )


@intervals_router.get("/status", response_model=IntervalsStatusResponse)
def intervals_status(current_user: User = Depends(get_current_user)):
    connected = bool(current_user.intervals_athlete_id)
    return IntervalsStatusResponse(
        connected=connected,
        athlete_id=current_user.intervals_athlete_id if connected else None,
        last_synced_at=current_user.intervals_last_synced_at if connected else None,
    )


@intervals_router.post("/disconnect")
async def intervals_disconnect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    intervals_service: IntervalsService = Depends(get_intervals_service),
):
    await intervals_service.disconnect(current_user, db)
    return {"message": "Intervals.icu disconnected"}
