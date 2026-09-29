"""The Anthropic adapter: bounded, tolerant of the SDK's shape, silent on failure.

This module sat at 0% coverage because ``anthropic`` is an optional dependency
out of the default dev environment, so the whole adapter went unexercised —
including three properties that can hurt: an unbounded client timeout, an
exception escaping into a page render, and (the one that actually bit) the 1.x
SDK removing ``temperature`` from ``Messages.create`` while ``generate_note``
swallowed the resulting ``TypeError``.

Pinned here against a stubbed SDK; ``test_anthropic_sdk_contract.py`` pins the
same call against the real one.
"""

import sys
import types
from typing import Any

import pytest

from app.infrastructure.integrations.anthropic_narrator import (
    _MAX_RETRIES,
    _REQUEST_TIMEOUT_SECONDS,
    _TEMPERATURE,
    AnthropicCoachNarrator,
)


class _MessagesNoTemperature:
    """The 1.x shape: ``create`` takes no ``temperature`` (it raises TypeError)."""

    def __init__(self, *, content=None, raises: Exception | None = None):
        self._content = content
        self._raises = raises
        self.calls: list[dict[str, Any]] = []

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: Any,
        messages: Any,
    ):
        self.calls.append(
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": messages,
            }
        )
        if self._raises is not None:
            raise self._raises
        if self._content is not None:
            return types.SimpleNamespace(content=self._content)
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text="A note.")]
        )


class _MessagesWithTemperature(_MessagesNoTemperature):
    """The 0.x shape: ``create`` still accepts ``temperature``."""

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        temperature: float,
        system: Any,
        messages: Any,
    ):
        result = super().create(
            model=model, max_tokens=max_tokens, system=system, messages=messages
        )
        self.calls[-1]["temperature"] = temperature
        return result


