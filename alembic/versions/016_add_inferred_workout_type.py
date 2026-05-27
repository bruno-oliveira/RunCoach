"""Add inferred_workout_type, confidence, and splits to run_logs.

Strava leaves workout_type unset on most activities (the sync defaults it to
"easy"), collapsing tempo/interval/long sessions. A classifier infers the real
type from pace/HR/distance/splits and writes it here, alongside -- not over --
the raw tag, mirroring the effort_class precedent. `splits` stores the compact
per-km breakdown used to tell steady tempos from surging intervals.

Revision ID: 016_add_inferred_workout_type
Revises: 015_add_coach_note_cache
Create Date: 2026-05-27
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "016_add_inferred_workout_type"
down_revision: Union[str, Sequence[str], None] = "015_add_coach_note_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("run_logs") as batch_op:
        batch_op.add_column(
            sa.Column("inferred_workout_type", sa.String(length=20), nullable=True)
        )
        batch_op.add_column(
            sa.Column("inferred_type_confidence", sa.Float(), nullable=True)
        )
        batch_op.add_column(sa.Column("splits", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("run_logs") as batch_op:
        batch_op.drop_column("splits")
        batch_op.drop_column("inferred_type_confidence")
        batch_op.drop_column("inferred_workout_type")
