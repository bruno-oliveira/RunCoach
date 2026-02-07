"""Recipe search and favorites endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db, get_optional_user
from app.meal_database import get_meal_database
from app.models import FavoriteRecipe

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recipes"])
templates = Jinja2Templates(directory="app/templates")
meal_db = get_meal_database()


@router.get("/recipes", response_class=HTMLResponse)
async def recipes_page(
    request: Request,
    current_user = Depends(get_optional_user),
) -> HTMLResponse:
    """Recipe search and browse page."""
    return templates.TemplateResponse(
        "recipes.html",
        {
            "request": request,
            "user": current_user,
            "google_client_id": settings.google_client_id,
        },
    )


@router.get("/recipes/{recipe_name}", response_class=HTMLResponse)
async def recipe_detail(
    request: Request,
    recipe_name: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_optional_user),
) -> HTMLResponse:
    """Recipe detail page with shareable URL."""
    # Find recipe by name (case-insensitive search)
    recipe = None
    for meal in meal_db.meals:
        if meal.get("name", "").lower().replace(" ", "-") == recipe_name.lower():
            recipe = meal
            break
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    # Check if recipe is in user's favorites
    is_favorite = False
    favorite_id = None
    if current_user:
        existing = (
            db.query(FavoriteRecipe)
            .filter(
                FavoriteRecipe.user_id == current_user.id,
                FavoriteRecipe.recipe_name == recipe.get("name"),
            )
            .first()
        )
        if existing:
            is_favorite = True
            favorite_id = existing.id
    
    return templates.TemplateResponse(
        "recipe_detail.html",
        {
            "request": request,
            "recipe": recipe,
            "user": current_user,
            "is_favorite": is_favorite,
            "favorite_id": favorite_id,
            "google_client_id": settings.google_client_id,
        },
    )


@router.get("/api/recipes")
async def search_recipes(
    query: str = "",
    meal_type: str = "",
    min_protein: int = 0,
    max_calories: int = 1000,
    dietary_tags: str = "",
    page: int = 1,
    page_size: int = 50,
):
    """Search recipes from meals database with pagination and dietary tag filtering."""
    all_recipes = meal_db.meals
    
    # Parse dietary tags from comma-separated string
    selected_dietary_tags = [tag.strip() for tag in dietary_tags.split(",") if tag.strip()] if dietary_tags else []
    
    filtered_recipes = []
    
    for recipe in all_recipes:
        matches_query = query.lower() in recipe.get("name", "").lower()
        matches_meal_type = not meal_type or recipe.get("meal_type") == meal_type
        matches_protein = recipe.get("protein", 0) >= min_protein
        matches_calories = recipe.get("calories", 0) <= max_calories
        
        # Check dietary tags
        recipe_dietary_tags = recipe.get("dietary_tags", [])
        matches_dietary_tags = not selected_dietary_tags or all(tag in recipe_dietary_tags for tag in selected_dietary_tags)
        
        if matches_query and matches_meal_type and matches_protein and matches_calories and matches_dietary_tags:
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
async def get_favorites(
    db: Session = Depends(get_db),
    current_user = Depends(get_optional_user),
):
    """Get user's favorite recipes."""
    if not current_user:
        return {"recipes": []}
    
    favorites = (
        db.query(FavoriteRecipe)
        .filter(FavoriteRecipe.user_id == current_user.id)
        .order_by(FavoriteRecipe.created_at.desc())
        .all()
    )
    
    recipes = []
    for fav in favorites:
        try:
            recipe_data = json.loads(fav.recipe_data)
            recipe_data["favorite_id"] = fav.id
            recipes.append(recipe_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Could not parse favorite recipe data for user {current_user.id}")
    
    return {"recipes": recipes}


@router.post("/api/recipes/favorite")
async def add_favorite(
    recipe_data: dict,
    db: Session = Depends(get_db),
    current_user = Depends(get_optional_user),
):
    """Add a recipe to user's favorites."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    recipe_name = recipe_data.get("name")
    meal_type = recipe_data.get("meal_type")
    
    existing = (
        db.query(FavoriteRecipe)
        .filter(
            FavoriteRecipe.user_id == current_user.id,
            FavoriteRecipe.recipe_name == recipe_name,
        )
        .first()
    )
    
    if existing:
        return {"message": "Recipe already in favorites", "already_exists": True}
    
    favorite = FavoriteRecipe(
        user_id=current_user.id,
        recipe_name=recipe_name,
        meal_type=meal_type,
        recipe_data=json.dumps(recipe_data),
    )
    
    db.add(favorite)
    db.commit()
    
    return {"message": "Recipe added to favorites", "id": favorite.id}


@router.delete("/api/recipes/favorite/{favorite_id}")
async def remove_favorite(
    favorite_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_optional_user),
):
    """Remove a recipe from user's favorites."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    favorite = (
        db.query(FavoriteRecipe)
        .filter(
            FavoriteRecipe.id == favorite_id,
            FavoriteRecipe.user_id == current_user.id,
        )
        .first()
    )
    
    if not favorite:
        raise HTTPException(status_code=404, detail="Favorite not found")
    
    db.delete(favorite)
    db.commit()
    
    return {"message": "Recipe removed from favorites"}
