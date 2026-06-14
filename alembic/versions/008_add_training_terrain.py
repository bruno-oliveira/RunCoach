"""Add training_terrain to training_plans.

Revision ID: 008_add_training_terrain
Revises: 007_add_trail_profile
Create Date: 2026-05-09
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "008_add_training_terrain"
down_revision: Union[str, Sequence[str], None] = "007_add_trail_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.add_column(sa.Column("training_terrain", sa.String(), nullable=True))

    # Backfill existing trail plans so plan dedupe and rendering stay stable
    # after rollout. Derive terrain class from race vertical density when
    # possible; otherwise default to hilly (legacy trail baseline).
    op.execute(
        sa.text(
            """
            UPDATE training_plans
               SET training_terrain = CASE
                   WHEN is_trail = 1
                        AND target_elevation_gain_m IS NOT NULL
                        AND CAST(target_distance AS FLOAT) > 0
                   THEN CASE
                       WHEN (target_elevation_gain_m / CAST(target_distance AS FLOAT)) < 10 THEN 'flat'
                       WHEN (target_elevation_gain_m / CAST(target_distance AS FLOAT)) < 25 THEN 'rolling'
                       WHEN (target_elevation_gain_m / CAST(target_distance AS FLOAT)) < 50 THEN 'hilly'
                       ELSE 'mountainous'
                   END
                   WHEN is_trail = 1 THEN 'hilly'
                   ELSE training_terrain
               END
             WHERE training_terrain IS NULL
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.drop_column("training_terrain")
