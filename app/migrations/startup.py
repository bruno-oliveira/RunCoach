"""Startup-time migration/backfill orchestration."""

import logging

from app.application.cleanup_service import (
    cleanup_anonymous_users,
    cleanup_inactive_accounts,
)
from app.dependencies import SessionLocal, engine
from app.migrations import run_alembic_migrations
from app.migrations.vdot_backfill import backfill_vdot

logger = logging.getLogger(__name__)


def run_startup_migrations() -> None:
    """Apply DB migrations, data backfills, and retention cleanup."""
    run_alembic_migrations(engine)

    session = SessionLocal()
    try:
        try:
            backfill_vdot(session)
        except Exception as e:
            session.rollback()
            logger.warning("VDOT backfill failed: %s", e)

        try:
            from app.contexts.runner.fitness.effort_classifier import backfill_effort_classes

            updated = backfill_effort_classes(session)
            if updated:
                session.commit()
                logger.info("Effort-class backfill updated %d runs", updated)
        except Exception as e:
            session.rollback()
            logger.warning("Effort-class backfill failed: %s", e)

        try:
            cleanup_inactive_accounts(session)
        except Exception as e:
            session.rollback()
            logger.warning("Inactive account cleanup failed: %s", e)

        try:
            cleanup_anonymous_users(session)
        except Exception as e:
            session.rollback()
            logger.warning("Anonymous user cleanup failed: %s", e)
    finally:
        session.close()
