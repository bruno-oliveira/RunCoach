"""Pin the adapter's call against the *real* ``anthropic`` SDK.

This is the test that would have caught the bug it was written for. The adapter
used to pass ``temperature=0.7`` unconditionally. The 1.x SDK removed that
parameter from ``Messages.create``, the call raised ``TypeError``, and
``generate_note`` — which must never break a page — swallowed it and returned
``None``. The result was an AI feature that had quietly degraded to its
deterministic fallback, with nothing red anywhere.

A stub cannot catch that: a stub agrees with whatever you call it with. So this
module drives the real SDK. No network is involved — constructing a client makes
no request, and the assertions are about what the SDK *accepts*, not what it
returns.

Skipped, not failed, when the SDK is absent: ``anthropic`` is an optional
dependency and is not installed in every dev environment. CI installs it from
``requirements.txt``, so CI is where this is enforced.
"""

import inspect

import pytest

anthropic = pytest.importorskip(
    "anthropic", reason="optional dependency; CI installs it from requirements.txt"
)

from app.infrastructure.integrations.anthropic_narrator import (  # noqa: E402
    _MAX_RETRIES,
    _REQUEST_TIMEOUT_SECONDS,
    _TEMPERATURE,
    AnthropicCoachNarrator,
    _accepts_temperature,
)


@pytest.fixture
def narrator() -> AnthropicCoachNarrator:
    """A real client, real SDK, no request made."""
    return AnthropicCoachNarrator(
        api_key="sk-ant-not-a-real-key", model="claude-haiku-4-5"
    )


class TestConstructorIsAcceptedByTheRealSdk:
    def test_the_client_accepts_our_timeout_and_retries(self, narrator):
        """If the SDK renames these, the ctor raises and the feature is dead."""
        assert narrator._client is not None
        assert _REQUEST_TIMEOUT_SECONDS > 0
        assert _MAX_RETRIES >= 0

    def test_the_installed_version_is_the_pinned_one(self):
        """requirements.txt is the contract; drift here means CI != production."""
        import re
        from pathlib import Path

        requirements = Path("requirements.txt").read_text()
        pinned = re.search(r"^anthropic==(\S+)$", requirements, re.MULTILINE)

        assert pinned, "anthropic must be pinned with == in requirements.txt"
        assert anthropic.__version__ == pinned.group(1), (
            f"installed anthropic {anthropic.__version__} != pinned {pinned.group(1)}"
        )


class TestMessageCreateAcceptsOurCall:
    """The regression guard, expressed as the SDK's own signature."""

    def test_temperature_support_is_detected_correctly(self, narrator):
        """Whichever shape is installed, the probe must agree with reality."""
        real = (
            "temperature"
            in inspect.signature(narrator._client.messages.create).parameters
        )

        assert narrator._supports_temperature is real
        assert _accepts_temperature(narrator._client.messages) is real

    def test_every_kwarg_we_send_is_a_real_parameter(self, narrator):
        """Catches an SDK that renames *any* of our keys, not just temperature."""
        accepted = set(inspect.signature(narrator._client.messages.create).parameters)

        for keyword in ("model", "max_tokens", "system", "messages"):
            assert keyword in accepted, f"{keyword} is no longer accepted"

        if narrator._supports_temperature:
            assert "temperature" in accepted
            assert _TEMPERATURE > 0

    def test_the_real_signature_accepts_the_payload_we_build(self, narrator):
        """The regression guard, with no network involved.

        ``Signature.bind`` raises ``TypeError: got an unexpected keyword
        argument`` for an unknown key — the exact error the SDK raised when this
        adapter still sent ``temperature`` to a 1.x release.
        """
        payload = narrator._build_request({"today": {"purpose": "easy"}})

        # Raises TypeError if the SDK would reject any keyword.
        inspect.signature(narrator._client.messages.create).bind(**payload)

    def test_we_do_not_send_temperature_to_an_sdk_that_rejects_it(self, narrator):
        payload = narrator._build_request({"today": {"purpose": "easy"}})

        assert ("temperature" in payload) is narrator._supports_temperature
