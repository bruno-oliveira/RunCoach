"""Add adaptation_revision to training_plans.

Revision ID: 012_add_adaptation_revision
Revises: 011_add_last_change_plan
Create Date: 2026-05-18
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "012_add_adaptation_revision"
down_revision: Union[str, Sequence[str], None] = "011_add_last_change_plan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.add_column(
            sa.Column(
                "adaptation_revision",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.drop_column("adaptation_revision")
