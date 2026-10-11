"""Remember which language a runner reads the app in.

The language toggle lives in the browser, so the server only ever knew it for
the length of a request — and not at all for the text it writes when no browser
is there: the coaching email, a push notification, the workout names mirrored
onto the watch. Those went out in English to a runner whose whole app was in
Portuguese. Stored on the user row for the same reason ``timezone`` is.

Nullable, with no backfill: NULL means English, which is what every runner has
been getting.

Revision ID: 039_add_user_language
Revises: 038_add_plan_recovery_dismissed_at
Create Date: 2026-10-11
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "039_add_user_language"
down_revision: Union[str, Sequence[str], None] = "038_add_plan_recovery_dismissed_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("language", sa.String(length=8), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("language")
