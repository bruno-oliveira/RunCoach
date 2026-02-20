from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Boolean
from datetime import datetime, timezone
import uuid

from app.models.base import Base


class StrengthExercise(Base):
    __tablename__ = "strength_exercises"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, index=True)
    exercise_id = Column(String, nullable=False, unique=True)  # Original ID from source dataset
    force = Column(String)  # "push", "pull", etc.
    level = Column(String)  # "beginner", "intermediate", "advanced"
    mechanic = Column(String)  # "compound", "isolation"
    equipment = Column(String)  # "body only", "dumbbell", etc.
    primary_muscles = Column(Text)  # JSON array of muscles
    secondary_muscles = Column(Text)  # JSON array of muscles
    instructions = Column(Text)  # JSON array of instruction strings
    category = Column(String)  # "strength", "stretching", etc.
    target_muscles = Column(Text)  # From GIFs dataset: "full-body", "quads", etc.
    
    # Media
    images = Column(Text)  # JSON array of image paths from free-exercise-db
    gif_url = Column(String)  # Direct URL from Exercises_Dataset
    
    # Filtering
    is_running_related = Column(Boolean, default=False, index=True)
    is_bodyweight = Column(Boolean, default=False, index=True)
    is_dumbbell = Column(Boolean, default=False, index=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
