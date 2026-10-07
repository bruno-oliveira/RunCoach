"""Remember the easy pace a plan's easy band was built around.

A plan's easy band used to be a fixed slice of its VDOT. It is now the pace the
runner actually jogs at an easy heart rate, fifteen seconds either side, and it
follows them as that pace moves. The plan has to remember which pace its steps
were written from: every later rebuild of a single day (an adjustment, a type
swap, a re-pace) has to reproduce the same band or the day sits beside
untouched ones with a different easy pace.

Nullable, with no backfill: NULL means "no measured pace", and such a plan
keeps the band its VDOT implies until the runner's next sync measures one.

Revision ID: 037_add_plan_easy_pace
Revises: 036_add_watch_event_pairing
Create Date: 2026-10-07
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "037_add_plan_easy_pace"
down_revision: Union[str, Sequence[str], None] = "036_add_watch_event_pairing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch:
        batch.add_column(sa.Column("easy_pace_min_km", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch:
        batch.drop_column("easy_pace_min_km")
