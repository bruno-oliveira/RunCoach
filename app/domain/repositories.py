"""Repository interfaces for persistence-agnostic data access.

Defined in the domain layer so application code can depend on these protocols
rather than concrete SQLAlchemy implementations. Concrete implementations live
in the infrastructure layer (introduced incrementally; not yet implemented).

The TYPE_CHECKING guard keeps this module free of ORM imports at runtime —
the protocols remain importable from anywhere in the codebase, including pure
core modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Protocol

if TYPE_CHECKING:
    from app.models.run_log import RunLog
    from app.models.training_plan import TrainingPlan


class IPlanRepository(Protocol):
    """Persistence interface for training plans."""

    def get_by_id(
        self, plan_id: str, *, include_weeks: bool = False
    ) -> Optional["TrainingPlan"]: ...

    def list_by_user(
        self, user_id: str, *, active_only: bool = True
    ) -> List["TrainingPlan"]: ...

    def save(self, plan: "TrainingPlan") -> None: ...

    def delete(self, plan: "TrainingPlan") -> None: ...


class IRunRepository(Protocol):
    """Persistence interface for logged runs."""

    def get_recent(self, user_id: str, weeks: int) -> List["RunLog"]: ...

    def list_by_user(self, user_id: str) -> List["RunLog"]: ...

    def save(self, run: "RunLog") -> None: ...

    def delete(self, run: "RunLog") -> None: ...
