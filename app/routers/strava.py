"""Strava OAuth and sync endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth_service import AuthService
from app.config import settings
from app.dependencies import get_current_user, get_db, get_auth_service, get_strava_service
from app.models.user import User
from app.schemas import StravaStatusResponse, StravaSyncResponse
from app.services.strava_service import StravaService
from app.utils import TimestampAdapter

logger = logging.getLogger(__name__)

strava_router = APIRouter(prefix="/api/strava", tags=["strava"])

# How far back to look on the very first sync (before any cursor exists)
INITIAL_SYNC_DAYS = 90


@strava_router.get("/connect")
async def strava_connect(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    strava_service: StravaService = Depends(get_strava_service),
):
    """Return Strava OAuth authorization URL."""
    state = auth_service.create_access_token(
        {"sub": current_user.id, "purpose": "strava_oauth"}
    )
    authorize_url = strava_service.get_authorization_url(state)
    return {"authorize_url": authorize_url}


@strava_router.get("/callback")
async def strava_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    strava_service: StravaService = Depends(get_strava_service),
):
    """Handle Strava OAuth callback: exchange code, store tokens, trigger initial sync."""
    payload = auth_service.verify_token(state)
    if not payload or payload.get("purpose") != "strava_oauth":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter",
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
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

    # Initial sync: pull last INITIAL_SYNC_DAYS days
    initial_after = TimestampAdapter.days_ago_utc_epoch(INITIAL_SYNC_DAYS)
    try:
        result = await strava_service.sync_activities(user, db, after_timestamp=initial_after)
        logger.info(
            f"Initial Strava sync for user {user.id}: "
            f"{result['synced']} synced, {result['total']} total"
        )
    except Exception as e:
        logger.error(f"Initial Strava sync failed: {e}")

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
    """Sync new Strava activities since the last sync.

    By default, only fetches activities created after the last successful sync
    (incremental). Pass force_days to re-pull a specific window, or full_sync=true
    to fetch the entire activity history.
    """
    if not current_user.strava_athlete_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strava account not connected. Connect via /api/strava/connect first.",
        )

    if full_sync:
        after_timestamp = None  # no time filter — fetch entire history
    elif force_days is not None:
        after_timestamp = TimestampAdapter.days_ago_utc_epoch(force_days)
    elif current_user.strava_last_synced_at:
        # Subtract a 24-hour buffer so runs whose start_date fell before the
        # last sync (e.g. a long run that was still in-progress when we last
        # synced) are still fetched. Dedup by strava_activity_id prevents
        # double-counting previously imported activities.
        after_timestamp = current_user.strava_last_synced_at - 86400
    else:
        # No cursor yet — treat like an initial sync
        after_timestamp = TimestampAdapter.days_ago_utc_epoch(INITIAL_SYNC_DAYS)

    try:
        result = await strava_service.sync_activities(
            current_user, db, after_timestamp=after_timestamp
        )
    except Exception as e:
        logger.error(f"Strava sync failed for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Strava sync failed: {str(e)}",
        )

    return StravaSyncResponse(**result)


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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    strava_service: StravaService = Depends(get_strava_service),
):
    """Disconnect Strava account. Keeps previously synced RunLogs."""
    strava_service.disconnect(current_user, db)
    return {"detail": "Strava account disconnected"}
