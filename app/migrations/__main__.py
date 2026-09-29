"""``python -m app.migrations`` — bring the database to head, then exit.

This is the entrypoint Fly's ``[deploy] release_command`` runs. It exists as a
separate path from the lifespan call on purpose.

A release command executes on a throwaway machine **with the volume attached and
before any traffic moves**, so a migration that fails aborts the deploy and the
previous release keeps serving. The same migration run inline at boot instead
produces a machine that fails its health check forever, gets restarted by Fly,
fails again — a loop with no signal about the cause.

Production therefore sets ``RUN_STARTUP_MIGRATIONS=false`` (see ``fly.toml``) so
the lifespan does no DDL, while local development and ``docker run`` without Fly
keep the default (on), where there is no release hook to lean on.

Lives inside ``app/`` rather than ``scripts/`` because the production image only
copies ``app/``, ``alembic/`` and ``alembic.ini`` — a migration entrypoint the
image cannot run is not an entrypoint.
"""

import logging
import sys

from app.infrastructure.config import settings, setup_logging
from app.migrations.startup import run_startup_migrations

logger = logging.getLogger(__name__)


def main() -> int:
    """Apply migrations and backfills. Returns a process exit code."""
    setup_logging(settings)
    logger.info("Applying migrations (release command)")
    try:
        run_startup_migrations()
    except Exception:
        # Non-zero exit is what aborts the deploy; log the traceback so the
        # release log names the migration that failed.
        logger.exception("Migration failed — aborting release")
        return 1
    logger.info("Migrations applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
