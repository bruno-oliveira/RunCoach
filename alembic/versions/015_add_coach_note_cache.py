"""Add coach_note_cache to training_plans.

Revision ID: 015_add_coach_note_cache
Revises: 014_fix_favorite_recipes_id
Create Date: 2026-05-26
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "015_add_coach_note_cache"
down_revision: Union[str, Sequence[str], None] = "014_fix_favorite_recipes_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.add_column(
            sa.Column("coach_note_cache", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.drop_column("coach_note_cache")
