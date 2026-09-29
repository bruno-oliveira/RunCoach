"""Health-check schema and the dependency probe behind ``/health``.

Lives here rather than in app/schemas so the pure schema layer no longer
depends on app.infrastructure.config (settings) — closing the upstream
dependency leak.

The probe matters more than the schema. A static ``{"status": "healthy"}`` only
proves the event loop is turning, which it still is when the SQLite volume has
failed to mount: every page then 500s while Fly's checks stay green and the
machine is never cycled. ``probe_database`` is what turns the endpoint into a
statement about whether this machine can actually serve a request.
"""

from typing import Callable, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.infrastructure.config import settings

# ``None`` when the dependency answered, otherwise a short human-readable
# reason. Deliberately not an exception: a health endpoint that can raise is a
# health endpoint that reports its own bug as an outage.
HealthProbe = Callable[[], Optional[str]]


class HealthResponse(BaseModel):
    """Health-check response."""

    status: str = "healthy"
    version: str = Field(default_factory=lambda: settings.app_version)
    # Per-dependency verdicts, e.g. {"database": "ok"}. Populated by the route
    # so a failing check names the broken dependency instead of just saying
    # "unhealthy" and leaving ops to guess.
    checks: dict[str, str] = Field(default_factory=dict)


def probe_database() -> Optional[str]:
    """``None`` when the database answers, else a short failure reason.

    ``SELECT 1`` rather than a read against a real table: this answers "is the
    volume mounted and the file openable?" — the failure mode that actually
    happens on this deployment — without depending on any schema version, so it
    keeps working during a rolling migration.

    The engine is imported inside the function because this module is reachable
    from ``app.schemas``; importing it at module scope would make every schema
    import construct the engine and its SQLite pragma listeners.
    """
    try:
        from app.infrastructure.database import engine

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return None
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def get_health_probe() -> HealthProbe:
    """The probe the health route consults.

    A FastAPI dependency so tests can substitute a failing probe through
    ``app.dependency_overrides`` and exercise the degraded branch without
    breaking a real database.
    """
    return probe_database
