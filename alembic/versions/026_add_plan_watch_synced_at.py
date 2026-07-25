"""Track when a plan was last pushed to the athlete's watch calendar.

Marks a plan as "on the watch" so later adaptations can be re-pushed
automatically. Without this we can't tell a runner who has sent workouts (and
expects the watch to stay correct) from one who never has (and would be
surprised to find their calendar filled in).

Revision ID: 026_add_plan_watch_synced_at
Revises: 025_recompute_inferred_workout_type
Create Date: 2026-07-25
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "026_add_plan_watch_synced_at"
down_revision: Union[str, Sequence[str], None] = "025_recompute_inferred_workout_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.add_column(sa.Column("watch_synced_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.drop_column("watch_synced_at")
