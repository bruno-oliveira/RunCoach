"""FavoriteRecipe model for saving user's favorite recipes."""

import uuid

from sqlalchemy import Column, ForeignKey, String, DateTime, func

from app.models.base import Base


class FavoriteRecipe(Base):
    """Model for storing user's favorite recipes."""

    __tablename__ = "favorite_recipes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    recipe_name = Column(String, nullable=False)
    meal_type = Column(String, nullable=False)
    recipe_data = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
