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


class EncryptedString(TypeDecorator):
    """Stores string values encrypted with Fernet.

    Values are encrypted before writing to the database and decrypted
    when read back. Null values pass through unchanged.

    The encryption key is derived from the application's SECRET_KEY.
    """

    impl = String
    cache_ok = True

    def _get_fernet(self) -> Fernet:
        from app.config import settings

        return Fernet(_derive_fernet_key(settings.secret_key))

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
            # Fernet tokens always start with "gAAAAA" (base64url of version
            # byte 0x80).  If the stored value has that prefix, it was
            # encrypted with a different key (SECRET_KEY rotated) — return
            # None so callers trigger a re-authorization flow.
            if value.startswith("gAAAAA"):
                logger.warning(
                    "Failed to decrypt token (likely SECRET_KEY change) "
                    "— returning None. User will need to re-authenticate."
                )
                return None
            # Otherwise it's a legacy plaintext value written before
            # encryption was enabled.  Return it as-is; it will be
            # re-encrypted on the next write via process_bind_param.
            logger.info(
                "Found legacy plaintext token — returning as-is. "
                "It will be re-encrypted on the next write."
            )
            return value
