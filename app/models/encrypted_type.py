"""SQLAlchemy custom type for transparent Fernet encryption at rest."""

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a 32-byte Fernet key from an arbitrary-length secret string."""
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _get_encryption_secret() -> str:
    """Return the encryption key source, preferring ENCRYPTION_KEY over SECRET_KEY."""
    from app.config import settings
    return settings.encryption_key if settings.encryption_key else settings.secret_key


class EncryptedString(TypeDecorator):
    """Stores string values encrypted with Fernet.

    Values are encrypted before writing to the database and decrypted
    when read back. Null values pass through unchanged.

    Uses ENCRYPTION_KEY if set, otherwise falls back to SECRET_KEY.
    """

    impl = String
    cache_ok = True

    def _get_fernet(self) -> Fernet:
        return Fernet(_derive_fernet_key(_get_encryption_secret()))

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        return self._get_fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        try:
            return self._get_fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            logger.warning(
                "Failed to decrypt token — returning None. "
                "User will need to re-authenticate."
            )
            return None
