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
    """Return the data-encryption secret, falling back to SECRET_KEY only in debug.

    In production we require ENCRYPTION_KEY to be set and distinct from SECRET_KEY
    so a leak of the JWT signing key does not expose Strava tokens at rest.
    """
    from app.config import settings
    if settings.encryption_key:
        return settings.encryption_key
    if not settings.debug:
        raise RuntimeError(
            "ENCRYPTION_KEY is required in non-debug mode. "
            "Set a separate key from SECRET_KEY for data-at-rest encryption."
        )
    return settings.secret_key


class EncryptedString(TypeDecorator):
    """Stores string values encrypted with Fernet.

    Values are encrypted before writing to the database and decrypted
    when read back. Null values pass through unchanged.

    Uses ENCRYPTION_KEY. In debug mode only, falls back to SECRET_KEY.
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
