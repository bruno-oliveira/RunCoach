"""Add is_trail and target_elevation_gain_m to training_plans.

Backfills existing plans whose target_distance is the legacy ``"30.0"`` /
``"trail"`` value so they remain valid trail plans under the new schema:

* ``is_trail`` becomes True
* ``target_elevation_gain_m`` defaults to 1000 m (≈33 m/km, the historic
  "hilly" baseline) — phase 1 of this redesign verified that 33 m/km lands
  cleanly in the ``hilly`` elevation class, matching the moderate hill
  emphasis the legacy Trail phase distribution prescribed.

Revision ID: 007_add_trail_profile
Revises: 006_drop_triathlon_plans
Create Date: 2026-05-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "007_add_trail_profile"
down_revision: Union[str, Sequence[str], None] = "006_drop_triathlon_plans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LEGACY_TRAIL_DEFAULT_ELEVATION_M = 1000.0


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_trail",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column("target_elevation_gain_m", sa.Float(), nullable=True)
        )

    # Backfill legacy trail plans. target_distance is stored as a string and
    # may be either "30.0" or the legacy "trail" placeholder.
    op.execute(
        sa.text(
            """
            UPDATE training_plans
               SET is_trail = :is_trail,
                   target_elevation_gain_m = :default_elev
             WHERE target_distance IN ('30.0', '30', 'trail')
               AND is_trail = :was_false
            """
        ).bindparams(
            is_trail=True,
            default_elev=_LEGACY_TRAIL_DEFAULT_ELEVATION_M,
            was_false=False,
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.drop_column("target_elevation_gain_m")
        batch_op.drop_column("is_trail")
