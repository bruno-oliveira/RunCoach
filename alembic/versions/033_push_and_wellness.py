"""Push notifications, the watch's overnight wellness, and what we've sent.

Three things the live loop needs to store:

* ``push_subscriptions`` — one row per browser that granted push permission.
* ``wellness_days`` — HRV / resting HR / sleep imported from Intervals.icu, so
  readiness no longer depends on the runner typing it in.
* ``notification_log`` — the (user, kind, key) ledger that makes every push
  idempotent across retried webhooks and double-fired crons.

Plus three columns: ``users.intervals_scopes`` (what the OAuth grant covers, so
wellness can be skipped rather than 403'd for pre-wellness connections),
``users.notification_prefs`` (per-category push opt-outs), and
``readiness_logs.source`` (a check-in the runner filled vs one derived from
their watch). Existing readiness rows are all genuine check-ins, hence the
server default.

Revision ID: 033_push_and_wellness
Revises: 032_add_user_timezone
Create Date: 2026-09-24
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "033_push_and_wellness"
down_revision: Union[str, Sequence[str], None] = "032_add_user_timezone"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.String(), nullable=False),
        sa.Column("auth", sa.String(), nullable=False),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column(
            "failure_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.create_index(
        "ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"]
    )

    op.create_table(
        "wellness_days",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hrv", sa.Float(), nullable=True),
        sa.Column("resting_hr", sa.Integer(), nullable=True),
        sa.Column("sleep_hours", sa.Float(), nullable=True),
        sa.Column("sleep_score", sa.Float(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default="intervals",
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "date", name="uq_wellness_user_date"),
    )
    op.create_index("ix_wellness_days_user_id", "wellness_days", ["user_id"])

    op.create_table(
        "notification_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "kind", "key", name="uq_notification_once"),
    )
    op.create_index("ix_notification_log_user_id", "notification_log", ["user_id"])

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("intervals_scopes", sa.String(), nullable=True))
        batch.add_column(sa.Column("notification_prefs", sa.JSON(), nullable=True))

    with op.batch_alter_table("readiness_logs") as batch:
        batch.add_column(
            sa.Column(
                "source",
                sa.String(length=20),
                nullable=False,
                server_default="checkin",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("readiness_logs") as batch:
        batch.drop_column("source")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("notification_prefs")
        batch.drop_column("intervals_scopes")
    op.drop_index("ix_notification_log_user_id", table_name="notification_log")
    op.drop_table("notification_log")
    op.drop_index("ix_wellness_days_user_id", table_name="wellness_days")
    op.drop_table("wellness_days")
    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
