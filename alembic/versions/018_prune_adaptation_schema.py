"""Prune dead adaptation schema.

Consolidation: plan adaptation is now fully user-driven through the
"Adjust my plan" intent menu. This removes the schema that backed the
retired surfaces:

- ``users.auto_adjust_enabled``  (the removed auto-accept toggle)
- ``training_plans.adaptation_alert``  (the removed alert card)
- ``training_plans.pending_recommendation`` / ``last_recommendation_week``
  (the removed weekly recommendation banner)
- the ``readiness_logs`` table (the removed daily readiness check-in)

This migration also merges the two pre-existing Alembic heads into one.

Revision ID: 018_prune_adaptation_schema
Revises: 017_add_resting_hr, 6329811ea4bd
Create Date: 2026-06-15
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "018_prune_adaptation_schema"
down_revision: Union[str, Sequence[str], None] = (
    "017_add_resting_hr",
    "6329811ea4bd",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("readiness_logs")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("auto_adjust_enabled")

    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.drop_column("adaptation_alert")
        batch_op.drop_column("pending_recommendation")
        batch_op.drop_column("last_recommendation_week")


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.add_column(
            sa.Column("last_recommendation_week", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("pending_recommendation", sa.JSON(), nullable=True)
        )
        batch_op.add_column(sa.Column("adaptation_alert", sa.JSON(), nullable=True))

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "auto_adjust_enabled",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )

    op.create_table(
        "readiness_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("sleep", sa.Integer(), nullable=False),
        sa.Column("soreness", sa.Integer(), nullable=False),
        sa.Column("energy", sa.Integer(), nullable=False),
        sa.Column("stress", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default="50"),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="ready"
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "idx_readiness_user_date",
        "readiness_logs",
        ["user_id", "log_date"],
        unique=True,
    )
