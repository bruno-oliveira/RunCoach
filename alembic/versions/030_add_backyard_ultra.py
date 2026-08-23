"""Store what a backyard runner actually signed up for.

A backyard ultra goal is a yardage — "24 hourly loops" — not a distance. The
plan engine periodises against the ultra that goal projects onto, which is
what ``target_distance`` / ``target_elevation_gain_m`` already hold, but that
projection is *clamped* (a 40-yard goal is 268 km; the engine's ceiling is
163) and so it does not round-trip back to a yardage.

Without these columns a stored backyard plan would be indistinguishable from
an ordinary 161 km trail plan the moment it left the request that created it:
no way to label it, no way to recompute the loop pace or the rest budget, and
no way to rebuild the simulation ladder on a regenerate.

Revision ID: 030_add_backyard_ultra
Revises: 029_retire_strava
Create Date: 2026-08-23
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "030_add_backyard_ultra"
down_revision: Union[str, Sequence[str], None] = "029_retire_strava"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch:
        batch.add_column(
            sa.Column(
                "is_backyard",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(sa.Column("backyard_target_loops", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("backyard_loop_km", sa.Float(), nullable=True))
        batch.add_column(
            sa.Column("backyard_loop_elevation_gain_m", sa.Float(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch:
        batch.drop_column("backyard_loop_elevation_gain_m")
        batch.drop_column("backyard_loop_km")
        batch.drop_column("backyard_target_loops")
        batch.drop_column("is_backyard")
