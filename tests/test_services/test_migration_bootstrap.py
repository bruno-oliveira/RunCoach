"""The pre-Alembic bootstrap must stamp the *head*, never an intermediate one.

`run_alembic_migrations` has a branch for a database that already has tables but
no `alembic_version` — a pre-Alembic install. It used to stamp a hardcoded
constant, `HEAD_REVISION = "011_add_last_change_plan"`, which had drifted far
behind the real head. Alembic then replayed every migration after 011 on a
schema that already contained them, and the boot died on the first
`create_table` for a table that was already there.

The reproduction below is faithful: build a database at head, delete its
`alembic_version` so it looks pre-Alembic, and require the bootstrap to be a
no-op rather than a replay.
"""

import sqlite3

import pytest
from sqlalchemy import create_engine

from app.migrations import current_head, run_alembic_migrations
from tests.conftest import _run_alembic_migrations


def _alembic_version(db_path) -> str | None:
    with sqlite3.connect(db_path) as conn:
        try:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.OperationalError:
            return None
    return row[0] if row else None


def _table_names(db_path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }


def _engine(db_path):
    return create_engine(f"sqlite:///{db_path}")


@pytest.fixture
def db_at_head(tmp_path):
    """A fully migrated database, then de-tagged to look pre-Alembic."""
    db_path = tmp_path / "legacy.db"
    engine = _engine(db_path)
    _run_alembic_migrations(engine)
    engine.dispose()

    # A real row, so a destructive replay would be visible.
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO users (id, created_at) VALUES ('u1', '2026-01-01')")
        conn.execute("DROP TABLE alembic_version")
        conn.commit()

    assert _alembic_version(db_path) is None, "fixture must look pre-Alembic"
    return db_path


class TestCurrentHead:
    def test_resolves_the_revision_the_script_directory_calls_head(self):
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config("alembic.ini")
        expected = ScriptDirectory.from_config(cfg).get_current_head()

        assert current_head(cfg) == expected

    def test_the_chain_has_exactly_one_head(self):
        """Two heads means `upgrade head` is ambiguous and silently partial."""
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
        assert len(heads) == 1

    def test_head_is_not_a_stale_intermediate_revision(self):
        """The literal that caused the bug must not come back."""
        from alembic.config import Config

        assert current_head(Config("alembic.ini")) != "011_add_last_change_plan"

    def test_fails_loudly_when_there_is_no_head(self, tmp_path):
        from alembic.config import Config

        (tmp_path / "empty_versions").mkdir()
        cfg = Config("alembic.ini")
        cfg.set_main_option("script_location", str(tmp_path))
        cfg.set_main_option("version_locations", str(tmp_path / "empty_versions"))

        with pytest.raises(RuntimeError, match="No Alembic head"):
            current_head(cfg)


class TestPreAlembicBootstrap:
    def test_stamps_head_and_does_not_replay_history(self, db_at_head):
        """The regression: this raised `table refresh_tokens already exists`."""
        run_alembic_migrations(_engine(db_at_head))

        from alembic.config import Config

        assert _alembic_version(db_at_head) == current_head(Config("alembic.ini"))

    def test_running_migrations_does_not_silence_existing_loggers(self, tmp_path):
        """Alembic's `fileConfig` defaults to disabling loggers that already exist.

        `env.py` runs on every upgrade — including the in-process run in the
        FastAPI lifespan — so the default switched off every `app.*` logger that
        had been created before boot. The app then served with its logging
        silently gone: no crash, no warning, nothing written. This is the canary
        for that, and it doubles as the reason a log-asserting test used to fail
        depending on which test ran first.
        """
        import logging

        logger = logging.getLogger("app.contexts.plan.generators.plan_generator")
        logger.disabled = False
        assert logger.disabled is False, "logger must predate the migration run"

        captured: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        handler = _Capture()
        was_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            run_alembic_migrations(_engine(tmp_path / "logging.db"))
            logger.warning("still audible after migrations")
        finally:
            logger.removeHandler(handler)
            logger.setLevel(was_level)

        assert logger.disabled is False
        assert any("still audible" in r.getMessage() for r in captured)

    def test_existing_rows_survive_the_bootstrap(self, db_at_head):
        run_alembic_migrations(_engine(db_at_head))

        with sqlite3.connect(db_at_head) as conn:
            kept = conn.execute("SELECT id FROM users").fetchall()

        assert kept == [("u1",)]

    def test_a_tracked_database_is_left_alone(self, tmp_path):
        """The normal case must not be perturbed by the legacy branch."""
        db_path = tmp_path / "tracked.db"
        engine = _engine(db_path)
        run_alembic_migrations(engine)
        engine.dispose()

        before = _table_names(db_path)
        run_alembic_migrations(_engine(db_path))

        assert _table_names(db_path) == before
        # The temporary table Alembic's batch mode leaves behind on failure is
        # the fingerprint of a replay that went wrong.
        assert not any(name.startswith("_alembic_tmp") for name in before)

    def test_migrating_an_already_current_database_is_idempotent(self, tmp_path):
        db_path = tmp_path / "twice.db"
        run_alembic_migrations(_engine(db_path))
        first = _alembic_version(db_path)

        run_alembic_migrations(_engine(db_path))

        assert _alembic_version(db_path) == first
