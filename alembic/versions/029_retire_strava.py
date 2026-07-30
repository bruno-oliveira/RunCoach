"""Retire the Strava integration; keep where each run came from.

Intervals.icu is the only activity source now, so the Strava credentials on
``users`` and the ``strava_activity_id`` on ``run_logs`` have nothing left to
serve. Dropping the run column outright would lose something that is still
read, though: ``RunLog.effective_workout_type`` treats a *platform-imported*
run's ``workout_type`` as unreliable (Strava defaulted the blank to "easy") and
defers to the inferred type instead. The only marker of that on several hundred
historical runs is the presence of a provider id.

So the provenance moves to a neutral ``run_logs.source`` before the Strava
column goes:

* a row with either provider id was imported and keeps deferring to inference,
* everything else was hand-logged and keeps trusting the runner's own tag.

Revision ID: 029_retire_strava
Revises: 028_add_nudge_email_prefs
Create Date: 2026-07-30
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "029_retire_strava"
down_revision: Union[str, Sequence[str], None] = "028_add_nudge_email_prefs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STRAVA_USER_COLUMNS = (
    "strava_athlete_id",
    "strava_access_token",
    "strava_refresh_token",
    "strava_token_expires_at",
    "strava_last_synced_at",
)


def _drop_indexes_on(table: str, column: str) -> None:
    """Drop every index covering ``column``, whatever it happens to be called.

    SQLite has no DROP COLUMN, so batch mode rebuilds the table and replays its
    indexes onto the new shape — an index on the dropped column fails there. The
    lookup is by covered column rather than by name because this database has
    been through renames: production still carries ``ix_users_strava_id`` where
    a database built from the migration chain has ``ix_users_strava_athlete_id``.
    """
    inspector = sa.inspect(op.get_bind())
    for index in inspector.get_indexes(table):
        if column in (index.get("column_names") or []):
            op.drop_index(index["name"], table_name=table)


def upgrade() -> None:
    op.add_column("run_logs", sa.Column("source", sa.String(20), nullable=True))

    # Order matters: intervals last so a run known to both ends up attributed
    # to the platform still feeding it.
    op.execute("UPDATE run_logs SET source = 'manual'")
    op.execute(
        "UPDATE run_logs SET source = 'strava' WHERE strava_activity_id IS NOT NULL"
    )
    op.execute(
        "UPDATE run_logs SET source = 'intervals' "
        "WHERE intervals_activity_id IS NOT NULL"
    )

    _drop_indexes_on("run_logs", "strava_activity_id")
    with op.batch_alter_table("run_logs") as batch_op:
        batch_op.drop_column("strava_activity_id")

    _drop_indexes_on("users", "strava_athlete_id")
    with op.batch_alter_table("users") as batch_op:
        for column in STRAVA_USER_COLUMNS:
            batch_op.drop_column(column)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("strava_athlete_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("strava_access_token", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("strava_refresh_token", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("strava_token_expires_at", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("strava_last_synced_at", sa.Integer(), nullable=True)
        )
    op.create_index("ix_users_strava_athlete_id", "users", ["strava_athlete_id"])

    with op.batch_alter_table("run_logs") as batch_op:
        batch_op.add_column(sa.Column("strava_activity_id", sa.String(), nullable=True))
        batch_op.drop_column("source")
    op.create_index(
        "ix_run_logs_strava_activity_id", "run_logs", ["strava_activity_id"]
    )

    # The Strava activity ids themselves are not recoverable — this restores the
    # shape of the schema, not the data that was in it.
