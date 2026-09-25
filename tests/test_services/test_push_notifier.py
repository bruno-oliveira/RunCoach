"""The one path to a phone: consent, exactly-once, and pruning dead devices."""

from datetime import datetime, timedelta, timezone

import pytest

from app.application.ambient_sync_service import RunnerSync
from app.application.push_notification_service import KIND_AFTER_SYNC, PushNotifier
from app.domain.notifications import PushMessage, PushOutcome
from app.models import NotificationLog, PushSubscription, RunLog, TrainingPlan, User


class FakeSender:
    def __init__(self, outcome: str = PushOutcome.DELIVERED, configured: bool = True):
        self.outcome = outcome
        self._configured = configured
        self.sent: list[tuple[str, PushMessage]] = []

    @property
    def configured(self) -> bool:
        return self._configured

    def send(self, target, message):
        self.sent.append((target.endpoint, message))
        return self.outcome


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def runner(test_db) -> User:
    user = User(id="push-user", email="push@example.com")
    test_db.add(user)
    test_db.add(
        PushSubscription(
            user_id=user.id,
            endpoint="https://fcm.googleapis.com/fcm/send/one",
            p256dh="p",
            auth="a",
        )
    )
    test_db.commit()
    return user


MSG = PushMessage(title="t", body="b")


def test_sends_once_per_key(test_db, runner):
    sender = FakeSender()
    notifier = PushNotifier(test_db, sender)
    assert notifier.notify(runner, MSG, category="after_run", kind="k", key="1")
    assert not notifier.notify(runner, MSG, category="after_run", kind="k", key="1")
    assert len(sender.sent) == 1


def test_respects_category_opt_out(test_db, runner):
    runner.notification_prefs = {"after_run": False}
    sender = FakeSender()
    assert not PushNotifier(test_db, sender).notify(
        runner, MSG, category="after_run", kind="k", key="1"
    )
    assert sender.sent == []


def test_undelivered_message_releases_its_claim_for_a_retry(test_db, runner):
    notifier = PushNotifier(test_db, FakeSender(PushOutcome.FAILED))
    assert not notifier.notify(runner, MSG, category=None, kind="k", key="1")
    assert test_db.query(NotificationLog).count() == 0
    notifier.sender = FakeSender()
    assert notifier.notify(runner, MSG, category=None, kind="k", key="1")


def test_gone_subscription_is_deleted(test_db, runner):
    PushNotifier(test_db, FakeSender(PushOutcome.GONE)).notify(
        runner, MSG, category=None, kind="k", key="1"
    )
    assert test_db.query(PushSubscription).count() == 0


def test_repeated_failures_eventually_prune_the_device(test_db, runner):
    notifier = PushNotifier(test_db, FakeSender(PushOutcome.FAILED))
    for n in range(5):
        notifier.notify(runner, MSG, category=None, kind="k", key=str(n))
    assert test_db.query(PushSubscription).count() == 0


def test_unconfigured_server_sends_nothing(test_db, runner):
    sender = FakeSender(configured=False)
    assert not PushNotifier(test_db, sender).notify(
        runner, MSG, category=None, kind="k", key="1"
    )
    assert sender.sent == []


def _run(test_db, user, *, km=8.0, age=timedelta(hours=1), plan_id=None) -> RunLog:
    run = RunLog(
        user_id=user.id,
        training_plan_id=plan_id,
        date=_now() - age,
        distance_km=km,
        duration_minutes=km * 5.5,
        avg_pace_min_km=5.5,
        created_at=_now() - age,
    )
    test_db.add(run)
    test_db.commit()
    return run


def test_after_sync_announces_the_new_run(test_db, runner):
    run = _run(test_db, runner)
    sender = FakeSender()
    assert PushNotifier(test_db, sender).after_sync(runner, RunnerSync(imported=1))
    assert sender.sent[0][1].title == "8 km logged · 5:30/km"
    ledger = test_db.query(NotificationLog).one()
    assert (ledger.kind, ledger.key) == (KIND_AFTER_SYNC, run.id)


def test_after_sync_folds_the_plan_change_into_the_same_note(test_db, runner):
    plan = TrainingPlan(
        id="pp",
        user_id=runner.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=8,
        plan_data=[],
        last_change_plan={"did_change": True, "reason": "Eased next week ~8%."},
    )
    test_db.add(plan)
    test_db.commit()
    _run(test_db, runner, plan_id="pp")
    sender = FakeSender()
    PushNotifier(test_db, sender).after_sync(
        runner,
        RunnerSync(imported=1, adjustments=[{"plan_id": "pp", "auto_adjusted": True}]),
    )
    title, body = sender.sent[0][1].title, sender.sent[0][1].body
    assert title.endswith("— plan adjusted")
    assert body == "Eased next week ~8%."


def test_backfills_and_old_runs_stay_silent(test_db, runner):
    _run(test_db, runner)
    sender = FakeSender()
    notifier = PushNotifier(test_db, sender)
    assert not notifier.after_sync(runner, RunnerSync(imported=40))

    test_db.query(RunLog).delete()
    _run(test_db, runner, age=timedelta(days=5))
    assert not notifier.after_sync(runner, RunnerSync(imported=1))
    assert sender.sent == []
