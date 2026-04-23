"""Encrypt plaintext Strava tokens before EncryptedString hardening.

Before this migration, EncryptedString returned plaintext values as-is when
they didn't look like Fernet tokens. After the hardening change, it returns
None — which would disconnect all users with plaintext tokens.

This migration finds any plaintext tokens and re-encrypts them in-place.
"""

import logging

from alembic import op
import sqlalchemy as sa

revision = "003_encrypt_plaintext_tokens"
down_revision = "002_add_adaptation_history"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a 32-byte Fernet key from an arbitrary-length secret string."""
    import base64
    import hashlib
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet():
    """Create a Fernet instance using the app's encryption key."""
    from cryptography.fernet import Fernet
    from app.config import settings
    key_source = settings.encryption_key if settings.encryption_key else settings.secret_key
    return Fernet(_derive_fernet_key(key_source))


def upgrade() -> None:
    """Encrypt any plaintext Strava tokens in the users table."""
    conn = op.get_bind()
    fernet = _get_fernet()

    users = sa.Table(
        "users",
        sa.MetaData(),
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("strava_access_token", sa.String, nullable=True),
        sa.Column("strava_refresh_token", sa.String, nullable=True),
    )

    updated = 0
    for row in conn.execute(sa.select(users)).fetchall():
        needs_update = False
        update_values = {}

        access_token = row.strava_access_token
        if access_token and not access_token.startswith("gAAAAA"):
            update_values["strava_access_token"] = fernet.encrypt(access_token.encode()).decode()
            needs_update = True

        refresh_token = row.strava_refresh_token
        if refresh_token and not refresh_token.startswith("gAAAAA"):
            update_values["strava_refresh_token"] = fernet.encrypt(refresh_token.encode()).decode()
            needs_update = True

        if needs_update:
            conn.execute(
                sa.update(users)
                .where(users.c.id == row.id)
                .values(**update_values)
            )
            updated += 1

    if updated:
        logger.info("Encrypted plaintext tokens for %d user(s)", updated)
    else:
        logger.info("No plaintext tokens found — all tokens already encrypted")


def downgrade() -> None:
    """Cannot safely reverse encryption — tokens would be exposed as plaintext."""
    logger.warning("Downgrade is a no-op: encrypted tokens cannot be safely reverted")
    pass
