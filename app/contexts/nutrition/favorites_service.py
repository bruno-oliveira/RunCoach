"""Favorite-recipe business logic for the nutrition context.

Keeps the recipes router thin: the router handles HTTP, this service owns the
dedup/ownership rules and talks to the repository (never the ORM directly),
mirroring PlanService / the runner context.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.contexts.nutrition.repositories import SQLAlchemyFavoriteRecipeRepository
from app.domain.repositories import IFavoriteRecipeRepository
from app.models import FavoriteRecipe


class FavoritesService:
    """Encapsulates favorite-recipe operations.

    Accepts a repository factory so tests / non-SQLAlchemy adapters can supply
    their own implementation of the ``IFavoriteRecipeRepository`` protocol.
    """

    def __init__(
        self,
        repo_factory: Callable[
            [Session], IFavoriteRecipeRepository
        ] = SQLAlchemyFavoriteRecipeRepository,
    ) -> None:
        self._repo_factory = repo_factory

    def list_favorites(self, user_id: str, db: Session) -> List[Dict[str, Any]]:
        """Return the user's favorited recipe payloads, newest first.

        Each payload is the stored ``recipe_data`` with the ``favorite_id``
        injected so the client can later remove it.
        """
        favorites = self._repo_factory(db).list_for_user(user_id)
        recipes: List[Dict[str, Any]] = []
        for fav in favorites:
            recipe_data = dict(fav.recipe_data)
            recipe_data["favorite_id"] = fav.id
            recipes.append(recipe_data)
        return recipes

    def add_favorite(
        self, user_id: str, recipe_data: Dict[str, Any], db: Session
    ) -> Dict[str, Any]:
        """Add a recipe to favorites, deduplicating by recipe name."""
        repo = self._repo_factory(db)
        recipe_name = recipe_data.get("name")
        meal_type = recipe_data.get("meal_type")

        existing = repo.get_by_user_and_name(user_id, recipe_name)
        if existing:
            return {"message": "Recipe already in favorites", "already_exists": True}

        favorite = FavoriteRecipe(
            user_id=user_id,
            recipe_name=recipe_name,
            meal_type=meal_type,
            recipe_data=recipe_data,
        )
        repo.save(favorite)
        db.commit()
        return {"message": "Recipe added to favorites", "id": favorite.id}

    def favorite_id_for(
        self, user_id: str, recipe_name: str, db: Session
    ) -> Optional[str]:
        """Return the favorite id for a recipe the user has saved, else None."""
        favorite = self._repo_factory(db).get_by_user_and_name(user_id, recipe_name)
        return favorite.id if favorite else None

    def remove_favorite(self, favorite_id: str, user_id: str, db: Session) -> bool:
        """Remove a favorite the user owns. Returns False if it doesn't exist."""
        repo = self._repo_factory(db)
        favorite = repo.get_for_user(favorite_id, user_id)
        if not favorite:
            return False
        repo.delete(favorite)
        db.commit()
        return True


__all__ = ["FavoritesService"]
