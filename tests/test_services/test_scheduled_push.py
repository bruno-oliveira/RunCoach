"""Hourly pushes: morning brief and week review land in each runner's own hour."""

from datetime import datetime, time, timedelta, timezone

import pytest

from app.application.push_notification_service import PushNotifier
from app.application.scheduled_push_service import (
    MORNING_HOUR,
    REVIEW_HOUR,
    ScheduledPushService,
    local_now,
)
from app.application.week_review_service import due_review
from app.domain.notifications import PushOutcome
from app.models import PushSubscription, RunLog, TrainingPlan, User


class FakeSender:
    configured = True

    def __init__(self):
        self.sent = []

    def send(self, target, message):
        self.sent.append(message)
        return PushOutcome.DELIVERED


class NoWellness:
    async def fetch_wellness(self, *args, **kwargs):
        return []


def _week(n):
    # A session every day, so the brief has something to say whatever
    # weekday the suite happens to run on.
    return {
        "week": n,
        "daily_workouts": [
            {"day": d, "type": "easy", "distance": 5} for d in range(1, 8)
        ],
    }


@pytest.fixture
def setup(test_db):
    """A UTC runner with a push device, in week 2 of a Monday-anchored plan.

    Anchored to the real UTC date because the service asks the clock which
    plan is in progress and what today's session is. Returns the Sunday that
    closes week 2 as the review date.
    """
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=today.weekday()) - timedelta(days=7)
    user = User(id="sched-user", email="s@example.com", timezone="UTC")
    test_db.add(user)
    test_db.add(
        PushSubscription(
            user_id=user.id,
            endpoint="https://fcm.googleapis.com/fcm/send/s",
            p256dh="p",
            auth="a",
        )
    )
    plan = TrainingPlan(
        id="sched-plan",
        user_id=user.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=6,
        start_date=datetime.combine(start, datetime.min.time()),
        plan_data=[_week(w) for w in range(1, 7)],
    )
    test_db.add(plan)
    test_db.add(
        RunLog(
            user_id=user.id,
            date=datetime.combine(start + timedelta(days=7), datetime.min.time()),
            distance_km=6.0,
            duration_minutes=33,
        )
    )
    test_db.commit()
    return user, plan, start + timedelta(days=13)


def test_local_now_follows_the_runners_zone():
    utc = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
    assert local_now("Europe/Lisbon", utc).hour == 19
    assert local_now("Not/AZone", utc).hour == 18
    assert local_now(None, utc).hour == 18


def test_review_is_due_on_the_last_day_and_the_morning_after(test_db, setup):
    user, plan, sunday = setup
    due = due_review(plan, user.id, test_db, sunday)
    assert due is not None and due.review.week_number == 2
    assert due.review.done_km == 6.0 and due.review.sessions_planned == 7
    assert due_review(plan, user.id, test_db, sunday + timedelta(days=1)) is not None
    assert due_review(plan, user.id, test_db, sunday - timedelta(days=2)) is None


def _at(today, hour):
    return datetime.combine(today, time(hour, 10), tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_week_review_fires_at_the_runners_evening_once(test_db, setup):
    user, plan, sunday = setup
    user.notification_prefs = {"morning_brief": False}
    test_db.commit()
    sender = FakeSender()
    service = ScheduledPushService(test_db, NoWellness(), PushNotifier(test_db, sender))

    summary = await service.run(now_utc=_at(sunday, REVIEW_HOUR))
    assert summary["reviews_sent"] == 1
    assert sender.sent[0].title == "Week 2: 6 km of 35 km"

    again = await service.run(now_utc=_at(sunday, REVIEW_HOUR))
    assert again["reviews_sent"] == 0


@pytest.mark.asyncio
async def test_morning_brief_names_todays_session_once(test_db, setup):
    user, plan, _sunday = setup
    today = datetime.now(timezone.utc).date()
    sender = FakeSender()
    service = ScheduledPushService(test_db, NoWellness(), PushNotifier(test_db, sender))

    summary = await service.run(now_utc=_at(today, MORNING_HOUR))
    assert summary["briefs_sent"] == 1
    assert sender.sent[0].title.startswith("Today: Easy")
    assert (await service.run(now_utc=_at(today, MORNING_HOUR)))["briefs_sent"] == 0


@pytest.mark.asyncio
async def test_nothing_is_sent_outside_the_runners_hours(test_db, setup):
    user, plan, _sunday = setup
    today = datetime.now(timezone.utc).date()
    sender = FakeSender()
    service = ScheduledPushService(test_db, NoWellness(), PushNotifier(test_db, sender))
    await service.run(now_utc=_at(today, 3))
    assert sender.sent == []


@pytest.mark.asyncio
async def test_morning_brief_opt_out_is_respected(test_db, setup):
    user, plan, _sunday = setup
    today = datetime.now(timezone.utc).date()
    user.notification_prefs = {"morning_brief": False}
    test_db.commit()
    sender = FakeSender()
    service = ScheduledPushService(test_db, NoWellness(), PushNotifier(test_db, sender))
    await service.run(now_utc=_at(today, MORNING_HOUR))
    assert sender.sent == []


@pytest.mark.asyncio
async def test_unconfigured_push_does_nothing(test_db, setup):
    class Off(FakeSender):
        configured = False

    service = ScheduledPushService(test_db, NoWellness(), PushNotifier(test_db, Off()))
    assert (await service.run())["configured"] is False
