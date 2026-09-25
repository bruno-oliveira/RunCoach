"""Recipe search and favorites endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.contexts.nutrition.favorites_service import FavoritesService
from app.contexts.nutrition.meal_database import (
    get_meal_database,
    meal_matches_query,
)
from app.dependencies import (
    get_current_user,
    get_db,
    get_favorites_service,
    get_optional_user,
)
from app.models import User
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recipes"])
templates = create_templates()
meal_db = get_meal_database()


@router.get("/api/recipes")
def search_recipes(
    query: str = "",
    meal_type: str = "",
    min_protein: int = 0,
    max_calories: int = 2000,
    dietary_tags: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Search and filter recipes from the meals database with pagination.

    Args:
        query: Free text; every word must appear in the name, description or
            ingredients.
        meal_type: Filter by meal type (e.g. "breakfast", "trail").
        min_protein: Minimum protein in grams per serving.
        max_calories: Maximum calories per serving.
        dietary_tags: Comma-separated tags; a recipe must carry all of them.
        page: Page number (1-indexed).
        page_size: Number of recipes per page.

    Returns:
        The page of recipes, the total, page metadata, and ``counts`` — how
        many recipes each meal type would return with the *other* filters
        applied, so the category chips can show live counts.
    """
    selected_tags = [tag.strip() for tag in dietary_tags.split(",") if tag.strip()]

    def passes_other_filters(recipe: dict) -> bool:
        tags = recipe.get("dietary_tags", [])
        return (
            meal_matches_query(recipe, query)
            and recipe.get("protein", 0) >= min_protein
            and recipe.get("calories", 0) <= max_calories
            and all(tag in tags for tag in selected_tags)
        )

    candidates = [r for r in meal_db.meals if passes_other_filters(r)]
    counts: dict[str, int] = {}
    for recipe in candidates:
        counts[recipe["meal_type"]] = counts.get(recipe["meal_type"], 0) + 1

    filtered_recipes = [
        r for r in candidates if not meal_type or r.get("meal_type") == meal_type
    ]

    total = len(filtered_recipes)
    total_pages = (total + page_size - 1) // page_size
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "recipes": filtered_recipes[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "counts": counts,
    }


@router.get("/api/recipes/favorites")
def get_favorites(
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
    favorites_service: FavoritesService = Depends(get_favorites_service),
):
    """Get the current user's favorite recipes.

    Returns:
        Dictionary with a list of favorited recipe data objects.
    """
    if not current_user:
        return {"recipes": []}
    return {"recipes": favorites_service.list_favorites(current_user.id, db)}


@router.post("/api/recipes/favorite")
def add_favorite(
    recipe_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    favorites_service: FavoritesService = Depends(get_favorites_service),
):
    """Add a recipe to the current user's favorites.

    Returns:
        Dictionary with success message and favorite ID, or already_exists flag.
    """
    return favorites_service.add_favorite(current_user.id, recipe_data, db)


@router.delete("/api/recipes/favorite/{favorite_id}")
def remove_favorite(
    favorite_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    favorites_service: FavoritesService = Depends(get_favorites_service),
):
    """Remove a recipe from the current user's favorites.

    Raises:
        HTTPException: 404 if the favorite is not found or doesn't belong to the user.
    """
    if not favorites_service.remove_favorite(favorite_id, current_user.id, db):
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"message": "Recipe removed from favorites"}
