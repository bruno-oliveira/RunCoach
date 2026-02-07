"""Authentication service for Google OAuth."""

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User
from app.schemas import UserCreate

logger = logging.getLogger(__name__)


class AuthService:
    _cert_cache: Optional[dict] = None
    _cert_cache_time: Optional[datetime] = None
    _cert_cache_ttl = timedelta(hours=1)

    def __init__(self):
        self.secret_key = settings.secret_key if hasattr(settings, 'secret_key') else "dev-secret-key-change-in-production"
        self.algorithm = "HS256"
        self.google_cert_url = "https://www.googleapis.com/oauth2/v3/certs"

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=1)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError:
            return None

    async def _get_google_certs(self) -> dict:
        """Get Google's public keys with 1-hour cache."""
        now = datetime.utcnow()

        if (self._cert_cache and self._cert_cache_time and
            now - self._cert_cache_time < self._cert_cache_ttl):
            logger.info("Using cached Google OAuth certificates")
            return self._cert_cache

        logger.info("Fetching Google OAuth certificates")
        async with httpx.AsyncClient() as client:
            response = await client.get(self.google_cert_url)
            response.raise_for_status()
            certs = response.json()
            AuthService._cert_cache = certs
            AuthService._cert_cache_time = now
            logger.info(f"Retrieved {len(certs.get('keys', []))} public keys from Google")
            return certs

    async def verify_google_token(self, id_token: str) -> Optional[dict]:
        """Verify Google ID token using Google's public keys."""
        try:
            logger.info(f"Attempting to verify Google token...")

            certs = await self._get_google_certs()

            # First, try to decode without issuer/audience validation to see what's in the token
            try:
                unverified_payload = jwt.decode(
                    id_token,
                    certs,
                    algorithms=["RS256"],
                    options={"verify_signature": False}
                )
                logger.info(f"Token issuer: {unverified_payload.get('iss')}")
                logger.info(f"Token audience: {unverified_payload.get('aud')}")
                logger.info(f"Expected audience: {settings.google_client_id if hasattr(settings, 'google_client_id') else 'NOT SET'}")
            except Exception as e:
                logger.error(f"Failed to decode unverified token: {e}")

            # Verify the token with proper validation
            try:
                payload = jwt.decode(
                    id_token,
                    certs,
                    algorithms=["RS256"],
                    audience=settings.google_client_id if hasattr(settings, 'google_client_id') else None,
                    issuer="https://accounts.google.com"
                )
                logger.info(f"Google token verified successfully for: {payload.get('email')}")
                return payload
            except JWTError as e:
                logger.error(f"JWT verification failed: {type(e).__name__}: {e}")
                logger.error(f"Google Client ID configured: {settings.google_client_id if hasattr(settings, 'google_client_id') else 'NOT SET'}")
                return None

        except Exception as e:
            logger.error(f"Google token verification error: {type(e).__name__}: {e}")
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

        user = db.query(User).filter(User.google_id == google_id).first()

        if not user:
            user = db.query(User).filter(User.email == email).first()

            if user:
                user.google_id = google_id
                user.name = name
                user.picture = picture
            else:
                user = User(
                    google_id=google_id,
                    email=email,
                    name=name,
                    picture=picture
                )
                db.add(user)

            db.commit()
            db.refresh(user)

        if anonymous_user_id and anonymous_user_id != user.id:
            from app.services.merge_service import MergeService
            MergeService.merge_anonymous_user(db, anonymous_user_id, user.id)

        user.last_activity = datetime.utcnow()
        db.commit()

        return user

    def get_current_user(self, db: Session, user_id: str) -> Optional[User]:
        """Get user by ID from token."""
        return db.query(User).filter(User.id == user_id).first()

    def update_user_activity(self, db: Session, user: User) -> None:
        """Update user's last activity timestamp."""
        user.last_activity = datetime.utcnow()
        db.commit()
