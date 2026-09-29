"""What we have already told a runner — the idempotency ledger for pushes.

Every proactive message has a natural key: the morning brief is once per local
day, the week review once per plan-week, a run note once per activity. Writing
``(user, kind, key)`` under a unique constraint *before* sending means a
retried webhook, a double-fired cron, or two requests racing can never make a
phone buzz twice for the same thing.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time_utils import utcnow_naive
from app.models.base import Base


class NotificationLog(Base):
    __tablename__ = "notification_log"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "key", name="uq_notification_once"),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(120))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow_naive)
