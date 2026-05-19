"""Automated cleanup of inactive user accounts per data retention policy."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.user import User

logger = logging.getLogger(__name__)

INACTIVE_MONTHS = 24


def cleanup_inactive_accounts(db: Session, *, dry_run: bool = False) -> int:
    """Delete user accounts with no activity in the last 24 months.

    Only deletes users who have a last_activity timestamp — accounts
    that predate the field are skipped (they'll be caught once
    last_activity is populated on their next login).

    Returns the number of accounts deleted (or that would be deleted
    in dry_run mode).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=INACTIVE_MONTHS * 30)).replace(tzinfo=None)

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
        logger.info("Dry run: would delete %d inactive account(s) (cutoff: %s)", count, cutoff)
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
