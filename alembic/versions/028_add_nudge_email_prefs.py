"""Give the coach a way to reach a runner who hasn't opened the app.

Three columns on ``users``:

* ``nudge_email_enabled`` — the consent. Defaults to **false**, including for
  every existing row: these people signed up for a plan generator, not a
  mailing list, and backfilling them to true would email the entire user table
  on the first cron run.
* ``last_nudge_email_at`` — the rate limit. One email per
  ``settings.nudge_min_interval_days``, enforced here rather than in memory so
  it survives a restart and holds across however many machines run the job.
* ``last_nudge_email_signature`` — the repeat guard. The same situation
  restated in the same words is nagging; the signature changes only when the
  situation materially does.

Revision ID: 028_add_nudge_email_prefs
Revises: 027_add_plan_watch_sync_state
Create Date: 2026-07-26
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "028_add_nudge_email_prefs"
down_revision: Union[str, Sequence[str], None] = "027_add_plan_watch_sync_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "nudge_email_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column("last_nudge_email_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_nudge_email_signature", sa.String(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("last_nudge_email_signature")
        batch_op.drop_column("last_nudge_email_at")
        batch_op.drop_column("nudge_email_enabled")
