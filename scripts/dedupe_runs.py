#!/usr/bin/env python3
"""Remove runs stored twice under two different provider ids.

Until ``app/infrastructure/integrations/activity_dedup.py`` existed, each
importer only deduplicated against its own provider id, so a run offered by two
platforms got a row from each and every distance total counted it twice. The
importers dedupe on the activity now; this stays as the way to clean up
anything that slipped through before they did.

This collapses each duplicate pair onto one row. The surviving row is the one
carrying the most context (plan link, then splits, then the earliest import);
the other row's provider id — and its plan link, if the survivor has none — moves
across before it is deleted, so the run stays traceable to both platforms and no
future sync re-imports it.

    python3 scripts/dedupe_runs.py                      # report only, changes nothing
    python3 scripts/dedupe_runs.py --apply              # delete the duplicates
    DATABASE_URL=sqlite:///./copy.db python3 scripts/dedupe_runs.py --apply

Dry run is the default, and ``--apply`` is the only thing that writes. Point
DATABASE_URL at a copy first and check the report before running it for real.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from app.infrastructure.database.engine import SessionLocal  # noqa: E402
from app.infrastructure.integrations.activity_dedup import (  # noqa: E402
    MAX_CLOCK_SHIFT,
    is_same_activity,
)
from app.models.run_feedback import RunFeedback  # noqa: E402
from app.models.run_log import RunLog  # noqa: E402


def _richness(run: RunLog) -> tuple:
    """Sort key picking the row worth keeping — most context first."""
    return (
        run.training_plan_id is not None,
        run.daily_workout_id is not None,
        run.splits is not None,
        run.workout_type is not None,
        # Earliest import wins the tie: it is the row every other table that
        # references a run has had the longest to point at.
        -(run.created_at.timestamp() if run.created_at else 0),
    )


def find_duplicate_pairs(db: Session) -> List[Tuple[RunLog, RunLog]]:
    """Every (keep, drop) pair of rows describing the same activity."""
    runs = db.query(RunLog).order_by(RunLog.user_id, RunLog.date).all()
    pairs: List[Tuple[RunLog, RunLog]] = []
    dropped: set[str] = set()

    for index, first in enumerate(runs):
        if first.id in dropped:
            continue
        for second in runs[index + 1 :]:
            if second.user_id != first.user_id:
                break
            if (
                first.date
                and second.date
                and (second.date - first.date) > MAX_CLOCK_SHIFT
            ):
                break
            if second.id in dropped:
                continue
            if not is_same_activity(
                first.date, first.distance_km, second.date, second.distance_km
            ):
                continue
            keep, drop = sorted((first, second), key=_richness, reverse=True)
            pairs.append((keep, drop))
            dropped.add(drop.id)

    return pairs


CARRIED_FIELDS = (
    "intervals_activity_id",
    "training_plan_id",
    "daily_workout_id",
)


def merge(keep: RunLog, drop: RunLog, db: Session) -> dict:
    """Delete the duplicate row, returning what must move onto the survivor.

    Both provider-id columns are unique, so the survivor cannot take the other
    row's id while that row still exists. The caller applies the returned values
    once the deletes have been flushed.
    """
    carried = {
        field: getattr(drop, field)
        for field in CARRIED_FIELDS
        if getattr(keep, field) is None and getattr(drop, field) is not None
    }

    # run_feedback has no cascade, so its rows would outlive the run and break
    # the foreign key. The survivor keeps its own feedback.
    db.query(RunFeedback).filter(RunFeedback.run_log_id == drop.id).delete(
        synchronize_session=False
    )
    db.delete(drop)
    return carried


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually delete the duplicates (default: report only)",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        pairs = find_duplicate_pairs(db)
        if not pairs:
            print(
                f"no duplicate runs found in {os.environ.get('DATABASE_URL', 'the configured database')}"
            )
            return 0

        total_km = sum(drop.distance_km or 0.0 for _, drop in pairs)
        print(f"{len(pairs)} duplicated runs, {total_km:.1f} km counted twice\n")
        for keep, drop in pairs:
            print(
                f"  {drop.date}  {drop.distance_km:>6} km"
                f"   keep {keep.id[:8]} [{keep.intervals_activity_id or keep.source}]"
                f"   drop {drop.id[:8]} [{drop.intervals_activity_id or drop.source}]"
            )

        if not args.apply:
            print(
                "\ndry run — nothing was changed. Re-run with --apply to delete these."
            )
            return 0

        carried = [(keep, merge(keep, drop, db)) for keep, drop in pairs]
        db.flush()  # duplicates gone — their provider ids are free to reuse
        for keep, values in carried:
            for field, value in values.items():
                setattr(keep, field, value)
        db.commit()
        print(
            f"\ndeleted {len(pairs)} duplicate runs; {total_km:.1f} km no longer double-counted"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
