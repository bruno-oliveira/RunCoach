"""The runner's language reaches everything written with no page to translate it.

The page is translated in the browser. An email, a push, the PDF and a workout
title on the watch are written on the server, often with no request around at
all — so the language has to arrive (a cookie), be remembered (``users.language``)
and be applied at each of those exits. One test per link in that chain.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.application.push_notification_service import PushNotifier
from app.contexts.auth.auth_service import AuthService
from app.core.coaching.outbound_nudge import OutboundNudge, render_email
from app.core.coaching.push_messages import RunFacts, after_sync_message
from app.core.i18n import (
    normalize_language,
    request_language,
    reset_request_language,
    set_request_language,
    stated_request_language,
)
from app.core.time_utils import utcnow_naive
from app.domain.notifications import PushMessage, PushOutcome
from app.infrastructure.export.runna.sheet import (
    Chip,
    Cover,
    DayCard,
    PhaseBlock,
    Sheet,
    WeekRow,
    localize_sheet,
)
from app.infrastructure.i18n import localizer, translate
from app.infrastructure.integrations import intervals_service
from app.models import PushSubscription, User

# --- which language ---------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [("pt", "pt"), ("pt-PT", "pt"), ("PT_br", "pt"), ("en", "en"), ("xx", None)],
)
def test_normalize_language(given: str, expected: str | None):
    assert normalize_language(given) == expected


def test_a_request_that_names_no_language_is_english_but_says_so():
    token = set_request_language(None)
    try:
        assert request_language() == "en"
        assert stated_request_language() is None
    finally:
        reset_request_language(token)


def _signed_in(client: TestClient, db: Session) -> User:
    user = User(id="lang-user", email="lang@example.com", last_activity=utcnow_naive())
    db.add(user)
    db.commit()
    client.cookies.set(
        "access_token", AuthService().create_access_token({"sub": user.id})
    )
    return user


def test_the_cookie_is_remembered_on_the_user(client: TestClient, test_db: Session):
    user = _signed_in(client, test_db)
    client.cookies.set("rc_lang", "pt")

    assert client.get("/api/auth/me").status_code == 200

    test_db.refresh(user)
    assert user.language == "pt"


def test_a_request_without_the_cookie_leaves_the_stored_language(
    client: TestClient, test_db: Session
):
    user = _signed_in(client, test_db)
    user.language = "pt"
    test_db.commit()

    # No cookie (an API client), then one that is not a language at all.
    assert client.get("/api/auth/me").status_code == 200
    client.cookies.set("rc_lang", "klingon")
    assert client.get("/api/auth/me").status_code == 200

    test_db.refresh(user)
    assert user.language == "pt"


# --- push -------------------------------------------------------------------


class _Sender:
    configured = True

    def __init__(self) -> None:
        self.sent: list[PushMessage] = []

    def send(self, target, message: PushMessage) -> str:
        self.sent.append(message)
        return PushOutcome.DELIVERED


def _subscribed(db: Session, language: str | None) -> User:
    user = User(id=f"push-{language}", email=f"{language}@example.com")
    user.language = language
    db.add(user)
    db.add(
        PushSubscription(
            user_id=user.id, endpoint=f"https://push/{language}", p256dh="k", auth="a"
        )
    )
    db.commit()
    return user


def test_every_push_is_translated_at_the_notifier(test_db: Session):
    sender = _Sender()
    user = _subscribed(test_db, "pt")
    message = PushMessage(
        title="Rest day", body="Check in to tell the plan how you feel."
    )

    assert PushNotifier(test_db, sender).notify(
        user, message, category=None, kind="test", key="one"
    )

    assert sender.sent[0].title == "Dia de descanso"
    assert sender.sent[0].body == "Faça o check-in para dizer ao plano como se sente."


def test_a_runner_with_no_stored_language_gets_english(test_db: Session):
    sender = _Sender()
    user = _subscribed(test_db, None)

    PushNotifier(test_db, sender).notify(
        user,
        PushMessage(title="Rest day", body="Enjoy it."),
        category=None,
        kind="test",
        key="one",
    )

    assert sender.sent[0].title == "Rest day"


def test_a_push_is_translated_before_it_is_clipped():
    # Clipped first, the sentence ends in "…" and matches nothing.
    long_body = " ".join(["Your plan was updated."] * 20)

    message = after_sync_message(
        RunFacts(distance_km=8.0, pace_min_km=5.25),
        plan_id="p",
        adaptation_headline=long_body,
        localize=localizer("pt"),
    )

    assert message.title.startswith("8 km registados")
    assert message.body.startswith("O seu plano foi atualizado.")
    assert "Your plan" not in message.body
    assert message.body.endswith("…")


# --- email ------------------------------------------------------------------


def test_the_nudge_email_is_written_in_the_runners_language():
    nudge = OutboundNudge(
        kind="gone_quiet",
        signature="s",
        subject="Your plan is still here",
        headline="Your plan is still here",
        body="That's not a problem to fix — it's just information.",
        cta_label="Pick the plan back up",
        cta_path="/today",
    )

    text, html_body = render_email(
        nudge,
        base_url="https://run.example",
        unsubscribe_url="https://run.example/unsubscribe?u=1",
        name="Ana",
        localize=localizer("pt"),
    )

    assert text.startswith("Olá Ana,")
    assert "O seu plano continua aqui" in text
    assert "Retomar o plano: https://run.example/today" in text
    assert "Parar estes e-mails: https://run.example/unsubscribe?u=1" in text
    assert "Parar estes e-mails</a>" in html_body
    # The links are data, not copy: they pass through untouched.
    assert 'href="https://run.example/today"' in html_body


# --- PDF --------------------------------------------------------------------


def test_the_pdf_sheet_translates_its_copy_and_keeps_its_style_keys():
    sheet = Sheet(
        cover=Cover(
            eyebrow="TRAINING PLAN",
            title_lines=("10K",),
            description="",
            stats=(Chip(text="Long Run", kind="long"),),
            legend=(),
        ),
        phases=(
            PhaseBlock(
                eyebrow="",
                title="Peak",
                subtitle="",
                weeks=(
                    WeekRow(
                        number=1,
                        cards=(DayCard(kind="easy", headline="Easy Run"),),
                        tag="(RACE)",
                        is_race=True,
                    ),
                ),
            ),
        ),
        sections=(),
        footer="",
    )

    localized = localize_sheet(sheet, localizer("pt"))

    week = localized.phases[0].weeks[0]
    assert localized.cover.eyebrow == "PLANO DE TREINO"
    assert localized.cover.stats[0].text == "Corrida longa"
    assert localized.cover.stats[0].kind == "long"  # a colour key, not a word
    assert week.cards[0].headline == "Corrida fácil"
    assert week.cards[0].kind == "easy"
    assert week.tag == "(PROVA)"
    assert week.is_race  # the accent no longer depends on the English tag
    assert localized.labels.days[0] == "SEG"
    assert localized.labels.rest == "Descanso"


# --- watch ------------------------------------------------------------------


class _Response:
    status_code = 200

    def json(self):
        return []

    def raise_for_status(self):
        return None


class _Client:
    posted: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        type(self).posted = kwargs["json"]
        return _Response()


async def test_watch_workouts_are_titled_in_the_runners_language(monkeypatch):
    monkeypatch.setattr(intervals_service.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(
        intervals_service, "raise_for_intervals_status", lambda response: None
    )
    event = {
        "name": "400S Into 200S",
        "description": "- Warmup 10m Z2 Pace",
        "start_date_local": f"{date(2026, 10, 12).isoformat()}T00:00:00",
        "external_id": "runcoach-p-1-1",
    }

    await intervals_service.IntervalsService().push_workouts(
        "token", "i1", [event], pre_delete=False, language="pt"
    )

    sent = _Client.posted[0]
    assert sent["name"] == translate("400S Into 200S", "pt") != "400S Into 200S"
    # The description is Intervals.icu's workout syntax, not prose.
    assert sent["description"] == "- Warmup 10m Z2 Pace"
    # The caller's event — the one the mirror hashes — is left in English.
    assert event["name"] == "400S Into 200S"
