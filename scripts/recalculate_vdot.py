"""Recalculate all stored VDOT values with the updated sanity checks.

The VDOT calculator now rejects runs with unrealistic pace (<2:30/km),
which means previously inflated VDOTs from GPS glitches or auto-pause
artifacts will be nullified.

Usage:
    python scripts/recalculate_vdot.py          # dry-run (default)
    python scripts/recalculate_vdot.py --apply   # apply changes
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


def recalculate_all_vdots(dry_run: bool = True):
    """Recalculate VDOT for every run that currently has one.

    Runs that now fail the pace sanity check will have their VDOT set to NULL.
    """
    db = SessionLocal()
    try:
        runs = db.query(RunLog).filter(RunLog.vdot.isnot(None)).all()
        total = len(runs)
        logger.info(f"Found {total} runs with existing VDOT")

        updated = 0
        nullified = 0
        unchanged = 0

        for run in runs:
            old_vdot = run.vdot
            new_vdot = VDOTCalculator.calculate_vdot(
                run.distance_km, int(run.duration_minutes * 60)
            )

            if new_vdot is None and old_vdot is not None:
                pace = (
                    run.duration_minutes / run.distance_km if run.distance_km > 0 else 0
                )
                logger.info(
                    f"NULLIFY run {run.id}: {run.distance_km}km in {run.duration_minutes:.1f}min "
                    f"(pace {pace:.2f} min/km) — old VDOT {old_vdot} → NULL  "
                    f"[{run.notes or 'no name'}]"
                )
                if not dry_run:
                    run.vdot = None
                nullified += 1
            elif new_vdot != old_vdot:
                logger.info(
                    f"UPDATE run {run.id}: VDOT {old_vdot} → {new_vdot}  "
                    f"[{run.notes or 'no name'}]"
                )
                if not dry_run:
                    run.vdot = new_vdot
                updated += 1
            else:
                unchanged += 1

        if not dry_run:
            db.commit()

        mode = "DRY-RUN" if dry_run else "APPLIED"
        logger.info(
            f"{mode}: {nullified} nullified, {updated} updated, "
            f"{unchanged} unchanged out of {total} total"
        )
    finally:
        db.close()


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    if not apply:
        logger.info("Running in DRY-RUN mode. Pass --apply to commit changes.")
    recalculate_all_vdots(dry_run=not apply)
