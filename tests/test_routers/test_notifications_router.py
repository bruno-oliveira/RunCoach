"""Tests for the two outbound-nudge surfaces: the trigger and the way out.

The trigger mails real people, so most of what matters is that it stays shut:
invisible until configured, and closed to anyone without the secret. The
unsubscribe has the opposite problem — it must work for someone holding only an
email, with no session — so what matters there is that a *prefetch* of the link
doesn't silently change their preference.
"""

import pytest

from app.application.outbound_nudge_service import unsubscribe_token
from app.infrastructure.config import settings
from app.models import User

CRON_SECRET = "test-cron-secret"


@pytest.fixture
def cron_enabled(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", CRON_SECRET)
    return CRON_SECRET


@pytest.fixture
def subscriber(test_db) -> User:
    user = User(
        id="notify-user",
        email="runner@example.com",
        nudge_email_enabled=True,
    )
    test_db.add(user)
    test_db.commit()
    return user


# ---------------------------------------------------------------------------
# The scheduled trigger
# ---------------------------------------------------------------------------


def test_the_trigger_is_invisible_until_a_cron_secret_is_configured(
    client, monkeypatch
):
    """404, not 401: an endpoint that mails real people shouldn't announce
    itself to someone probing for it."""
    monkeypatch.setattr(settings, "cron_secret", "")
    res = client.post("/api/notifications/run", headers={"X-Cron-Secret": "anything"})
    assert res.status_code == 404


def test_the_trigger_rejects_a_missing_secret(client, cron_enabled):
    assert client.post("/api/notifications/run").status_code == 403


def test_the_trigger_rejects_a_wrong_secret(client, cron_enabled):
    res = client.post(
        "/api/notifications/run", headers={"X-Cron-Secret": "not-the-secret"}
    )
    assert res.status_code == 403


def test_the_trigger_runs_with_the_right_secret(client, cron_enabled, subscriber):
    res = client.post("/api/notifications/run", headers={"X-Cron-Secret": CRON_SECRET})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["candidates"] == 1
    # No SMTP host in tests, so the null mailer refuses and nothing is recorded.
    assert body["delivered"] == 0


def test_a_dry_run_is_reported_as_such(client, cron_enabled, subscriber):
    res = client.post(
        "/api/notifications/run?dry_run=true",
        headers={"X-Cron-Secret": CRON_SECRET},
    )
    assert res.status_code == 200
    assert res.json()["dry_run"] is True


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------


def test_the_unsubscribe_page_offers_but_does_not_act(client, test_db, subscriber):
    """Mail clients and scanners prefetch links; a GET that flipped the
    preference would be a bug the runner never sees."""
    token = unsubscribe_token(subscriber.id)
    res = client.get(f"/unsubscribe?u={subscriber.id}&t={token}")

    assert res.status_code == 200
    assert "Stop coaching emails?" in res.text
    test_db.refresh(subscriber)
    assert subscriber.nudge_email_enabled is True


def test_confirming_turns_coaching_emails_off(client, test_db, subscriber):
    token = unsubscribe_token(subscriber.id)
    res = client.post("/unsubscribe", data={"u": subscriber.id, "t": token})

    assert res.status_code == 200
    assert "no more coaching emails" in res.text.lower()
    test_db.refresh(subscriber)
    assert subscriber.nudge_email_enabled is False


def test_unsubscribing_twice_is_harmless(client, test_db, subscriber):
    token = unsubscribe_token(subscriber.id)
    client.post("/unsubscribe", data={"u": subscriber.id, "t": token})
    res = client.post("/unsubscribe", data={"u": subscriber.id, "t": token})

    assert res.status_code == 200
    test_db.refresh(subscriber)
    assert subscriber.nudge_email_enabled is False


def test_a_forged_token_cannot_unsubscribe_a_stranger(client, test_db, subscriber):
    res = client.post("/unsubscribe", data={"u": subscriber.id, "t": "deadbeef"})

    assert res.status_code == 200
    assert "didn't work" in res.text
    test_db.refresh(subscriber)
    assert subscriber.nudge_email_enabled is True


def test_another_users_token_does_not_transfer(client, test_db, subscriber):
    res = client.post(
        "/unsubscribe",
        data={"u": subscriber.id, "t": unsubscribe_token("someone-else")},
    )

    assert res.status_code == 200
    test_db.refresh(subscriber)
    assert subscriber.nudge_email_enabled is True


def test_an_unknown_user_gets_the_same_failure_as_a_bad_token(client):
    res = client.get("/unsubscribe?u=ghost&t=" + unsubscribe_token("ghost"))
    assert res.status_code == 200
    assert "didn't work" in res.text