class _MessagesUnreadableSignature(_MessagesNoTemperature):
    """A ``create`` whose signature cannot be introspected (e.g. a C extension)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.create = _unreadable  # type: ignore[method-assign]


def _unreadable(*args, **kwargs):  # pragma: no cover - only its signature matters
    raise AssertionError("should not be called")


class _FakeClient:
    def __init__(self, messages, **kwargs):
        self.kwargs = kwargs
        self.messages = messages


class _FakeSDK:
    """Stands in for the ``anthropic`` module with a chosen ``create`` shape."""

    def __init__(self, messages_cls):
        self._messages_cls = messages_cls
        self.ctor_kwargs: dict[str, Any] = {}
        self.client: _FakeClient | None = None

    def install(self, monkeypatch) -> "_FakeSDK":
        outer = self

        def _Anthropic(**kwargs):  # noqa: N802 — mirrors the SDK's own name
            client = _FakeClient(outer._messages_cls(), **kwargs)
            outer.ctor_kwargs.update(kwargs)
            outer.client = client
            return client

        monkeypatch.setitem(
            sys.modules, "anthropic", types.SimpleNamespace(Anthropic=_Anthropic)
        )
        return self


@pytest.fixture
def sdk(monkeypatch):
    """A 1.x-shaped SDK by default (no ``temperature``)."""
    return _FakeSDK(_MessagesNoTemperature).install(monkeypatch)


@pytest.fixture
def legacy_sdk(monkeypatch):
    """A 0.x-shaped SDK, which still accepts ``temperature``."""
    return _FakeSDK(_MessagesWithTemperature).install(monkeypatch)


def _make() -> AnthropicCoachNarrator:
    return AnthropicCoachNarrator(api_key="k", model="claude-test")


class TestClientBounds:
    """The SDK defaults (600s, 2 retries) are wrong for a call made in a request."""

    def test_bounds_the_timeout_and_retries(self, sdk):
        _make()

        assert sdk.ctor_kwargs["timeout"] == _REQUEST_TIMEOUT_SECONDS
        assert sdk.ctor_kwargs["max_retries"] == _MAX_RETRIES
        # Guard the intent, not just the constant: a page load cannot absorb a
        # call that occupies a worker thread for minutes.
        assert _REQUEST_TIMEOUT_SECONDS <= 60
        assert _MAX_RETRIES <= 2

    def test_passes_the_api_key_through(self, sdk):
        AnthropicCoachNarrator(api_key="secret-key", model="m")

        assert sdk.ctor_kwargs["api_key"] == "secret-key"


class TestTemperatureTolerance:
    """The 1.x SDK dropped ``temperature``; passing it raises, and the adapter
    swallows the raise — so it must not pass it."""

    def test_detects_an_sdk_that_accepts_temperature(self, legacy_sdk):
        assert _make()._supports_temperature is True

    def test_detects_an_sdk_that_rejects_temperature(self, sdk):
        assert _make()._supports_temperature is False

    def test_treats_an_unreadable_signature_as_unsupported(self, monkeypatch):
        _FakeSDK(_MessagesUnreadableSignature).install(monkeypatch)

        assert _make()._supports_temperature is False

    def test_omits_temperature_when_the_sdk_will_not_take_it(self, sdk):
        narrator = _make()

        assert narrator.generate_note({"a": 1}) == "A note."
        assert "temperature" not in sdk.client.messages.calls[0]

    def test_sends_temperature_when_the_sdk_accepts_it(self, legacy_sdk):
        narrator = _make()

        assert narrator.generate_note({"a": 1}) == "A note."
        assert legacy_sdk.client.messages.calls[0]["temperature"] == _TEMPERATURE


class TestGenerateNote:
    def test_returns_the_model_text(self, sdk):
        assert _make().generate_note({"a": 1}) == "A note."

    def test_returns_none_when_the_sdk_raises(self, sdk):
        """A coach's note is a nicety — failure must fall back, not 500 the page."""
        narrator = _make()
        narrator._client.messages = _MessagesNoTemperature(raises=RuntimeError("reset"))

        assert narrator.generate_note({"a": 1}) is None

    def test_logs_a_failure_at_error_level(self, sdk, caplog):
        """The only signal that the AI path is down — warning would read as noise."""
        narrator = _make()
        narrator._client.messages = _MessagesNoTemperature(raises=RuntimeError("reset"))

        with caplog.at_level("ERROR"):
            narrator.generate_note({"a": 1})

        assert any(
            "Coach note generation failed" in record.message
            for record in caplog.records
        )

    @pytest.mark.parametrize(
        "content", [[], [types.SimpleNamespace(type="text", text="  ")]]
    )
    def test_returns_none_for_empty_model_output(self, sdk, content):
        """Whitespace or no text block must read as 'no note', not ''."""
        narrator = _make()
        narrator._client.messages = _MessagesNoTemperature(content=content)

        assert narrator.generate_note({"a": 1}) is None

    def test_ignores_non_text_blocks(self, sdk):
        narrator = _make()
        narrator._client.messages = _MessagesNoTemperature(
            content=[
                types.SimpleNamespace(type="thinking", text="ignore me"),
                types.SimpleNamespace(type="text", text="The real note."),
            ]
        )

        assert narrator.generate_note({"a": 1}) == "The real note."

    def test_sends_a_stable_cacheable_persona_prefix(self, sdk):
        """Prompt caching only engages on a stable prefix, so it must lead."""
        _make().generate_note({"current_km": 40})

        sent = sdk.client.messages.calls[0]
        assert sent["model"] == "claude-test"
        assert sent["max_tokens"] == 300
        assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert sent["system"][0]["type"] == "text"
        # The fact pack travels in the user turn, not the cached prefix.
        assert "current_km" in sent["messages"][0]["content"]

    def test_the_fact_pack_reaches_the_model(self, sdk):
        _make().generate_note({"focus": "ease the tempo"})

        sent = sdk.client.messages.calls[0]
        assert "ease the tempo" in sent["messages"][0]["content"]
