"""SQLAlchemy adapter for ``ReadinessLog`` queries."""

from __future__ import annotations

from datetime import date as date_cls
from datetime import timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import ReadinessLog


class SQLAlchemyReadinessRepository:
    """Persistence adapter for daily readiness check-ins."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_date(self, user_id: str, log_date: date_cls) -> Optional[ReadinessLog]:
        return (
            self.session.query(ReadinessLog)
            .filter(
                ReadinessLog.user_id == user_id,
                ReadinessLog.log_date == log_date,
            )
            .first()
        )

    def get_today(self, user_id: str) -> Optional[ReadinessLog]:
        return self.get_for_date(user_id, date_cls.today())

    def list_recent(self, user_id: str, days: int) -> List[ReadinessLog]:
        cutoff = date_cls.today() - timedelta(days=days - 1)
        return (
            self.session.query(ReadinessLog)
            .filter(
                ReadinessLog.user_id == user_id,
                ReadinessLog.log_date >= cutoff,
            )
            .order_by(ReadinessLog.log_date.desc())
            .all()
        )

    def save(self, log: ReadinessLog) -> None:
        self.session.add(log)


__all__ = ["SQLAlchemyReadinessRepository"]
