"""Tests for the scheduled pass that decides who gets emailed.

The pure detector is covered in ``tests/test_core/test_outbound_nudge.py``.
What's under test here is everything that keeps a scheduled job from turning
into a mailing list: consent, the floor between emails, the repeat guard, and
the rule that we only *record* an email we actually managed to send.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.application.outbound_nudge_service import (
    OutboundNudgeService,
    unsubscribe_token,
    verify_unsubscribe_token,
)
from app.domain.notifications import EmailMessage
from app.infrastructure.notifications import NullMailer
from app.models import ReadinessLog, RunLog, TrainingPlan, User


class _RecordingMailer:
    """Collects what it was asked to send and reports success."""

    def __init__(self, delivers: bool = True):
        self.delivers = delivers
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> bool:
        self.sent.append(message)
        return self.delivers


def _week(week: int, distance: float = 8.0) -> dict:
    """A rest Monday and a real run on every other day."""
    workouts = [{"day": 1, "type": "rest", "distance": 0}]
    workouts += [{"day": d, "type": "easy", "distance": distance} for d in range(2, 8)]
    return {"week": week, "daily_workouts": workouts}


@pytest.fixture
def today() -> date:
    return date.today()


@pytest.fixture
def subscriber(test_db) -> User:
    user = User(
        id="nudge-user",
        email="runner@example.com",
        name="Sam Taylor",
        nudge_email_enabled=True,
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def active_plan(test_db, subscriber, today) -> TrainingPlan:
    """A plan the runner is in week 2 of."""
    plan = TrainingPlan(
        id="nudge-plan",
        user_id=subscriber.id,
        current_weekly_km=30,
        target_distance="10",
        weeks_duration=6,
        start_date=datetime.combine(today - timedelta(days=7), datetime.min.time()),
        plan_data=[_week(w) for w in range(1, 7)],
    )
    test_db.add(plan)
    test_db.commit()
    return plan


def _log_run(db, user: User, plan: TrainingPlan, days_ago: int) -> None:
    db.add(
        RunLog(
            user_id=user.id,
            training_plan_id=plan.id,
            date=datetime.combine(
                date.today() - timedelta(days=days_ago), datetime.min.time()
            ),
            distance_km=8.0,
            duration_minutes=45,
        )
    )
    db.commit()


def _run(db, mailer, **kwargs) -> dict:
    return OutboundNudgeService(db, mailer).run(**kwargs)


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


def test_a_runner_who_never_opted_in_is_not_even_a_candidate(
    test_db, subscriber, active_plan
):
    subscriber.nudge_email_enabled = False
    test_db.commit()

    mailer = _RecordingMailer()
    summary = _run(test_db, mailer)

    assert summary["candidates"] == 0
    assert mailer.sent == []


def test_an_opted_in_runner_with_no_email_address_is_skipped(
    test_db, subscriber, active_plan
):
    subscriber.email = None
    test_db.commit()

    mailer = _RecordingMailer()
    assert _run(test_db, mailer)["candidates"] == 0


def test_unsubscribing_stops_the_next_run(test_db, subscriber, active_plan):
    _log_run(test_db, subscriber, active_plan, days_ago=8)
    mailer = _RecordingMailer()
    assert _run(test_db, mailer)["delivered"] == 1

    subscriber.nudge_email_enabled = False
    subscriber.last_nudge_email_at = None
    subscriber.last_nudge_email_signature = None
    test_db.commit()

    assert _run(test_db, mailer)["candidates"] == 0


# ---------------------------------------------------------------------------
# Having something to say
# ---------------------------------------------------------------------------


def test_a_runner_on_track_gets_nothing(test_db, subscriber, active_plan):
    _log_run(test_db, subscriber, active_plan, days_ago=1)

    mailer = _RecordingMailer()
    summary = _run(test_db, mailer)

    assert summary["candidates"] == 1
    assert summary["skipped_no_signal"] == 1
    assert mailer.sent == []


def test_a_runner_with_no_plan_in_flight_is_left_alone(test_db, subscriber):
    mailer = _RecordingMailer()
    summary = _run(test_db, mailer)
    assert summary["skipped_no_signal"] == 1
    assert mailer.sent == []


def test_a_finished_plan_is_not_something_to_be_behind_on(
    test_db, subscriber, active_plan, today
):
    active_plan.start_date = datetime.combine(
        today - timedelta(weeks=20), datetime.min.time()
    )
    test_db.commit()
    _log_run(test_db, subscriber, active_plan, days_ago=30)

    mailer = _RecordingMailer()
    assert _run(test_db, mailer)["skipped_no_signal"] == 1


def test_going_quiet_mid_plan_earns_an_email(test_db, subscriber, active_plan):
    _log_run(test_db, subscriber, active_plan, days_ago=8)

    mailer = _RecordingMailer()
    summary = _run(test_db, mailer)

    assert summary["delivered"] == 1
    assert len(mailer.sent) == 1
    message = mailer.sent[0]
    assert message.to == "runner@example.com"
    # First name only — "Hi Sam", not "Hi Sam Taylor".
    assert "Hi Sam," in message.text
    assert "/unsubscribe?u=nudge-user" in message.text


def test_a_run_of_rough_mornings_earns_an_email(
    test_db, subscriber, active_plan, today
):
    _log_run(test_db, subscriber, active_plan, days_ago=1)
    for offset in range(3):
        test_db.add(
            ReadinessLog(
                user_id=subscriber.id,
                date=today - timedelta(days=offset),
                sleep_hours=4.0,
                energy=1,
                soreness=5,
                score=22.0,
            )
        )
    test_db.commit()

    mailer = _RecordingMailer()
    assert _run(test_db, mailer)["delivered"] == 1
    assert "run-down" in mailer.sent[0].text


# ---------------------------------------------------------------------------
# Rate limit and repeat guard
# ---------------------------------------------------------------------------


def test_a_second_pass_the_same_day_sends_nothing(test_db, subscriber, active_plan):
    _log_run(test_db, subscriber, active_plan, days_ago=8)
    mailer = _RecordingMailer()

    assert _run(test_db, mailer)["delivered"] == 1
    second = _run(test_db, mailer)

    assert second["delivered"] == 0
    assert second["skipped_rate_limited"] == 1
    assert len(mailer.sent) == 1


def test_an_unchanged_situation_is_not_restated_once_the_floor_has_passed(
    test_db, subscriber, active_plan
):
    _log_run(test_db, subscriber, active_plan, days_ago=8)
    mailer = _RecordingMailer()
    _run(test_db, mailer)

    # Step past the rate limit, but the runner is still in the same week away.
    subscriber.last_nudge_email_at = datetime.now(timezone.utc).replace(
        tzinfo=None
    ) - timedelta(days=30)
    test_db.commit()

    summary = _run(test_db, mailer)
    assert summary["skipped_repeat"] == 1
    assert len(mailer.sent) == 1


def test_a_materially_worse_situation_does_get_a_second_email(
    test_db, subscriber, active_plan, today
):
    _log_run(test_db, subscriber, active_plan, days_ago=8)
    mailer = _RecordingMailer()
    _run(test_db, mailer)

    # Another week away: a different signature, so it is news again.
    run = test_db.query(RunLog).first()
    run.date = datetime.combine(today - timedelta(days=16), datetime.min.time())
    subscriber.last_nudge_email_at = datetime.now(timezone.utc).replace(
        tzinfo=None
    ) - timedelta(days=30)
    test_db.commit()

    assert _run(test_db, mailer)["delivered"] == 1
    assert len(mailer.sent) == 2


# ---------------------------------------------------------------------------
# Honest bookkeeping
# ---------------------------------------------------------------------------


def test_a_failed_send_is_not_recorded_as_sent(test_db, subscriber, active_plan):
    """Otherwise a broken SMTP host silences the real email that follows."""
    _log_run(test_db, subscriber, active_plan, days_ago=8)

    failing = _RecordingMailer(delivers=False)
    summary = _run(test_db, failing)

    assert summary["nudged"] == 1
    assert summary["delivered"] == 0
    assert summary["failed"] == 1
    test_db.refresh(subscriber)
    assert subscriber.last_nudge_email_at is None
    assert subscriber.last_nudge_email_signature is None

    # …and once SMTP is fixed, the message actually goes.
    working = _RecordingMailer()
    assert _run(test_db, working)["delivered"] == 1


def test_an_unconfigured_deploy_sends_nothing_and_says_so(
    test_db, subscriber, active_plan
):
    _log_run(test_db, subscriber, active_plan, days_ago=8)

    summary = _run(test_db, NullMailer())

    assert summary["nudged"] == 1
    assert summary["delivered"] == 0
    test_db.refresh(subscriber)
    assert subscriber.last_nudge_email_at is None


def test_dry_run_reports_who_would_be_mailed_without_mailing_them(
    test_db, subscriber, active_plan
):
    _log_run(test_db, subscriber, active_plan, days_ago=8)

    mailer = _RecordingMailer()
    summary = _run(test_db, mailer, dry_run=True)

    assert summary["nudged"] == 1
    assert summary["delivered"] == 0
    assert mailer.sent == []
    test_db.refresh(subscriber)
    assert subscriber.last_nudge_email_at is None


def test_one_runners_bad_data_does_not_abort_the_batch(
    test_db, subscriber, active_plan, monkeypatch
):
    other = User(id="nudge-user-2", email="two@example.com", nudge_email_enabled=True)
    test_db.add(other)
    test_db.commit()

    original = OutboundNudgeService._active_plan

    def _explode_for_first(self, user, today):
        if user.id == "nudge-user":
            raise RuntimeError("corrupt plan_data")
        return original(self, user, today)

    monkeypatch.setattr(OutboundNudgeService, "_active_plan", _explode_for_first)

    summary = _run(test_db, _RecordingMailer())
    assert summary["candidates"] == 2
    assert summary["failed"] == 1


# ---------------------------------------------------------------------------
# Unsubscribe tokens
# ---------------------------------------------------------------------------


def test_an_unsubscribe_token_only_verifies_for_its_own_user():
    token = unsubscribe_token("user-a")
    assert verify_unsubscribe_token("user-a", token)
    assert not verify_unsubscribe_token("user-b", token)
    assert not verify_unsubscribe_token("user-a", "")
    assert not verify_unsubscribe_token("user-a", "deadbeef")


def test_unsubscribe_tokens_are_stable_so_an_old_email_still_works():
    # The link lives in an inbox forever; it must not expire between sends.
    assert unsubscribe_token("user-a") == unsubscribe_token("user-a")
