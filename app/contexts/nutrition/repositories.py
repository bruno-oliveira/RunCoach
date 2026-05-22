"""SQLAlchemy implementation of IFavoriteRecipeRepository for the nutrition context."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import FavoriteRecipe


class SQLAlchemyFavoriteRecipeRepository:
    """Persistence adapter for ``FavoriteRecipe``.

    Wraps SQLAlchemy ``Session`` operations behind the
    ``IFavoriteRecipeRepository`` protocol so the nutrition context doesn't
    depend on SQLAlchemy directly.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_user(self, user_id: str) -> List[FavoriteRecipe]:
        return (
            self.session.query(FavoriteRecipe)
            .filter(FavoriteRecipe.user_id == user_id)
            .order_by(FavoriteRecipe.created_at.desc())
            .all()
        )

    def get_for_user(self, favorite_id: str, user_id: str) -> Optional[FavoriteRecipe]:
        return (
            self.session.query(FavoriteRecipe)
            .filter(
                FavoriteRecipe.id == favorite_id,
                FavoriteRecipe.user_id == user_id,
            )
            .first()
        )

    def get_by_user_and_name(
        self, user_id: str, recipe_name: str
    ) -> Optional[FavoriteRecipe]:
        return (
            self.session.query(FavoriteRecipe)
            .filter(
                FavoriteRecipe.user_id == user_id,
                FavoriteRecipe.recipe_name == recipe_name,
            )
            .first()
        )

    def save(self, favorite: FavoriteRecipe) -> None:
        self.session.add(favorite)

    def delete(self, favorite: FavoriteRecipe) -> None:
        self.session.delete(favorite)


__all__ = ["SQLAlchemyFavoriteRecipeRepository"]
