"""The one path to a phone: consent, exactly-once, pruning dead devices, and
staying off the event loop while doing it."""

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.application.ambient_sync_service import RunnerSync
from app.application.push_notification_service import (
    KIND_AFTER_SYNC,
    KIND_TEST,
    PushNotifier,
    after_sync_off_loop,
    notify_off_loop,
)
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


class _ThreadRecordingNotifier:
    """Stands in for ``PushNotifier``; records which thread reached it."""

    def __init__(self, blocked_seconds: float = 0.0):
        self.thread_id: int | None = None
        self._blocked_seconds = blocked_seconds

    def notify(self, user, message, *, category, kind, key) -> bool:
        if self._blocked_seconds:
            time.sleep(self._blocked_seconds)
        self.thread_id = threading.get_ident()
        return True

    def after_sync(self, user, result) -> bool:
        self.thread_id = threading.get_ident()
        return True


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


class TestOffLoopWrappers:
    """Push delivery is blocking HTTPS, so async callers must not do it inline.

    ``WebPushSender.send`` is synchronous ``httpx`` and is also reached from
    sync callers, so it cannot be a coroutine. That makes it the async caller's
    job to get off the event loop — otherwise a single unresponsive push
    service stalls every request on the machine for up to the 10s send timeout,
    including the health check Fly uses to decide whether to keep the machine.
    """

    async def test_notify_runs_on_a_worker_thread(self, runner):
        notifier = _ThreadRecordingNotifier()
        loop_thread = threading.get_ident()

        delivered = await notify_off_loop(
            notifier, runner, MSG, category=None, kind=KIND_TEST, key="k"
        )

        assert delivered is True
        assert notifier.thread_id is not None
        assert notifier.thread_id != loop_thread

    async def test_after_sync_runs_on_a_worker_thread(self, runner):
        notifier = _ThreadRecordingNotifier()
        loop_thread = threading.get_ident()

        delivered = await after_sync_off_loop(notifier, runner, RunnerSync(imported=1))

        assert delivered is True
        assert notifier.thread_id is not None
        assert notifier.thread_id != loop_thread

    async def test_a_real_notifier_commits_through_the_worker_thread(
        self, test_db, runner
    ):
        """The session is handed to the worker thread and its writes must stick.

        This is the one place a request's ``Session`` is touched off the event
        loop. The handoff is sequential (the caller awaits, so the session is
        never used by two threads at once) and SQLite runs with
        ``check_same_thread=False``, but that is an assumption worth pinning:
        if the claim were written on a connection the caller never sees, the
        exactly-once ledger would silently stop working — pushes would repeat.
        """
        sender = FakeSender()
        notifier = PushNotifier(test_db, sender)
        loop_thread = threading.get_ident()

        delivered = await notify_off_loop(
            notifier, runner, MSG, category=None, kind=KIND_TEST, key="off-loop"
        )

        assert delivered is True
        # The claim landed in the caller's session, on the thread that made it.
        assert notifier.already_sent(runner, KIND_TEST, "off-loop") is True
        assert threading.get_ident() == loop_thread

    async def test_a_second_off_loop_notify_for_the_same_key_is_suppressed(
        self, test_db, runner
    ):
        """Exactly-once survives the thread hop — a retried webhook stays quiet."""
        sender = FakeSender()
        notifier = PushNotifier(test_db, sender)

        first = await notify_off_loop(
            notifier, runner, MSG, category=None, kind=KIND_TEST, key="same"
        )
        second = await notify_off_loop(
            notifier, runner, MSG, category=None, kind=KIND_TEST, key="same"
        )

        assert first is True
        assert second is False
        assert len(sender.sent) == 1

    async def test_the_loop_keeps_running_while_a_send_blocks(self, runner):
        """The behaviour that matters: a stalled send must not stall the loop."""
        notifier = _ThreadRecordingNotifier(blocked_seconds=0.2)
        ticks = 0

        async def _tick():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        ticker = asyncio.create_task(_tick())
        try:
            await notify_off_loop(
                notifier, runner, MSG, category=None, kind=KIND_TEST, key="k"
            )
        finally:
            ticker.cancel()

        # ~20 ticks fit inside a 0.2s sleep — but only if the loop kept running.
        assert ticks >= 5
