"""Backfill VDOT for existing race-type runs.

Run this script to calculate and store VDOT values for all existing
race-type runs that don't have a VDOT calculated yet.

Usage:
    python scripts/backfill_race_vdot.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.training.vdot_calculator import VDOTCalculator
from app.dependencies import SessionLocal
from app.models import RunLog

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def reclassify_strava_races():
    """Fix Strava-synced runs that were mapped as 'tempo' instead of 'race'.

    Strava workout_type=1 means 'Race', but was previously mapped to 'tempo'.
    This only affects Strava-synced runs (strava_activity_id IS NOT NULL).
    """
    db = SessionLocal()
    try:
        misclassified = (
            db.query(RunLog)
            .filter(
                RunLog.strava_activity_id.isnot(None),
                RunLog.workout_type == "tempo",
            )
            .all()
        )

        reclassified = len(misclassified)
        if reclassified == 0:
            logger.info("No Strava runs need reclassification")
            return 0

        for run in misclassified:
            run.workout_type = "race"

        db.commit()
        logger.info(f"Reclassified {reclassified} Strava runs from 'tempo' to 'race'")
        return reclassified
    finally:
        db.close()


def backfill_race_vdot():
    """Backfill VDOT for all existing race-type runs."""
    db = SessionLocal()
    try:
        races_to_update = (
            db.query(RunLog)
            .filter(
                RunLog.workout_type == "race",
                RunLog.vdot.is_(None),
            )
            .all()
        )

        total = len(races_to_update)
        if total == 0:
            logger.info("No race runs need VDOT backfill")
            return

        logger.info(f"Found {total} race runs to backfill")

        updated = 0
        skipped = 0

        for run in races_to_update:
            try:
                if run.distance_km <= 0 or run.duration_minutes <= 0:
                    logger.warning(
                        f"Skipping run {run.id}: invalid distance or duration"
                    )
                    skipped += 1
                    continue

                vdot = VDOTCalculator.calculate_vdot(
                    run.distance_km, int(run.duration_minutes * 60)
                )

                if vdot:
                    run.vdot = vdot
                    updated += 1
                    logger.debug(f"Updated run {run.id}: VDOT = {vdot}")
                else:
                    logger.warning(f"Could not calculate VDOT for run {run.id}")
                    skipped += 1

            except Exception as e:
                logger.error(f"Error processing run {run.id}: {e}")
                skipped += 1

        db.commit()
        logger.info(f"Backfill complete: {updated} updated, {skipped} skipped")

    finally:
        db.close()


if __name__ == "__main__":
    reclassify_strava_races()
    backfill_race_vdot()
