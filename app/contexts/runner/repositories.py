"""SQLAlchemy implementation of IRunRepository for the runner context."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import RunLog


class SQLAlchemyRunRepository:
    """Persistence adapter for ``RunLog``.

    Wraps SQLAlchemy ``Session`` operations behind the ``IRunRepository``
    protocol. Complex filter chains (workout type, date windows, training
    plan scope) stay in the calling services for now — the repo covers the
    common identity/list lookups.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, run_id: int) -> Optional[RunLog]:
        return self.session.query(RunLog).filter(RunLog.id == run_id).first()

    def get_for_user(self, run_id: int, user_id: str) -> Optional[RunLog]:
        return (
            self.session.query(RunLog)
            .filter(RunLog.id == run_id, RunLog.user_id == user_id)
            .first()
        )

    def list_by_user(self, user_id: str) -> List[RunLog]:
        return self.session.query(RunLog).filter(RunLog.user_id == user_id).all()

    def list_recent_for_user(
        self,
        user_id: str,
        *,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[RunLog]:
        q = (
            self.session.query(RunLog)
            .filter(RunLog.user_id == user_id)
            .order_by(RunLog.date.desc())
        )
        if since is not None:
            q = q.filter(RunLog.date >= since)
        if limit is not None:
            q = q.limit(limit)
        return q.all()

    def save(self, run: RunLog) -> None:
        self.session.add(run)

    def delete(self, run: RunLog) -> None:
        self.session.delete(run)


__all__ = ["SQLAlchemyRunRepository"]
