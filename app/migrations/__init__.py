"""Database migration utilities using Alembic."""

import logging

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect

from alembic import command

logger = logging.getLogger(__name__)


def current_head(alembic_cfg: Config) -> str:
    """The single head revision in ``alembic/versions``.

    Derived from the script directory rather than hardcoded. It used to be a
    module constant (``HEAD_REVISION = "011_add_last_change_plan"``) that drifted
    ~22 migrations behind: a pre-Alembic database was stamped at 011 and then had
    012–033 replayed over a schema that already contained them, so
    ``013_add_refresh_tokens`` would try to ``create_table`` a table that was
    already there and the boot would fail. Deriving it means the value cannot go
    stale again.

    Raises:
        RuntimeError: when the script directory has no head — an empty
            ``alembic/versions``, or the config pointing somewhere unexpected.
            Failing here beats stamping a database into a state nobody chose.
    """
    head = ScriptDirectory.from_config(alembic_cfg).get_current_head()
    if head is None:
        raise RuntimeError(
            "No Alembic head revision found — is alembic/versions populated "
            "and is alembic.ini pointing at it?"
        )
    return head


def run_alembic_migrations(engine: Engine) -> None:
    """Run Alembic migrations programmatically.

    Handles the case where the database already has tables but no
    ``alembic_version`` tracking (a pre-Alembic database): stamps the head
    revision so Alembic treats the schema as already up-to-date, then lets
    ``upgrade`` be the no-op it should be. Stamping the head — not an
    intermediate revision — is the only choice that cannot replay DDL over a
    schema that already has it.
    """
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))

    insp = inspect(engine)
    has_alembic_version = "alembic_version" in insp.get_table_names()
    has_existing_tables = "users" in insp.get_table_names()

    if has_existing_tables and not has_alembic_version:
        head = current_head(alembic_cfg)
        logger.warning(
            "Existing database without Alembic tracking detected — stamping "
            "head (%s) and assuming the schema is current. If this database "
            "predates some migrations, run them by hand: they will NOT be "
            "replayed.",
            head,
        )
        command.stamp(alembic_cfg, head)

    command.upgrade(alembic_cfg, "head")

    logger.info("Alembic migrations applied successfully")
