"""Persist the frequency composer that shaped each plan.

The adaptive engine needs to know which ``FrequencyComposer`` built a plan so
it can load the matching ``AdaptationPolicy`` (long-run share limits, quality
caps, protected slots) before adjusting future weeks.  Without this column the
policy would have to be re-derived from the workout count in week 1, which
breaks as soon as adaptation has already modified the plan.

Backfill: derive from ``max_runs_per_week`` — plans generated before the
composer system used the same structural path as the matching composer.

Revision ID: 031_add_frequency_composer
Revises: 030_add_backyard_ultra
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "031_add_frequency_composer"
down_revision: Union[str, Sequence[str], None] = "030_add_backyard_ultra"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COMPOSER_BY_RUNS = {
    2: "two_run",
    3: "three_run",
    4: "four_run",
    5: "five_run",
    6: "six_run",
}


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch:
        batch.add_column(sa.Column("frequency_composer", sa.String(), nullable=True))

    conn = op.get_bind()
    for runs, name in _COMPOSER_BY_RUNS.items():
        conn.execute(
            sa.text(
                "UPDATE training_plans SET frequency_composer = :name "
                "WHERE max_runs_per_week = :runs AND frequency_composer IS NULL"
            ),
            {"name": name, "runs": runs},
        )
    conn.execute(
        sa.text(
            "UPDATE training_plans SET frequency_composer = 'four_run' "
            "WHERE frequency_composer IS NULL"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch:
        batch.drop_column("frequency_composer")
