"""Add threshold_hr to users.

Revision ID: 019_add_threshold_hr
Revises: 018_prune_adaptation_schema
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "019_add_threshold_hr"
down_revision: Union[str, Sequence[str], None] = "018_prune_adaptation_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("threshold_hr", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("threshold_hr")
