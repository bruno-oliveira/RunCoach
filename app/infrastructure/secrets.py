"""Startup validation for production secrets."""

import logging
import os

from app.infrastructure.config import settings

logger = logging.getLogger(__name__)


def validate_production_secrets() -> None:
    """Validate that required secrets are properly configured."""
    if not os.environ.get("SECRET_KEY"):
        logger.warning(
            "SECRET_KEY not set via environment variable — using random default. "
            "JWTs will be invalidated on every restart. "
            "Set SECRET_KEY as a persistent secret (e.g. `fly secrets set SECRET_KEY=...`)."
        )
    if not settings.debug:
        weak_patterns = [
            "dev-secret",
            "your-secret",
            "change-in-production",
            "placeholder",
        ]
        key = settings.secret_key
        if len(key) < 32 or any(p in key.lower() for p in weak_patterns):
            raise RuntimeError(
                "SECRET_KEY is too weak for production. "
                "Set a random key of at least 32 characters."
            )
        if not settings.encryption_key:
            raise RuntimeError(
                "ENCRYPTION_KEY is required in production. "
                "Set a separate key from SECRET_KEY (e.g. `fly secrets set ENCRYPTION_KEY=...`) "
                "so a JWT-key compromise does not expose data-at-rest."
            )
        if len(settings.encryption_key) < 32:
            raise RuntimeError(
                "ENCRYPTION_KEY is too weak. Use at least 32 characters of random entropy."
            )
        if settings.encryption_key == settings.secret_key:
            raise RuntimeError(
                "ENCRYPTION_KEY must differ from SECRET_KEY. "
                "Reusing the JWT secret for data encryption breaks defense-in-depth."
            )
    elif not settings.encryption_key:
        logger.warning(
            "ENCRYPTION_KEY not set — falling back to SECRET_KEY for data encryption. "
            "This is allowed in debug mode only. Set a separate ENCRYPTION_KEY for production."
        )
