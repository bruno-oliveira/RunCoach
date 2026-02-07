from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from datetime import datetime
import uuid

from app.models.base import Base


class DailyStrengthWorkout(Base):
    __tablename__ = "daily_strength_workouts"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    date = Column(String, nullable=False, index=True)  # Format: "YYYY-MM-DD"
    title = Column(String, nullable=False)
    description = Column(Text)
    
    # Workout structure
    warmup_exercises = Column(Text)  # JSON array of exercise IDs
    main_exercises = Column(Text)  # JSON array with sets, reps, exercise IDs
    cooldown_exercises = Column(Text)  # JSON array of exercise IDs
    
    # Timing (in minutes)
    warmup_duration = Column(Integer, default=5)
    main_duration = Column(Integer, default=25)
    cooldown_duration = Column(Integer, default=5)
    total_duration = Column(Integer, default=35)
    
    # Focus areas
    primary_focus = Column(String)  # e.g., "upper_body", "lower_body", "full_body"
    secondary_focus = Column(String)
    difficulty = Column(String, default="beginner")  # "beginner", "intermediate", "advanced"
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
