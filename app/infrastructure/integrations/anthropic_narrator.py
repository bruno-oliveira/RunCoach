"""Anthropic-backed implementation of the CoachNarrator protocol.

Turns the fact pack into 2-4 sentences of warm, grounded coach prose via Claude
Haiku. The model is told to use ONLY the numbers in the fact pack — it never
invents paces/streaks/VDOT. The displayed hard numbers come from the
deterministic recognition chips, not from this prose, so accuracy is guaranteed
regardless. Any failure returns ``None`` so the caller falls back to the
deterministic note.

Caching is the caller's responsibility: ``coach_narrative_service`` persists the
generated payload on the plan keyed by a run signature, so this adapter just
generates on demand and is only invoked when the note actually needs rebuilding.

**The SDK is a moving target and this call is version-sensitive.** ``Messages.
create`` dropped its ``temperature`` parameter in the 1.x SDK (the replacement
``output_config`` carries ``effort``/``format``, not sampling), so passing it
raises ``TypeError``. Because ``generate_note`` swallows every exception by
design — a note must never break a page — that failure mode is *silent*: the
note would quietly centre on the deterministic fallback forever. The adapter
therefore probes the signature once and omits the parameter when unsupported,
and ``tests/test_services/test_anthropic_sdk_contract.py`` pins the whole call
against the real SDK so an incompatible upgrade fails CI rather than production.
"""

import inspect
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Persona + guardrails. Static so the prompt-cache prefix stays stable; marked
# cacheable below (engages once the prompt exceeds Haiku's min cacheable size).
_SYSTEM_PROMPT = """You are an experienced, perceptive running coach writing a \
short daily note to a recreational runner you have been coaching for weeks. You \
speak to them directly — warm and encouraging, but your real job is to make them \
a better, smarter runner. Be a coach, not a cheerleader.

Write 2 to 4 sentences, in the second person ("you"), as one flowing note — not \
a list, no labels. Build it in three beats:

1. RECOGNITION — ONE short clause acknowledging their consistency or journey. \
Keep it brief; they already show up, and the chips beside the note carry the \
numbers, so do not recite stats.
2. TODAY'S PURPOSE — what today's session builds and how to run it. Ground this \
in the "today" block (its purpose rationale, and the HR-zone / distance cue when \
present). This is the teaching beat — be concrete and specific.
3. FOCUS — the single coaching adjustment in the "focus" field, framed for \
today. ONLY include this beat when "focus" is present and non-null. If "focus" \
is null, DO NOT invent a warning, caveat, or adjustment — simply end after \
today's purpose.

Hard rules:
- Use ONLY the numbers and facts in the provided JSON. Never invent paces, \
distances, dates, VDOT values, streaks, zones, or any metric not present.
- If something is not in the data, do not mention it and do not guess.
- Respect the focus rule above: no manufactured concern on a clean day.
- No medical or injury advice.
- No emojis, no markdown, no headings, no preamble such as "Here is your note". \
Output only the note itself."""

# See the note in ``AnthropicCoachNarrator.__init__``: the SDK's 600s default is
# unsuitable for a call made inside a page request.
_REQUEST_TIMEOUT_SECONDS = 20.0
_MAX_RETRIES = 1
# Moderate sampling variance: warm prose should not be identical every day, but
# the fact pack is what carries the meaning, so this is flavour, not accuracy.
_TEMPERATURE = 0.7


def _accepts_temperature(messages_api: Any) -> bool:
    """Whether this SDK's ``Messages.create`` still takes ``temperature``.

    Probed rather than assumed, because the failure mode is silent (see the
    module docstring). Returns False on an unreadable signature: dropping a
    flavour parameter is the harmless direction to guess in.
    """
    try:
        return "temperature" in inspect.signature(messages_api.create).parameters
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return False


class AnthropicCoachNarrator:
    """Generates the Coach's Note via Claude Haiku (stateless; caller caches)."""

    def __init__(self, api_key: str, model: str) -> None:
        # Lazy import so the module (and app startup) never hard-depends on the
        # SDK unless an AI narrator is actually constructed.
        import anthropic

        # The SDK defaults are 600s with 2 internal retries, which is the wrong
        # shape for this call: it runs inside ``GET /api/coach-note``, and the
        # route is a sync ``def`` (Starlette's threadpool), so one hung request
        # holds a worker thread for ten minutes and enough of them starve every
        # other sync endpoint on the machine. A coach's note is a nicety —
        # bound it to something a page load can absorb and let the deterministic
        # fallback in ``coach_narrative_service`` cover the rest.
        self._client = anthropic.Anthropic(
            api_key=api_key,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            max_retries=_MAX_RETRIES,
        )
        self._model = model
        # Probed once at construction; see the module docstring for why this is
        # not simply passed and allowed to fail.
        self._supports_temperature = _accepts_temperature(self._client.messages)

    def generate_note(self, context: dict[str, Any]) -> Optional[str]:
        try:
            return self._call(context)
        except Exception:  # never let a coach note break the page
            # ERROR, not warning: this is the only signal that the AI path is
            # down. Left at warning, a silent SDK incompatibility (see the module
            # docstring) would look like normal noise in the logs.
            logger.error("Coach note generation failed", exc_info=True)
            return None

    def _build_request(self, context: dict[str, Any]) -> dict[str, Any]:
        """The exact kwargs sent to ``Messages.create``.

        Split out from ``_call`` so the SDK-contract test can check the payload
        against the installed SDK's real signature (``Signature.bind``) without
        making a request — an unexpected keyword is precisely the failure this
        adapter must not hit twice.
        """
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 300,
            "system": [
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Here is the athlete's training context as JSON:\n\n"
                        + json.dumps(context, indent=2, default=str)
                        + "\n\nWrite the coach's note now."
                    ),
                }
            ],
        }
        if self._supports_temperature:
            request["temperature"] = _TEMPERATURE
        return request

    def _call(self, context: dict[str, Any]) -> Optional[str]:
        response = self._client.messages.create(**self._build_request(context))
        text = next(
            (b.text for b in response.content if getattr(b, "type", None) == "text"),
            "",
        ).strip()
        return text or None
