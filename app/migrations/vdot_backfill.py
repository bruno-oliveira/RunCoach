"""VDOT backfill utility for existing runs."""

import logging

from sqlalchemy.orm import Session

from app.core.training.vdot_calculator import VDOTCalculator
from app.models.run_log import RunLog

logger = logging.getLogger(__name__)


def backfill_vdot(session: Session) -> int:
    """Backfill VDOT for runs that have sufficient distance but no VDOT yet.

    Returns the number of runs updated.
    """
    runs = (
        session.query(RunLog)
        .filter(
            RunLog.vdot.is_(None),
            RunLog.distance_km >= 2.0,
            RunLog.duration_minutes > 0,
        )
        .all()
    )
    if not runs:
        return 0

    updated = 0
    for run in runs:
        vdot = VDOTCalculator.calculate_vdot(
            run.distance_km,
            int(run.duration_minutes * 60),
            elevation_gain_m=run.elevation_gain_m,
        )
        if vdot:
            run.vdot = vdot
            updated += 1

    session.commit()
    logger.info("VDOT backfill: updated %d/%d runs", updated, len(runs))
    return updated
