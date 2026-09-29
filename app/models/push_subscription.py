"""A browser that agreed to receive RunCoach's push notifications.

One row per device (the push service's ``endpoint`` URL is unique per browser
install), so a runner with a phone and a laptop has two. The endpoint is a
capability URL — anyone holding it can wake that browser — and ``auth`` is the
shared secret the payload is encrypted against, so both stay out of logs and
``auth`` is encrypted at rest like the OAuth tokens.

``failure_count`` exists because push services report a dead subscription in
two ways: an explicit 404/410 (delete at once) and repeated transient failures
(give up after a few rather than retrying a phone that was wiped months ago).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time_utils import utcnow_naive
from app.models.base import Base
from app.models.encrypted_type import EncryptedString

if TYPE_CHECKING:
    from app.models.user import User


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    # The browser's P-256 public key (base64url) — public by definition.
    p256dh: Mapped[str] = mapped_column(String)
    auth: Mapped[str] = mapped_column(EncryptedString())
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow_naive)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship("User", back_populates="push_subscriptions")
