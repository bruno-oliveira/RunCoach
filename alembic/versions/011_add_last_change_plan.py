"""Add last_change_plan to training_plans.

Revision ID: 011_add_last_change_plan
Revises: 010_add_auto_adjust_enabled
Create Date: 2026-05-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011_add_last_change_plan"
down_revision: Union[str, Sequence[str], None] = "010_add_auto_adjust_enabled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.add_column(
            sa.Column("last_change_plan", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.drop_column("last_change_plan")
