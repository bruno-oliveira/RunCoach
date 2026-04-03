"""Strava OAuth and sync endpoints."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth_service import AuthService
from app.config import settings
from app.dependencies import get_adaptation_service, get_current_user, get_db, get_auth_service, get_strava_service
from app.models import TrainingPlan
from app.models.user import User
from app.schemas import StravaStatusResponse, StravaSyncResponse
from app.services.strava_service import StravaService
from app.utils import TimestampAdapter

logger = logging.getLogger(__name__)

strava_router = APIRouter(prefix="/api/strava", tags=["strava"])


def _auto_map_and_adjust(
    user: User,
    db: Session,
    adaptation_service,
) -> list[dict]:
    """Find active plans and auto-map runs + auto-adjust each one.

    Returns a list of per-plan result dicts suitable for the sync response.
    """
    from app.utils import to_date as _to_date

    today = datetime.now(timezone.utc).date()

    active_plans = (
        db.query(TrainingPlan)
        .filter(
            TrainingPlan.user_id == user.id,
            TrainingPlan.start_date.isnot(None),
        )
        .all()
    )

    results: list[dict] = []
    for plan in active_plans:
        start = _to_date(plan.start_date)
        if start is None:
            continue
        end_date = start + timedelta(weeks=plan.weeks_duration)
        if today > end_date:
            continue  # plan is completed

        try:
            map_result = adaptation_service.map_runs_to_plan(
                plan.id, user.id, db
            )
            adjust_result = adaptation_service.adjust_plan(
                plan.id, user.id, db
            )
            results.append({
                "plan_id": plan.id,
                "runs_mapped": map_result.get("mapped", 0),
                "adjusted": adjust_result.get("adjusted", False),
                "multiplier": adjust_result.get("multiplier"),
                "reason": adjust_result.get("reason", ""),
            })
        except Exception as e:
            logger.warning("Auto-adjust failed for plan %s: %s", plan.id, e)

    return results

# How far back to look on the very first sync (before any cursor exists).
# A full year ensures we cover any active training plan the user might have.
INITIAL_SYNC_DAYS = 365


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
    code: str = Query(...),
    state: str = Query(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
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
        logger.error("Strava token exchange failed: %s", e)
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

    # Initial sync in background to avoid blocking the HTTP response
    async def _initial_sync(user_id: str):
        from app.dependencies import SessionLocal
        from app.services.adaptation_service import AdaptationService
        sync_db = SessionLocal()
        try:
            sync_user = sync_db.query(User).filter(User.id == user_id).first()
            if not sync_user:
                return
            initial_after = TimestampAdapter.days_ago_utc_epoch(INITIAL_SYNC_DAYS)
            result = await strava_service.sync_activities(sync_user, sync_db, after_timestamp=initial_after)
            logger.info(
                f"Initial Strava sync for user {user_id}: "
                f"{result['synced']} synced, {result['total']} total"
            )
            if result.get("synced", 0) > 0:
                adaptation_service = AdaptationService()
                adjustment_results = _auto_map_and_adjust(sync_user, sync_db, adaptation_service)
                if adjustment_results:
                    logger.info(
                        f"Auto-adjusted {len(adjustment_results)} plan(s) for user {user_id}"
                    )
        except Exception as e:
            logger.error("Initial Strava sync failed: %s", e)
        finally:
            sync_db.close()

    background_tasks.add_task(_initial_sync, user.id)

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
    adaptation_service = Depends(get_adaptation_service),
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
        # Start from the last sync cursor minus a 24-hour buffer so runs
        # whose start_date fell before the last sync are still fetched.
        after_timestamp = current_user.strava_last_synced_at - 86400

        # If the user has a training plan whose start date is before the
        # cursor, extend the window to cover the entire plan period.  This
        # backfills any runs that were missed during the initial sync
        # (e.g. the initial sync only pulled 90 days and the plan started
        # earlier).
        earliest_plan_start = (
            db.query(TrainingPlan.start_date)
            .filter(
                TrainingPlan.user_id == current_user.id,
                TrainingPlan.start_date.isnot(None),
            )
            .order_by(TrainingPlan.start_date.asc())
            .first()
        )
        if earliest_plan_start and earliest_plan_start[0]:
            sd = earliest_plan_start[0]
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
        # No cursor yet — treat like an initial sync
        after_timestamp = TimestampAdapter.days_ago_utc_epoch(INITIAL_SYNC_DAYS)

    try:
        result = await strava_service.sync_activities(
            current_user, db, after_timestamp=after_timestamp
        )
    except Exception as e:
        logger.error("Strava sync failed for user %s: %s", current_user.id, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Strava sync failed: {str(e)}",
        )

    # Auto-map and adjust active plans on every sync (not just when new
    # runs arrive) so previously-unmapped runs get linked too.
    adjustment_results = _auto_map_and_adjust(current_user, db, adaptation_service) or None

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

