"""Database migration utilities using Alembic."""

import logging

from alembic.config import Config
from sqlalchemy import Engine, inspect

from alembic import command

logger = logging.getLogger(__name__)

HEAD_REVISION = "011_add_last_change_plan"


def run_alembic_migrations(engine: Engine) -> None:
    """Run Alembic migrations programmatically at startup.

    Handles the case where the database already has tables but no
    alembic_version tracking (pre-Alembic databases): stamps the current
    revision so Alembic treats the schema as up-to-date.
    """
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))

    insp = inspect(engine)
    has_alembic_version = "alembic_version" in insp.get_table_names()
    has_existing_tables = "users" in insp.get_table_names()

    if has_existing_tables and not has_alembic_version:
        logger.info(
            "Existing database without Alembic tracking detected — "
            "stamping revision %s",
            HEAD_REVISION,
        )
        command.stamp(alembic_cfg, HEAD_REVISION)

    command.upgrade(alembic_cfg, "head")

    logger.info("Alembic migrations applied successfully")
