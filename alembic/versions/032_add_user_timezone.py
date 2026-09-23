"""Remember each runner's timezone for the scheduled jobs.

Requests bind the browser's IANA zone per call, but the daily sync and the
nudge sweep run with no browser attached, so "today" in the adaptive engine
and the nudge guards was UTC's today — a day off for much of the world around
midnight. Nullable: a runner who hasn't visited since this shipped keeps the
UTC fallback until their next page load records their zone.

Revision ID: 032_add_user_timezone
Revises: 031_add_frequency_composer
Create Date: 2026-09-23
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "032_add_user_timezone"
down_revision: Union[str, Sequence[str], None] = "031_add_frequency_composer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("timezone", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("timezone")
