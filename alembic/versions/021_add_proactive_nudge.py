"""Add last_proactive_nudge to training_plans.

Revision ID: 021_add_proactive_nudge
Revises: 020_add_max_hr
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "021_add_proactive_nudge"
down_revision: Union[str, Sequence[str], None] = "020_add_max_hr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.add_column(
            sa.Column("last_proactive_nudge", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.drop_column("last_proactive_nudge")
