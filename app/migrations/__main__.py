"""``python -m app.migrations`` — bring the database to head, then exit.

This is what ``start.sh`` runs before uvicorn, on the app machine. It exists as
a separate path from the lifespan call so a failure is a non-zero exit with the
traceback in the log, before the server ever binds its port.

It must run on the app machine. It was once Fly's ``[deploy] release_command``,
on the belief that a release machine has the volume attached. It does not: the
command migrated an empty throwaway database from revision 001, exited 0, and
the real ``/data/runcoach.db`` was never touched — a deploy that reports a
successful migration and then serves ``no such column``.

Production sets ``RUN_STARTUP_MIGRATIONS=false`` (see ``fly.toml``) so the
lifespan does not repeat the work in the same boot, while local development and
``docker run`` with another entrypoint keep the default (on).

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
    logger.info("Applying migrations")
    try:
        run_startup_migrations()
    except Exception:
        # Non-zero exit is what stops start.sh before uvicorn; log the
        # traceback so the machine log names the migration that failed.
        logger.exception("Migration failed — not starting the server")
        return 1
    logger.info("Migrations applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
