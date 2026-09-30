"""SQLAlchemy repositories for the auth context: runners and their devices."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import PushSubscription, User


class SQLAlchemyUserRepository:
    """Persistence adapter for ``User``.

    Wraps SQLAlchemy ``Session`` operations behind the ``IUserRepository``
    protocol so the auth context doesn't depend on SQLAlchemy directly.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, user_id: str) -> Optional[User]:
        return self.session.query(User).filter(User.id == user_id).first()

    def get_by_google_id(self, google_id: str) -> Optional[User]:
        return self.session.query(User).filter(User.google_id == google_id).first()

    def get_by_email(self, email: str) -> Optional[User]:
        return self.session.query(User).filter(User.email == email).first()

    def save(self, user: User) -> None:
        self.session.add(user)


class SQLAlchemyPushSubscriptionRepository:
    """Persistence adapter for ``PushSubscription`` — one row per browser.

    A subscription is keyed by its push-service ``endpoint``, not by runner:
    the same device can be re-homed to whoever signs in on it next.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_user(self, user_id: str) -> List[PushSubscription]:
        return (
            self.session.query(PushSubscription)
            .filter(PushSubscription.user_id == user_id)
            .all()
        )

    def count_for_user(self, user_id: str) -> int:
        return (
            self.session.query(PushSubscription.id)
            .filter(PushSubscription.user_id == user_id)
            .count()
        )

    def get_by_endpoint(self, endpoint: str) -> Optional[PushSubscription]:
        return (
            self.session.query(PushSubscription)
            .filter(PushSubscription.endpoint == endpoint)
            .first()
        )

    def delete_for_user(self, endpoint: str, user_id: str) -> int:
        """Forget ``endpoint`` only if it belongs to ``user_id``."""
        return (
            self.session.query(PushSubscription)
            .filter(
                PushSubscription.endpoint == endpoint,
                PushSubscription.user_id == user_id,
            )
            .delete(synchronize_session=False)
        )

    def save(self, subscription: PushSubscription) -> None:
        self.session.add(subscription)


__all__ = ["SQLAlchemyPushSubscriptionRepository", "SQLAlchemyUserRepository"]
