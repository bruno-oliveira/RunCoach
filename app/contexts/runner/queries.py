"""Read-only query helpers for the runner context (CQRS-lite read side).

Per the persistence boundary (see ``ARCHITECTURE_PERSISTENCE.md``), writes go
through repositories while read-heavy paths use thin query functions like
these. Raw ``db.query(...)`` here is intentional, not a leak: these functions
are the documented read side and keep that SQL out of routers and services.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import RunLog

# Average climb per km above which a run counts as a trail run.
TRAIL_ELEVATION_M_PER_KM = 20.0


def count_prior_trail_runs(user_id: str, db: Session) -> int:
    """Count a user's runs that average >= 20 m of climb per km."""
    runs = (
        db.query(RunLog.distance_km, RunLog.elevation_gain_m)
        .filter(
            RunLog.user_id == user_id,
            RunLog.distance_km > 0,
            RunLog.elevation_gain_m.isnot(None),
        )
        .all()
    )
    return sum(
        1
        for distance_km, gain in runs
        if distance_km and gain and gain / distance_km >= TRAIL_ELEVATION_M_PER_KM
    )


__all__ = ["count_prior_trail_runs", "TRAIL_ELEVATION_M_PER_KM"]
