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
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, relationship

from app.models.base import Base
from app.models.encrypted_type import EncryptedString


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint = Column(Text, nullable=False, unique=True)
    # The browser's P-256 public key (base64url) — public by definition.
    p256dh = Column(String, nullable=False)
    auth = Column(EncryptedString(), nullable=False)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    last_success_at = Column(DateTime, nullable=True)
    failure_count = Column(Integer, nullable=False, default=0)

    user: Mapped["User"] = relationship("User", back_populates="push_subscriptions")
