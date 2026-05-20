"""Authentication service for Google OAuth."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import httpx
import jwt as pyjwt
from jwt import PyJWKSet
from jwt.exceptions import PyJWTError
from sqlalchemy.orm import Session

from app.contexts.auth.repositories import SQLAlchemyUserRepository
from app.domain.repositories import IUserRepository
from app.infrastructure.config import settings
from app.models import User
from app.models.refresh_token import RefreshToken, _generate_raw_token, hash_token
from app.schemas import UserCreate

logger = logging.getLogger(__name__)


class AuthService:
    _cert_cache_entry: Optional[tuple[dict, datetime]] = None  # (certs, fetched_at)
    _cert_cache_ttl = timedelta(hours=1)

    def __init__(
        self,
        user_repo_factory: Callable[[Session], IUserRepository] = SQLAlchemyUserRepository,
    ):
        self.secret_key = settings.secret_key
        self.algorithm = "HS256"
        self.google_cert_url = "https://www.googleapis.com/oauth2/v3/certs"
        self._user_repo_factory = user_repo_factory

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc).replace(tzinfo=None) + expires_delta
        else:
            expire = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
        to_encode.update({
            "exp": expire,
            "iat": datetime.now(timezone.utc).replace(tzinfo=None),
        })
        return pyjwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[dict]:
        try:
            return pyjwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except PyJWTError:
            return None

    def issue_refresh_token(self, db: Session, user: User) -> tuple[str, datetime]:
        """Mint a new refresh token for ``user`` and return (raw_token, expires_at).

        Stores only the SHA-256 hash server-side; the raw value is given to
        the client and never logged.
        """
        raw = _generate_raw_token()
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
            days=settings.refresh_token_days
        )
        token = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=expires_at,
        )
        db.add(token)
        db.commit()
        return raw, expires_at

    def consume_refresh_token(self, db: Session, raw_token: str) -> Optional[User]:
        """Validate a refresh token and return the owning user.

        Rotation: marks the presented token as revoked and is expected to be
        followed by ``issue_refresh_token`` so the client gets a fresh value.
        """
        token_hash = hash_token(raw_token)
        token = (
            db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .one_or_none()
        )
        if token is None:
            return None
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if token.revoked_at is not None or token.expires_at <= now:
            return None
        token.revoked_at = now
        db.commit()
        return self._user_repo_factory(db).get_by_id(token.user_id)

    def revoke_refresh_token(self, db: Session, raw_token: str) -> None:
        """Mark a refresh token as revoked. No-op if not found."""
        token_hash = hash_token(raw_token)
        token = (
            db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .one_or_none()
        )
        if token is None or token.revoked_at is not None:
            return
        token.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()

    async def _get_google_certs(self) -> dict:
        """Get Google's public keys with 1-hour cache."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        entry = self._cert_cache_entry  # single atomic read
        if entry is not None and (now - entry[1]) < self._cert_cache_ttl:
            logger.info("Using cached Google OAuth certificates")
            return entry[0]

        logger.info("Fetching Google OAuth certificates")
        async with httpx.AsyncClient() as client:
            response = await client.get(self.google_cert_url)
            response.raise_for_status()
            certs = response.json()
            AuthService._cert_cache_entry = (certs, now)  # single atomic write
            logger.info(f"Retrieved {len(certs.get('keys', []))} public keys from Google")
            return certs

    async def verify_google_token(self, id_token: str) -> Optional[dict]:
        """Verify Google ID token using Google's public keys."""
        try:
            if not settings.google_client_id:
                logger.error("Google client ID is not configured — refusing to verify token without audience validation")
                return None

            certs = await self._get_google_certs()
            jwk_set = PyJWKSet.from_dict(certs)

            header = pyjwt.get_unverified_header(id_token)
            kid = header.get("kid")
            signing_key = next(
                (k.key for k in jwk_set.keys if k.key_id == kid),
                None,
            )
            if signing_key is None:
                logger.error("No matching Google public key for kid: %s", kid)
                return None

            payload = pyjwt.decode(
                id_token,
                signing_key,
                algorithms=["RS256"],
                audience=settings.google_client_id,
                issuer=["https://accounts.google.com", "accounts.google.com"],
            )
            logger.debug("Google token verified successfully for sub: %s", payload.get("sub"))
            return payload
        except PyJWTError as e:
            logger.error("JWT verification failed: %s: %s", type(e).__name__, e)
            return None
        except Exception as e:
            logger.error("Google token verification error: %s: %s", type(e).__name__, e)
            return None

    def get_or_create_user(self, db: Session, google_user_data: dict, anonymous_user_id: Optional[str] = None) -> User:
        """Get existing user or create new one from Google data.

        Args:
            db: Database session
            google_user_data: Google OAuth user data
            anonymous_user_id: Optional anonymous user ID to merge from
        """
        google_id = google_user_data.get("sub")
        email = google_user_data.get("email")
        name = google_user_data.get("name")
        picture = google_user_data.get("picture")

        users = self._user_repo_factory(db)
        user = users.get_by_google_id(google_id)

        if not user:
            user = users.get_by_email(email)

            if user:
                user.google_id = google_id
                user.name = name
                user.picture = picture
            else:
                user = User(
                    google_id=google_id,
                    email=email,
                    name=name,
                    picture=picture,
                    auto_adjust_enabled=True,
                )
                db.add(user)

            db.commit()
            db.refresh(user)

        if anonymous_user_id and anonymous_user_id != user.id:
            from app.contexts.plan.merge_service import MergeService
            MergeService.merge_anonymous_user(db, anonymous_user_id, user.id)

        user.last_activity = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()

        return user

    def get_current_user(self, db: Session, user_id: str) -> Optional[User]:
        """Get user by ID from token."""
        return self._user_repo_factory(db).get_by_id(user_id)

    def update_user_activity(self, db: Session, user: User) -> None:
        """Update user's last activity timestamp (throttled to once per 5 minutes)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if user.last_activity:
            last = user.last_activity
            if last.tzinfo is not None:
                last = last.replace(tzinfo=None)
            if (now - last) < timedelta(minutes=5):
                return
        user.last_activity = now
        db.commit()
