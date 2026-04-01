from sqlalchemy.orm import relationship

from app.models.base import Base
from app.models.user import User
from app.models.training_plan import TrainingPlan
from app.models.weekly_plan import WeeklyPlan
from app.models.daily_workout import DailyWorkout
from app.models.plan_customization import PlanCustomization
from app.models.run_log import RunLog
from app.models.run_feedback import RunFeedback
from app.models.favorite_recipe import FavoriteRecipe
from app.models.triathlon_plan import TriathlonPlan

# Configure relationships after all models are imported
User.training_plans = relationship("TrainingPlan", back_populates="user", cascade="all, delete-orphan")
User.run_logs = relationship("RunLog", back_populates="user", cascade="all, delete-orphan")

TrainingPlan.user = relationship("User", back_populates="training_plans")
TrainingPlan.weekly_plans = relationship("WeeklyPlan", back_populates="training_plan", cascade="all, delete-orphan")

WeeklyPlan.training_plan = relationship("TrainingPlan", back_populates="weekly_plans")
WeeklyPlan.daily_workouts = relationship("DailyWorkout", back_populates="weekly_plan", cascade="all, delete-orphan")

DailyWorkout.weekly_plan = relationship("WeeklyPlan", back_populates="daily_workouts")

PlanCustomization.training_plan = relationship("TrainingPlan")

RunLog.user = relationship("User", back_populates="run_logs")
RunLog.training_plan = relationship("TrainingPlan")
RunLog.daily_workout = relationship("DailyWorkout")
RunLog.feedback = relationship("RunFeedback", uselist=False, back_populates="run_log")

RunFeedback.run_log = relationship("RunLog", back_populates="feedback")
RunFeedback.user = relationship("User")

User.favorite_recipes = relationship("FavoriteRecipe", back_populates="user", cascade="all, delete-orphan")
FavoriteRecipe.user = relationship("User", back_populates="favorite_recipes")

User.triathlon_plans = relationship("TriathlonPlan", back_populates="user", cascade="all, delete-orphan")
TriathlonPlan.user = relationship("User", back_populates="triathlon_plans")

__all__ = [
    "Base",
    "User",
    "TrainingPlan",
    "WeeklyPlan",
    "DailyWorkout",
    "PlanCustomization",
    "RunLog",
    "RunFeedback",
    "FavoriteRecipe",
    "TriathlonPlan",
]
