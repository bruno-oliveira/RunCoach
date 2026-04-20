"""Database migration utilities using Alembic."""

import logging

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

logger = logging.getLogger(__name__)


def run_alembic_migrations(engine: Engine) -> None:
    """Run Alembic migrations programmatically at startup."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations applied successfully")
