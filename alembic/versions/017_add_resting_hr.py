"""Add resting_hr to users.

Revision ID: 017_add_resting_hr
Revises: 016_add_inferred_workout_type
Create Date: 2026-06-15
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "017_add_resting_hr"
down_revision: Union[str, Sequence[str], None] = "016_add_inferred_workout_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("resting_hr", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("resting_hr")
