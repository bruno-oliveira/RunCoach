"""Add pending_recommendation and last_recommendation_week to training_plans.

Supports auto-triggered adaptation recommendations that surface as
notifications rather than auto-applying adjustments.
"""

import sqlalchemy as sa

from alembic import op

revision = "004_add_pending_recommendation"
down_revision = "6329811ea4bd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.add_column(
            sa.Column("pending_recommendation", sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_recommendation_week", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.drop_column("last_recommendation_week")
        batch_op.drop_column("pending_recommendation")
