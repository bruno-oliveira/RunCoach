"""Integration tests for FitnessService.create_fitness_plan."""

import uuid

from app.contexts.runner.fitness.fitness_service import FitnessService
from app.models import DailyWorkout, TrainingPlan, User, WeeklyPlan
from app.schemas import FitnessPlanRequest


def _user(test_db):
    user = User(id=str(uuid.uuid4()), email=f"{uuid.uuid4().hex[:8]}@t.com")
    test_db.add(user)
    test_db.commit()
    return user


def test_create_fitness_plan_persists_full_structure(test_db, nutrition_engine):
    user = _user(test_db)
    req = FitnessPlanRequest(
        current_km=30.0, weeks=8, runs_per_week=4, focus_area="vo2max"
    )

    plan, plan_data = FitnessService(test_db).create_fitness_plan(
        user, req, nutrition_engine
    )

    assert plan.id is not None
    assert plan.plan_type == "fitness"
    assert plan.target_distance == "fitness_vo2max"
    assert len(plan_data) == 8

    weeks = (
        test_db.query(WeeklyPlan).filter(WeeklyPlan.training_plan_id == plan.id).count()
    )
    assert weeks == 8
    workouts = (
        test_db.query(DailyWorkout)
        .join(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan.id)
        .count()
    )
    assert workouts > 0
    # Nutrition attached.
    assert plan.nutrition_plan_data is not None


def test_create_fitness_plan_dedupes(test_db, nutrition_engine):
    user = _user(test_db)
    req = FitnessPlanRequest(
        current_km=25.0, weeks=6, runs_per_week=3, focus_area="threshold"
    )

    plan1, _ = FitnessService(test_db).create_fitness_plan(user, req, nutrition_engine)
    plan2, _ = FitnessService(test_db).create_fitness_plan(user, req, nutrition_engine)

    assert plan1.id == plan2.id
    total = test_db.query(TrainingPlan).filter(TrainingPlan.user_id == user.id).count()
    assert total == 1


def test_create_fitness_plan_derives_vdot_from_race(test_db, nutrition_engine):
    user = _user(test_db)
    req = FitnessPlanRequest(
        current_km=40.0,
        weeks=10,
        runs_per_week=5,
        focus_area="balanced",
        recent_race_distance_km=10.0,
        recent_race_time="00:45:00",
    )

    plan, _ = FitnessService(test_db).create_fitness_plan(user, req, nutrition_engine)
    # The request model computes VDOT from the race time; it is persisted.
    assert plan.vdot is not None and plan.vdot > 0
