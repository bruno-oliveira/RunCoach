"""Recipe search and favorites endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.contexts.nutrition.favorites_service import FavoritesService
from app.contexts.nutrition.meal_database import get_meal_database
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
    max_calories: int = 1000,
    dietary_tags: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Search and filter recipes from the meals database with pagination.

    Args:
        query: Free-text search term matched against recipe names.
        meal_type: Filter by meal type (e.g. "breakfast", "lunch", "dinner", "snacks").
        min_protein: Minimum protein in grams.
        max_calories: Maximum calories per serving.
        dietary_tags: Comma-separated dietary tags (e.g. "vegetarian,gluten-free").
        page: Page number (1-indexed).
        page_size: Number of recipes per page.

    Returns:
        Dictionary with paginated recipe list, total count, and page metadata.
    """
    all_recipes = meal_db.meals

    # Parse dietary tags from comma-separated string
    selected_dietary_tags = (
        [tag.strip() for tag in dietary_tags.split(",") if tag.strip()]
        if dietary_tags
        else []
    )

    filtered_recipes = []

    for recipe in all_recipes:
        matches_query = query.lower() in recipe.get("name", "").lower()
        matches_meal_type = not meal_type or recipe.get("meal_type") == meal_type
        matches_protein = recipe.get("protein", 0) >= min_protein
        matches_calories = recipe.get("calories", 0) <= max_calories

        # Check dietary tags
        recipe_dietary_tags = recipe.get("dietary_tags", [])
        matches_dietary_tags = not selected_dietary_tags or all(
            tag in recipe_dietary_tags for tag in selected_dietary_tags
        )

        if (
            matches_query
            and matches_meal_type
            and matches_protein
            and matches_calories
            and matches_dietary_tags
        ):
            filtered_recipes.append(recipe)

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
