"""Add derived effort_class column to run_logs.

A small classifier writes one of {race_effort, tempo_effort, easy_effort}
based on pace-percentile + perceived effort. We keep this separate from the
user-tagged `workout_type` so we don't overwrite their input -- and because
`workout_type` is unreliable in practice (Strava defaults it to easy).
"""

import sqlalchemy as sa

from alembic import op

revision = "005_add_effort_class"
down_revision = "004_add_pending_recommendation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("run_logs") as batch_op:
        batch_op.add_column(
            sa.Column("effort_class", sa.String(length=20), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("run_logs") as batch_op:
        batch_op.drop_column("effort_class")
