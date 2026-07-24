"""Add readiness_logs table (daily morning check-ins).

Revision ID: 023_add_readiness_logs
Revises: 022_add_intervals_sync
Create Date: 2026-07-22
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "023_add_readiness_logs"
down_revision: Union[str, Sequence[str], None] = "022_add_intervals_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "readiness_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("sleep_hours", sa.Float(), nullable=True),
        sa.Column("sleep_quality", sa.Integer(), nullable=True),
        sa.Column("energy", sa.Integer(), nullable=True),
        sa.Column("soreness", sa.Integer(), nullable=True),
        sa.Column("stress", sa.Integer(), nullable=True),
        sa.Column("resting_hr", sa.Integer(), nullable=True),
        sa.Column("hrv", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "date", name="uq_readiness_user_date"),
    )
    op.create_index("idx_readiness_user_date", "readiness_logs", ["user_id", "date"])


def downgrade() -> None:
    op.drop_index("idx_readiness_user_date", table_name="readiness_logs")
    op.drop_table("readiness_logs")
