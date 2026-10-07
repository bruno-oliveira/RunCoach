"""Remember that the runner turned down the recovery block after a plan.

The block after a finished race plan is offered, never imposed, and the offer
stood on the plan page and the home hero until the six-week window closed — a
runner who had decided to rest, or to recover their own way, had no way to say
so. A dismissal is a decision about one finished plan, so it lives on that row.

Nullable, with no backfill: NULL means "not dismissed", which is what every
existing plan is.

Revision ID: 038_add_plan_recovery_dismissed_at
Revises: 037_add_plan_easy_pace
Create Date: 2026-10-07
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "038_add_plan_recovery_dismissed_at"
down_revision: Union[str, Sequence[str], None] = "037_add_plan_easy_pace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch:
        batch.add_column(
            sa.Column("recovery_dismissed_at", sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch:
        batch.drop_column("recovery_dismissed_at")
