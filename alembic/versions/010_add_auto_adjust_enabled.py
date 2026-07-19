"""Add auto_adjust_enabled to users.

Revision ID: 010_add_auto_adjust_enabled
Revises: 009_add_pace_zones_updated_at
Create Date: 2026-05-15
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "010_add_auto_adjust_enabled"
down_revision: Union[str, Sequence[str], None] = "009_add_pace_zones_updated_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "auto_adjust_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("auto_adjust_enabled")
