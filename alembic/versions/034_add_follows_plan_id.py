"""Link a recovery block to the race plan it follows.

When a plan finishes, RunCoach offers a recovery block built from it. The link
is what keeps that offer honest: a plan whose block has already been started
shows "view your recovery block" instead of offering a second one, and the
block can name the race it is recovering from.

A plain indexed column rather than a foreign key: deleting the race plan should
leave its recovery block standing (``delete_plan`` clears the pointer), and
SQLite's batch mode would otherwise have to rebuild ``training_plans`` to add
the constraint.

Revision ID: 034_add_follows_plan_id
Revises: 033_push_and_wellness
Create Date: 2026-09-30
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "034_add_follows_plan_id"
down_revision: Union[str, Sequence[str], None] = "033_push_and_wellness"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch:
        batch.add_column(sa.Column("follows_plan_id", sa.String(), nullable=True))
        batch.create_index(
            "idx_training_plan_follows_plan_id", ["follows_plan_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch:
        batch.drop_index("idx_training_plan_follows_plan_id")
        batch.drop_column("follows_plan_id")
