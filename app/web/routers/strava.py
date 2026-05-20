"""Strava OAuth and sync endpoints."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.contexts.auth.auth_service import AuthService
from app.contexts.auth.repositories import SQLAlchemyUserRepository
from app.infrastructure.config import settings
from app.contexts.plan.repositories import SQLAlchemyPlanRepository
from app.dependencies import get_current_user, get_db, get_auth_service, get_strava_service
from app.models.user import User
from app.schemas import StravaStatusResponse, StravaSyncResponse
from app.rate_limit import strava_callback_limiter
from app.infrastructure.integrations.strava_service import StravaService
from app.contexts.plan.adaptation import AdaptationService
from app.infrastructure.integrations.strava_post_sync_service import auto_map_and_adjust, initial_sync
from app.utils import TimestampAdapter

logger = logging.getLogger(__name__)

strava_router = APIRouter(prefix="/api/strava", tags=["strava"])


@strava_router.get("/connect")
async def strava_connect(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    strava_service: StravaService = Depends(get_strava_service),
):
    """Return Strava OAuth authorization URL."""
    state = auth_service.create_access_token(
        {"sub": current_user.id, "purpose": "strava_oauth"},
        expires_delta=timedelta(minutes=5),
    )
    authorize_url = strava_service.get_authorization_url(state)
    return {"authorize_url": authorize_url}


@strava_router.get("/callback")
async def strava_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    strava_service: StravaService = Depends(get_strava_service),
):
    """Handle Strava OAuth callback: exchange code, store tokens, trigger initial sync."""
    strava_callback_limiter.check(request)
    payload = auth_service.verify_token(state)
    if not payload or payload.get("purpose") != "strava_oauth":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter",
        )

    user_id = payload.get("sub")
    user = SQLAlchemyUserRepository(db).get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    try:
        token_data = await strava_service.exchange_code_for_tokens(code)
    except Exception as e:
        logger.error(f"Strava token exchange failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to exchange code with Strava",
        )

    athlete = token_data.get("athlete", {})
    user.strava_athlete_id = str(athlete.get("id", ""))
    user.strava_access_token = token_data["access_token"]
    user.strava_refresh_token = token_data["refresh_token"]
    user.strava_token_expires_at = token_data["expires_at"]
    db.commit()

    background_tasks.add_task(initial_sync, user.id, strava_service)

    return RedirectResponse(url="/my-plans", status_code=status.HTTP_302_FOUND)


@strava_router.post("/sync", response_model=StravaSyncResponse)
async def strava_sync(
    force_days: Optional[int] = Query(
        default=None,
        ge=1,
        le=3650,
        description="Force a full re-sync for the last N days, ignoring the cursor.",
    ),
    full_sync: bool = Query(
        default=False,
        description="Fetch all historical activities with no time filter, ignoring the cursor.",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    strava_service: StravaService = Depends(get_strava_service),
):
    """Sync new Strava activities since the last sync."""
    if not current_user.strava_athlete_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strava account not connected. Connect via /api/strava/connect first.",
        )

    if full_sync:
        after_timestamp = None
    elif force_days is not None:
        after_timestamp = TimestampAdapter.days_ago_utc_epoch(force_days)
    elif current_user.strava_last_synced_at:
        after_timestamp = current_user.strava_last_synced_at - 86400

        earliest_plan_start = SQLAlchemyPlanRepository(db).earliest_start_date(
            current_user.id
        )
        if earliest_plan_start:
            sd = earliest_plan_start
            plan_epoch = int(
                datetime.combine(
                    sd if not hasattr(sd, "date") else sd.date(),
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                ).timestamp()
            )
            if plan_epoch < after_timestamp:
                logger.info(
                    "Extending sync window to plan start %s (was %s)",
                    sd, after_timestamp,
                )
                after_timestamp = plan_epoch
    else:
        after_timestamp = TimestampAdapter.days_ago_utc_epoch(settings.strava_initial_sync_days)

    try:
        result = await strava_service.sync_activities(
            current_user, db, after_timestamp=after_timestamp
        )
    except Exception as e:
        logger.error(f"Strava sync failed for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Strava sync failed. Please try again.",
        )

    adaptation_service = AdaptationService()
    adjustment_results = auto_map_and_adjust(current_user, db, adaptation_service) or None

    return StravaSyncResponse(**result, adjustment_results=adjustment_results)


@strava_router.get("/status", response_model=StravaStatusResponse)
async def strava_status(
    current_user: User = Depends(get_current_user),
):
    """Return Strava connection status for the current user."""
    connected = bool(current_user.strava_athlete_id)
    return StravaStatusResponse(
        connected=connected,
        athlete_id=current_user.strava_athlete_id if connected else None,
        last_synced_at=current_user.strava_last_synced_at if connected else None,
    )


@strava_router.post("/disconnect")
async def strava_disconnect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    strava_service: StravaService = Depends(get_strava_service),
):
    """Disconnect Strava: revoke token with Strava API and clear stored credentials."""
    await strava_service.disconnect(current_user, db)
    logger.info("Strava disconnected for user %s", current_user.id)
    return {"message": "Strava disconnected"}
