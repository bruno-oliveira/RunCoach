"""Recompute inferred_workout_type against the fixed HR zones.

The inferred workout type is classified partly from the runner's HR zones, and
those zones were previously anchored on a circular LTHR estimate (the median HR
of runs *labelled* tempo -- a label derived from the very zones being built).
That collapsed Zone 2, so easy runs were mislabelled as tempo/hard and their
inferred_workout_type is wrong.

Null the column so the startup backfill (``backfill_inferred_workout_types``,
which fills NULLs and is already wrapped in try/except) recomputes every run
against the corrected, non-circular zones on next boot. Alembic runs this once.

Revision ID: 025_recompute_inferred_workout_type
Revises: 024_add_intervals_hr_settings
Create Date: 2026-07-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "025_recompute_inferred_workout_type"
down_revision: Union[str, Sequence[str], None] = "024_add_intervals_hr_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE run_logs "
        "SET inferred_workout_type = NULL, inferred_type_confidence = NULL"
    )


def downgrade() -> None:
    # Data-only recompute; nothing to reverse (the values are re-derived).
    pass
