"""FavoriteRecipe model for saving user's favorite recipes."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class FavoriteRecipe(Base):
    __tablename__ = "favorite_recipes"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    recipe_name: Mapped[str] = mapped_column(String)
    meal_type: Mapped[str] = mapped_column(String)
    recipe_data: Mapped[Any] = mapped_column(JSON)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="favorite_recipes")
