"""Add adaptation_history column to training_plans.

Stores a JSON array of adaptation events for the plan evolution timeline.
"""

import sqlalchemy as sa

from alembic import op

revision = "002_add_adaptation_history"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.add_column(
            sa.Column("adaptation_history", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.drop_column("adaptation_history")
