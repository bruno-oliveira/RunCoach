"""Remember which calendar event a run was recorded against.

Intervals.icu pairs an activity with the planned calendar event it was run
from. Storing both ends — the event id a single run was pushed as, and the
event id an imported activity came back paired with — lets the claim join them
exactly instead of guessing from day and distance.

Both are plain nullable strings: Intervals event ids are theirs, not ours, and
neither column is a key into any table here.

Revision ID: 036_add_watch_event_pairing
Revises: 035_add_single_runs
Create Date: 2026-10-02
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "036_add_watch_event_pairing"
down_revision: Union[str, Sequence[str], None] = "035_add_single_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("single_runs") as batch:
        batch.add_column(sa.Column("watch_event_id", sa.String(), nullable=True))
    with op.batch_alter_table("run_logs") as batch:
        batch.add_column(
            sa.Column("intervals_paired_event_id", sa.String(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("run_logs") as batch:
        batch.drop_column("intervals_paired_event_id")
    with op.batch_alter_table("single_runs") as batch:
        batch.drop_column("watch_event_id")
