from sqlalchemy.orm import relationship

from app.models.base import Base
from app.models.user import User
from app.models.training_plan import TrainingPlan
from app.models.weekly_plan import WeeklyPlan
from app.models.daily_workout import DailyWorkout
from app.models.plan_customization import PlanCustomization
from app.models.run_log import RunLog
from app.models.favorite_recipe import FavoriteRecipe
from app.models.strength_exercise import StrengthExercise
from app.models.daily_strength_workout import DailyStrengthWorkout
from app.models.user_favorite_workout import UserFavoriteWorkout
from app.models.strava_analytics import StravaAnalytics, StravaActivity

# Configure relationships after all models are imported
User.training_plans = relationship("TrainingPlan", back_populates="user")
User.run_logs = relationship("RunLog", back_populates="user")

TrainingPlan.user = relationship("User", back_populates="training_plans")
TrainingPlan.weekly_plans = relationship("WeeklyPlan", back_populates="training_plan")

WeeklyPlan.training_plan = relationship("TrainingPlan", back_populates="weekly_plans")
WeeklyPlan.daily_workouts = relationship("DailyWorkout", back_populates="weekly_plan")

DailyWorkout.weekly_plan = relationship("WeeklyPlan", back_populates="daily_workouts")

PlanCustomization.training_plan = relationship("TrainingPlan")

RunLog.user = relationship("User", back_populates="run_logs")
RunLog.training_plan = relationship("TrainingPlan")
RunLog.daily_workout = relationship("DailyWorkout")

User.favorite_recipes = relationship("FavoriteRecipe")

# relationships for StravaAnalytics and StravaActivity are defined in strava_analytics.py

__all__ = [
    "Base",
    "User",
    "TrainingPlan",
    "WeeklyPlan",
    "DailyWorkout",
    "PlanCustomization",
    "RunLog",
    "FavoriteRecipe",
    "StrengthExercise",
    "DailyStrengthWorkout",
    "UserFavoriteWorkout",
    "StravaAnalytics",
    "StravaActivity",
]
