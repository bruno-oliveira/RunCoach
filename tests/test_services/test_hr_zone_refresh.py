"""A plan's stored HR zones follow the runner's anchors after creation.

Zones used to be stored once, at plan creation, while run classification
resolved the anchors live -- so a new LTHR from Intervals.icu or a corrected max
HR in settings reached the home page but never the plan's BPM targets.
"""

import uuid
from datetime import datetime, timedelta

from app.contexts.runner.fitness.hr_zone_service import (
    HRZoneService,
    refresh_active_plan_zones,
)
from app.core.time_utils import local_today
from app.models import TrainingPlan, User
from app.utils import persist_json


def _uid() -> str:
    return str(uuid.uuid4())


def _week(n: int) -> dict:
    return {
        "week": n,
        "daily_workouts": [
            {"day": 1, "type": "easy", "distance": 6.0},
            {"day": 3, "type": "tempo", "distance": 8.0},
        ],
    }


def _setup(test_db, *, weeks_ago: int = 2, weeks: int = 6):
    user = User(id=_uid(), email=f"{_uid()[:8]}@t.com", max_hr=190, threshold_hr=160)
    test_db.add(user)
    start = local_today() - timedelta(weeks=weeks_ago)
    plan = TrainingPlan(
        id=_uid(),
        user_id=user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=weeks,
        start_date=datetime.combine(start, datetime.min.time()),
        plan_data=[_week(w) for w in range(1, weeks + 1)],
    )
    test_db.add(plan)
    test_db.flush()
    zones = HRZoneService.compute_and_store_zones(plan, user, test_db)
    HRZoneService.inject_hr_zones_into_plan_data(plan.plan_data, zones)
    persist_json(plan, "plan_data")
    test_db.commit()
    return user, plan


def _label(plan: TrainingPlan, week: int) -> str:
    return plan.plan_data[week - 1]["daily_workouts"][0]["hr_zone_label"]


class TestRefreshZones:
    def test_unchanged_anchors_leave_the_plan_alone(self, test_db):
        user, plan = _setup(test_db)
        before = dict(plan.hr_zones_data)

        assert HRZoneService.refresh_zones(plan, user, test_db) is False
        assert plan.hr_zones_data == before

    def test_new_lthr_moves_stored_bands_and_future_labels(self, test_db):
        user, plan = _setup(test_db)
        old_past_label = _label(plan, 1)

        user.threshold_hr = 170
        test_db.commit()

        assert HRZoneService.refresh_zones(plan, user, test_db) is True
        test_db.commit()
        test_db.refresh(plan)

        assert plan.hr_zones_data["lthr"] == 170
        # Zone 3 ends on LTHR.
        assert plan.hr_zones_data["zones"][2]["max_bpm"] == 170
        # Current (week 3) and future weeks carry the new band...
        assert _label(plan, 3) != old_past_label
        assert "170" in plan.plan_data[2]["daily_workouts"][1]["hr_zone_label"]
        # ...while completed weeks keep the target they were prescribed.
        assert _label(plan, 1) == old_past_label

    def test_synced_intervals_lthr_reaches_the_plan(self, test_db):
        user, plan = _setup(test_db)
        user.threshold_hr = None
        user.intervals_lthr = 168
        test_db.commit()

        assert HRZoneService.refresh_zones(plan, user, test_db) is True
        assert plan.hr_zones_data["lthr"] == 168
        assert plan.hr_zones_data["lthr_source"] == "intervals"


class TestRefreshActivePlans:
    def test_finished_plans_are_left_alone(self, test_db):
        user, plan = _setup(test_db, weeks_ago=10, weeks=6)
        before = dict(plan.hr_zones_data)
        user.threshold_hr = 170
        test_db.commit()

        assert refresh_active_plan_zones(user, test_db) == 0
        assert plan.hr_zones_data == before

    def test_active_plan_is_refreshed(self, test_db):
        user, plan = _setup(test_db)
        user.max_hr = 200
        test_db.commit()

        assert refresh_active_plan_zones(user, test_db) == 1
        assert plan.hr_zones_data["max_hr"] == 200
        assert plan.max_heart_rate == 200
