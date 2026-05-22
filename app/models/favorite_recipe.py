"""FavoriteRecipe model for saving user's favorite recipes."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.types import JSON

from app.models.base import Base


class FavoriteRecipe(Base):
    __tablename__ = "favorite_recipes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    recipe_name = Column(String, nullable=False)
    meal_type = Column(String, nullable=False)
    recipe_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="favorite_recipes")
