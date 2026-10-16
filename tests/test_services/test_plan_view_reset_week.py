"""Which weeks offer "Reset week": only those whose distances have moved.

Every generated workout stores its baseline distance, so "has a baseline" was
true of every week and the button sat on all of them.
"""

from datetime import datetime

from app.application.plan_view_service import PlanViewService
from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator
from app.contexts.plan.plan_creation_helpers import persist_weekly_workouts
from app.models import DailyWorkout, TrainingPlan, User, WeeklyPlan


def test_only_an_adjusted_week_can_be_reset(test_db):
    user = User(id="reset-user", email="reset@example.com")
    plan_data = TrainingPlanGenerator().generate_plan(30, 10, 8, 4, vdot=45.0)
    plan = TrainingPlan(
        id="reset-plan",
        user_id=user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=8,
        start_date=datetime(2026, 10, 12),
        plan_data=plan_data,
    )
    test_db.add_all([user, plan])
    test_db.flush()
    persist_weekly_workouts(plan, plan_data, test_db)
    test_db.commit()

    view = PlanViewService().get_plan_view_data(plan, user, test_db)
    assert view["overridden_weeks"] == set()

    moved = (
        test_db.query(DailyWorkout)
        .join(WeeklyPlan)
        .filter(WeeklyPlan.training_plan_id == plan.id, WeeklyPlan.week_number == 3)
        .filter(DailyWorkout.distance_km > 0)
        .first()
    )
    moved.distance_km = (moved.distance_km or 0) - 1.0
    test_db.commit()

    view = PlanViewService().get_plan_view_data(plan, user, test_db)
    assert view["overridden_weeks"] == {3}
