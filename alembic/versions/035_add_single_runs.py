"""Single runs: one-off workouts outside any training plan.

``single_runs`` holds the generated session. ``run_logs.single_run_id`` marks
the imported activity that completed it, which is what lets the run mapper
count that run as training load without matching it to a planned day.

The pointer is a plain indexed column rather than a foreign key, for the same
reason as ``training_plans.follows_plan_id``: SQLite's batch mode would have to
rebuild ``run_logs`` to add the constraint, and deleting a single run should
leave the logged run standing (the service clears the pointer).

Revision ID: 035_add_single_runs
Revises: 034_add_follows_plan_id
Create Date: 2026-10-02
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "035_add_single_runs"
down_revision: Union[str, Sequence[str], None] = "034_add_follows_plan_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "single_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("run_type", sa.String(length=20), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("workout", sa.JSON(), nullable=False),
        sa.Column("vdot", sa.Float(), nullable=True),
        sa.Column("watch_event_hash", sa.String(length=32), nullable=True),
        sa.Column("watch_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_single_run_user_date", "single_runs", ["user_id", "date"])

    with op.batch_alter_table("run_logs") as batch:
        batch.add_column(sa.Column("single_run_id", sa.String(), nullable=True))
        batch.create_index("idx_run_log_single_run", ["single_run_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("run_logs") as batch:
        batch.drop_index("idx_run_log_single_run")
        batch.drop_column("single_run_id")

    op.drop_index("idx_single_run_user_date", table_name="single_runs")
    op.drop_table("single_runs")
