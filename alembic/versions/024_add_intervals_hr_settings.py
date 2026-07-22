"""Add Intervals.icu-synced HR anchor columns to users.

Keeps the athlete's max HR / LTHR / resting HR as configured in Intervals.icu in
their own columns, separate from any value the runner typed into RunCoach. This
gives HR-zone resolution a clean provenance order — a manual RunCoach entry wins,
then the synced Intervals value, then detection/estimation — so a re-sync always
refreshes the connected-platform value without ever clobbering a manual override.

Revision ID: 024_add_intervals_hr_settings
Revises: 023_add_readiness_logs
Create Date: 2026-07-22
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "024_add_intervals_hr_settings"
down_revision: Union[str, Sequence[str], None] = "023_add_readiness_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("intervals_max_hr", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("intervals_lthr", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("intervals_resting_hr", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("intervals_resting_hr")
        batch_op.drop_column("intervals_lthr")
        batch_op.drop_column("intervals_max_hr")
