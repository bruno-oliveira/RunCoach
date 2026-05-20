"""Refresh token model — server-side revocable JWT refresh tokens."""

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, relationship

from app.models.base import Base


def _generate_raw_token() -> str:
    """Generate a fresh random refresh token (opaque string)."""
    return secrets.token_urlsafe(48)


def hash_token(raw_token: str) -> str:
    """Hash a raw refresh token for database storage."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")
