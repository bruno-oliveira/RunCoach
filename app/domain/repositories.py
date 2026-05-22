"""Repository interfaces for persistence-agnostic data access.

Defined in the domain layer so application code can depend on these protocols
rather than concrete SQLAlchemy implementations. Concrete implementations live
in the contexts/ and infrastructure/ layers.

The TYPE_CHECKING guard keeps this module free of ORM imports at runtime —
the protocols remain importable from anywhere in the codebase, including pure
core modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, Protocol

if TYPE_CHECKING:
    from app.models.favorite_recipe import FavoriteRecipe
    from app.models.run_log import RunLog
    from app.models.training_plan import TrainingPlan
    from app.models.user import User
    from app.schemas import PlanRequest


class IPlanRepository(Protocol):
    """Persistence interface for training plans."""

    def get_by_id(
        self, plan_id: str, *, include_weeks: bool = False
    ) -> Optional["TrainingPlan"]: ...

    def get_for_user(
        self, plan_id: str, user_id: str, *, include_weeks: bool = False
    ) -> Optional["TrainingPlan"]: ...

    def list_by_user(self, user_id: str) -> List["TrainingPlan"]: ...

    def list_by_user_recent_first(self, user_id: str) -> List["TrainingPlan"]: ...

    def get_by_share_token(self, share_token: str) -> Optional["TrainingPlan"]: ...

    def find_duplicate(
        self, user_id: str, request: "PlanRequest", race_time_seconds: Optional[int]
    ) -> Optional["TrainingPlan"]: ...

    def save(self, plan: "TrainingPlan") -> None: ...

    def delete(self, plan: "TrainingPlan") -> None: ...


class IRunRepository(Protocol):
    """Persistence interface for logged runs."""

    def get_by_id(self, run_id: int) -> Optional["RunLog"]: ...

    def get_for_user(self, run_id: int, user_id: str) -> Optional["RunLog"]: ...

    def list_by_user(self, user_id: str) -> List["RunLog"]: ...

    def list_recent_for_user(
        self, user_id: str, *, since: Any | None = None, limit: int | None = None
    ) -> List["RunLog"]: ...

    def save(self, run: "RunLog") -> None: ...

    def delete(self, run: "RunLog") -> None: ...


class IUserRepository(Protocol):
    """Persistence interface for application users."""

    def get_by_id(self, user_id: str) -> Optional["User"]: ...

    def get_by_google_id(self, google_id: str) -> Optional["User"]: ...

    def get_by_email(self, email: str) -> Optional["User"]: ...

    def save(self, user: "User") -> None: ...


class IFavoriteRecipeRepository(Protocol):
    """Persistence interface for a user's favorite recipes."""

    def list_for_user(self, user_id: str) -> List["FavoriteRecipe"]: ...

    def get_for_user(
        self, favorite_id: str, user_id: str
    ) -> Optional["FavoriteRecipe"]: ...

    def get_by_user_and_name(
        self, user_id: str, recipe_name: str
    ) -> Optional["FavoriteRecipe"]: ...

    def save(self, favorite: "FavoriteRecipe") -> None: ...

    def delete(self, favorite: "FavoriteRecipe") -> None: ...
