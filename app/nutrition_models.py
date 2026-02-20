from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

Base = declarative_base()

class Meal(Base):
    __tablename__ = "meals"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    meal_type = Column(String, nullable=False)  # 'breakfast', 'lunch', 'dinner', 'snack', 'post_workout'
    description = Column(Text)
    instructions = Column(Text)  # Cooking instructions
    prep_time = Column(Integer)  # minutes
    cook_time = Column(Integer)  # minutes
    
    # Nutrition information (per serving)
    calories = Column(Float)
    protein = Column(Float)  # grams
    fiber = Column(Float)  # grams
    carbs = Column(Float)  # grams
    fat = Column(Float)  # grams
    
    # Ingredients and dietary info
    ingredients = Column(Text)  # JSON string of ingredients
    dietary_tags = Column(Text)  # JSON string of dietary tags
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class NutritionPlan(Base):
    __tablename__ = "nutrition_plans"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    training_plan_id = Column(String, ForeignKey("training_plans.id"))
    week_number = Column(Integer)
    daily_calories_target = Column(Float)
    protein_target = Column(Float)  # grams
    fiber_target = Column(Float)  # grams
    
    # Meal plan data (JSON)
    meal_plan_data = Column(Text)  # Daily meal plans
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    
    training_plan = relationship("TrainingPlan")

class DailyMealPlan(Base):
    __tablename__ = "daily_meal_plans"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nutrition_plan_id = Column(String, ForeignKey("nutrition_plans.id"))
    day_of_week = Column(Integer)  # 1-7 (Monday-Sunday)
    meal_type = Column(String)  # 'breakfast', 'lunch', 'dinner', 'snack', 'post_workout'
    meal_id = Column(String, ForeignKey("meals.id"))
    servings = Column(Float, default=1.0)
    
    nutrition_plan = relationship("NutritionPlan")
    meal = relationship("Meal")