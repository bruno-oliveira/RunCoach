"""Recipe page endpoints (HTML responses)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.contexts.nutrition.favorites_service import FavoritesService
from app.contexts.nutrition.meal_database import get_meal_database
from app.dependencies import get_db, get_favorites_service, get_optional_user
from app.infrastructure.config import settings
from app.template_helpers import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recipes-pages"])
templates = create_templates()
meal_db = get_meal_database()


@router.get("/recipes", response_class=HTMLResponse)
def recipes_page(
    request: Request,
    current_user=Depends(get_optional_user),
) -> HTMLResponse:
    """Render the recipe search and browse page.

    Args:
        request: The incoming HTTP request.
        current_user: The currently authenticated user, if any.

    Returns:
        HTMLResponse with the rendered recipes template.
    """
    return templates.TemplateResponse(
        request,
        "recipes.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id,
            "current_page": "recipes",
        },
    )


@router.get("/recipes/{recipe_name}", response_class=HTMLResponse)
def recipe_detail(
    request: Request,
    recipe_name: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
    favorites_service: FavoritesService = Depends(get_favorites_service),
) -> HTMLResponse:
    """Render a single recipe detail page with a shareable URL.

    Args:
        request: The incoming HTTP request.
        recipe_name: URL-slug of the recipe (e.g. "chicken-stir-fry").
        db: Database session.
        current_user: The currently authenticated user, if any.

    Returns:
        HTMLResponse with the rendered recipe detail template.

    Raises:
        HTTPException: 404 if the recipe is not found.
    """
    # Find recipe by name (case-insensitive search)
    recipe = None
    for meal in meal_db.meals:
        if meal.get("name", "").lower().replace(" ", "-") == recipe_name.lower():
            recipe = meal
            break

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Check if recipe is in user's favorites
    favorite_id = None
    if current_user:
        favorite_id = favorites_service.favorite_id_for(
            current_user.id, recipe.get("name"), db
        )
    is_favorite = favorite_id is not None

    return templates.TemplateResponse(
        request,
        "recipe_detail.html",
        {
            "request": request,
            "recipe": recipe,
            "user": current_user,
            "is_favorite": is_favorite,
            "favorite_id": favorite_id,
            "google_client_id": settings.google_client_id,
            "current_page": "recipes",
        },
    )
