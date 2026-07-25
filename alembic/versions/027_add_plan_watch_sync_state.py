"""Turn send-to-watch from an export into a subscription.

``watch_synced_at`` conflated two things: "the runner wants this plan mirrored"
and "here is when we last mirrored it". Splitting them lets the mirror become a
reconciler:

* ``watch_sync_enabled`` is the authorisation — the runner opted in, so we may
  create *and delete* events on their calendar. ``watch_synced_at`` keeps its
  second meaning only (the timestamp shown in the status line).
* ``watch_event_hashes`` maps each pushed ``external_id`` to a hash of the event
  body we last sent. It makes re-mirroring idempotent (only genuinely changed
  days are rewritten) and it is the record of which events on the calendar are
  ours — which is what makes deleting a removed day safe.

Existing plans with a ``watch_synced_at`` are opted in, because they already get
re-pushed on every adaptation today. Leaving them off would silently withdraw a
feature they are relying on.

Revision ID: 027_add_plan_watch_sync_state
Revises: 026_add_plan_watch_synced_at
Create Date: 2026-07-25
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "027_add_plan_watch_sync_state"
down_revision: Union[str, Sequence[str], None] = "026_add_plan_watch_synced_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.add_column(
            sa.Column(
                "watch_sync_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(sa.Column("watch_event_hashes", sa.JSON(), nullable=True))
        # The mirror runs as a background task, so a failure has no response to
        # ride back on. Persisting the kind is what lets the plan page say
        # "reconnect" instead of leaving a 401 in the log and a stale watch.
        batch_op.add_column(
            sa.Column("watch_sync_error", sa.String(), nullable=True)
        )

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("watch_setup_confirmed_at", sa.DateTime(), nullable=True)
        )

    # Preserve the behaviour these runners already have: a plan that has ever
    # been pushed is a plan we currently re-push on every change.
    op.execute(
        "UPDATE training_plans SET watch_sync_enabled = 1 "
        "WHERE watch_synced_at IS NOT NULL"
    )
    # Anyone who has already sent a workout has been through the setup, whether
    # or not a wizard existed at the time. Making them click through one now
    # would be a regression dressed up as onboarding.
    op.execute(
        "UPDATE users SET watch_setup_confirmed_at = CURRENT_TIMESTAMP "
        "WHERE id IN (SELECT DISTINCT user_id FROM training_plans "
        "WHERE watch_synced_at IS NOT NULL)"
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("watch_setup_confirmed_at")

    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.drop_column("watch_sync_error")
        batch_op.drop_column("watch_event_hashes")
        batch_op.drop_column("watch_sync_enabled")
