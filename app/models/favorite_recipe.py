"""FavoriteRecipe model for saving user's favorite recipes."""

from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, func

from app.models.base import Base


class FavoriteRecipe(Base):
    """Model for storing user's favorite recipes."""

    __tablename__ = "favorite_recipes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    recipe_name = Column(String, nullable=False)
    meal_type = Column(String, nullable=False)
    recipe_data = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
