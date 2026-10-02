"""SQLAlchemy implementation of ISingleRunRepository."""

from __future__ import annotations

from datetime import date as date_cls
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import RunLog, SingleRun


class SQLAlchemySingleRunRepository:
    """Persistence adapter for one-off workouts (``SingleRun``)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_user(self, single_run_id: str, user_id: str) -> Optional[SingleRun]:
        return (
            self.session.query(SingleRun)
            .filter(SingleRun.id == single_run_id, SingleRun.user_id == user_id)
            .first()
        )

    def list_for_user(
        self,
        user_id: str,
        *,
        since: Optional[date_cls] = None,
        limit: Optional[int] = None,
    ) -> List[SingleRun]:
        q = (
            self.session.query(SingleRun)
            .filter(SingleRun.user_id == user_id)
            .order_by(SingleRun.date.desc(), SingleRun.created_at.desc())
        )
        if since is not None:
            q = q.filter(SingleRun.date >= since)
        if limit is not None:
            q = q.limit(limit)
        return q.all()

    def completed_runs(self, single_run_ids: List[str]) -> dict[str, RunLog]:
        """The logged run that completed each single run, keyed by its id.

        Single runs nobody has run yet are simply absent from the result.
        """
        if not single_run_ids:
            return {}
        runs = (
            self.session.query(RunLog)
            .filter(RunLog.single_run_id.in_(single_run_ids))
            .order_by(RunLog.date.asc())
            .all()
        )
        return {str(run.single_run_id): run for run in runs}

    def save(self, single_run: SingleRun) -> None:
        self.session.add(single_run)

    def delete(self, single_run: SingleRun) -> None:
        """Delete a single run, releasing the logged run that completed it.

        The run itself stays — the runner did run it — and with the pointer
        cleared it becomes an ordinary unplanned run again.
        """
        self.session.query(RunLog).filter(RunLog.single_run_id == single_run.id).update(
            {RunLog.single_run_id: None}, synchronize_session=False
        )
        self.session.delete(single_run)
