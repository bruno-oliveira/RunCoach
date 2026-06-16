"""Add max_hr to users.

Revision ID: 020_add_max_hr
Revises: 019_add_threshold_hr
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "020_add_max_hr"
down_revision: Union[str, Sequence[str], None] = "019_add_threshold_hr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("max_hr", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("max_hr")
