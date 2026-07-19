"""Add pace_zones_updated_at to weekly_plans.

Revision ID: 009_add_pace_zones_updated_at
Revises: 008_add_training_terrain
Create Date: 2026-05-15
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "009_add_pace_zones_updated_at"
down_revision: Union[str, Sequence[str], None] = "008_add_training_terrain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("weekly_plans") as batch_op:
        batch_op.add_column(
            sa.Column("pace_zones_updated_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("weekly_plans") as batch_op:
        batch_op.drop_column("pace_zones_updated_at")
