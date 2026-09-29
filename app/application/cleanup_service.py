"""Automated cleanup of inactive user accounts per data retention policy."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User

logger = logging.getLogger(__name__)

INACTIVE_MONTHS = 24
ANONYMOUS_RETENTION_DAYS = 90


def cleanup_inactive_accounts(db: Session, *, dry_run: bool = False) -> int:
    """Delete user accounts with no activity in the last 24 months.

    Only deletes users who have a last_activity timestamp — accounts
    that predate the field are skipped (they'll be caught once
    last_activity is populated on their next login).

    Returns the number of accounts deleted (or that would be deleted
    in dry_run mode).
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=INACTIVE_MONTHS * 30)
    ).replace(tzinfo=None)

    inactive_users = (
        db.query(User)
        .filter(
            User.last_activity.isnot(None),
            User.last_activity < cutoff,
        )
        .all()
    )

    count = len(inactive_users)
    if count == 0:
        logger.info("No inactive accounts found (cutoff: %s)", cutoff)
        return 0

    if dry_run:
        logger.info(
            "Dry run: would delete %d inactive account(s) (cutoff: %s)", count, cutoff
        )
        return count

    for user in inactive_users:
        logger.info(
            "Deleting inactive account %s (last activity: %s)",
            user.id,
            user.last_activity,
        )
        db.delete(user)

    db.commit()
    logger.info("Deleted %d inactive account(s)", count)
    return count


def cleanup_anonymous_users(db: Session, *, dry_run: bool = False) -> int:
    """Delete anonymous users (no google_id, no email) older than ANONYMOUS_RETENTION_DAYS.

    Anonymous user records are created by the middleware when a visitor lands
    on a plan-generation page. They accumulate without ever being claimed by a
    login. Retention is keyed off ``last_activity`` (falls back to
    ``created_at`` if last_activity is null).

    The cutoff is applied in SQL rather than in Python. This used to load every
    anonymous row the table had ever held and filter in a loop, which is free at
    nine users and a full-table materialisation at ten thousand — on the boot
    path, where it runs before the machine can pass a health check.

    ``coalesce`` reproduces the previous Python exactly: a row with both
    timestamps null compares NULL and is skipped, which is why the old
    ``if (u.last_activity or u.created_at)`` guard was there.

    Cascade deletes on User → TrainingPlan / RunLog / FavoriteRecipe
    clean up associated rows automatically (the ORM-level delete is deliberate:
    a bulk ``query.delete()`` would bypass those cascades).
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=ANONYMOUS_RETENTION_DAYS)
    ).replace(tzinfo=None)

    stale_anonymous = (
        db.query(User)
        .filter(
            User.google_id.is_(None),
            User.email.is_(None),
            func.coalesce(User.last_activity, User.created_at) < cutoff,
        )
        .all()
    )

    count = len(stale_anonymous)
    if count == 0:
        logger.info("No stale anonymous users found (cutoff: %s)", cutoff)
        return 0

    if dry_run:
        logger.info(
            "Dry run: would delete %d anonymous user(s) (cutoff: %s)", count, cutoff
        )
        return count

    # One summary line, then per-row ids at DEBUG: deleting a backlog of
    # thousands should not emit thousands of INFO lines into the release log,
    # but the ids stay recoverable when someone needs them.
    logger.info("Deleting %d anonymous user(s) older than %s", count, cutoff)
    logger.debug("Anonymous users to delete: %s", [user.id for user in stale_anonymous])
    for user in stale_anonymous:
        db.delete(user)

    db.commit()
    logger.info("Deleted %d anonymous user(s)", count)
    return count
