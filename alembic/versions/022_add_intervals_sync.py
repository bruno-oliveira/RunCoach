"""Add Intervals.icu account and activity sync fields.

Revision ID: 022_add_intervals_sync
Revises: 021_add_proactive_nudge
Create Date: 2026-07-19
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "022_add_intervals_sync"
down_revision: Union[str, Sequence[str], None] = "021_add_proactive_nudge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("intervals_athlete_id", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("intervals_access_token", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("intervals_last_synced_at", sa.Integer(), nullable=True)
        )
        batch_op.create_index(
            "ix_users_intervals_athlete_id",
            ["intervals_athlete_id"],
            unique=True,
        )

    with op.batch_alter_table("run_logs") as batch_op:
        batch_op.add_column(
            sa.Column("intervals_activity_id", sa.String(), nullable=True)
        )
        batch_op.create_index(
            "ix_run_logs_intervals_activity_id",
            ["intervals_activity_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("run_logs") as batch_op:
        batch_op.drop_index("ix_run_logs_intervals_activity_id")
        batch_op.drop_column("intervals_activity_id")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_intervals_athlete_id")
        batch_op.drop_column("intervals_last_synced_at")
        batch_op.drop_column("intervals_access_token")
        batch_op.drop_column("intervals_athlete_id")
