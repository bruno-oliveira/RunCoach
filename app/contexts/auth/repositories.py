"""SQLAlchemy implementation of IUserRepository for the auth context."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import User


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


__all__ = ["SQLAlchemyUserRepository"]
