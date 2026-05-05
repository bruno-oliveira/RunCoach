"""Drop triathlon_plans table.

Revision ID: 006_drop_triathlon_plans
Revises: 005_add_effort_class
Create Date: 2026-05-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_drop_triathlon_plans"
down_revision: Union[str, Sequence[str], None] = "005_add_effort_class"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_triathlon_plans_user_id", table_name="triathlon_plans")
    op.drop_table("triathlon_plans")


def downgrade() -> None:
    op.create_table(
        "triathlon_plans",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("distance", sa.String(), nullable=True),
        sa.Column("weeks_duration", sa.Integer(), nullable=True),
        sa.Column("plan_data", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_triathlon_plans_user_id", "triathlon_plans", ["user_id"])
