"""SQLAlchemy implementation of IReadinessRepository."""

from __future__ import annotations

from datetime import date as date_cls
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import ReadinessLog


class SQLAlchemyReadinessRepository:
    """Persistence adapter for daily readiness check-ins (``ReadinessLog``)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_user_on(
        self, user_id: str, on_date: date_cls
    ) -> Optional[ReadinessLog]:
        return (
            self.session.query(ReadinessLog)
            .filter(
                ReadinessLog.user_id == user_id,
                ReadinessLog.date == on_date,
            )
            .first()
        )

    def list_recent_for_user(
        self,
        user_id: str,
        *,
        since: Optional[date_cls] = None,
        limit: Optional[int] = None,
    ) -> List[ReadinessLog]:
        q = (
            self.session.query(ReadinessLog)
            .filter(ReadinessLog.user_id == user_id)
            .order_by(ReadinessLog.date.desc())
        )
        if since is not None:
            q = q.filter(ReadinessLog.date >= since)
        if limit is not None:
            q = q.limit(limit)
        return q.all()

    def save(self, log: ReadinessLog) -> None:
        self.session.add(log)
        self.session.commit()
        self.session.refresh(log)
