"""Post-sync orchestration for Intervals.icu activity imports."""

import logging

from app.contexts.auth.repositories import SQLAlchemyUserRepository
from app.contexts.plan.adaptation import AdaptationService
from app.infrastructure.config import settings
from app.infrastructure.integrations.strava_post_sync_service import (
    auto_map_and_adjust,
)
from app.utils import TimestampAdapter

logger = logging.getLogger(__name__)


async def initial_intervals_sync(user_id: str, intervals_service) -> None:
    """Run the initial import in a background task with its own DB session."""
    from app.dependencies import SessionLocal

    sync_db = SessionLocal()
    try:
        user = SQLAlchemyUserRepository(sync_db).get_by_id(user_id)
        if not user:
            return
        result = await intervals_service.sync_activities(
            user,
            sync_db,
            after_timestamp=TimestampAdapter.days_ago_utc_epoch(
                settings.intervals_initial_sync_days
            ),
        )
        logger.info(
            "Initial Intervals.icu sync for user %s: %s synced, %s total",
            user_id,
            result["synced"],
            result["total"],
        )
        if result.get("synced", 0) > 0:
            auto_map_and_adjust(user, sync_db, AdaptationService())
    except Exception:
        logger.exception("Initial Intervals.icu sync failed for user %s", user_id)
    finally:
        sync_db.close()
