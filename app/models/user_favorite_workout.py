from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from datetime import datetime, timezone

from app.models.base import Base


class UserFavoriteWorkout(Base):
    __tablename__ = "user_favorite_workouts"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    workout_id = Column(String, ForeignKey("daily_strength_workouts.id"), nullable=False, index=True)
    notes = Column(String)  # User's personal notes about this workout
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    
    __table_args__ = (UniqueConstraint('user_id', 'workout_id', name='unique_user_workout'),)
