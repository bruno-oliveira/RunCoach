"""What we have already told a runner — the idempotency ledger for pushes.

Every proactive message has a natural key: the morning brief is once per local
day, the week review once per plan-week, a run note once per activity. Writing
``(user, kind, key)`` under a unique constraint *before* sending means a
retried webhook, a double-fired cron, or two requests racing can never make a
phone buzz twice for the same thing.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint

from app.models.base import Base


class NotificationLog(Base):
    __tablename__ = "notification_log"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "key", name="uq_notification_once"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = Column(String(40), nullable=False)
    key = Column(String(120), nullable=False)
    sent_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
