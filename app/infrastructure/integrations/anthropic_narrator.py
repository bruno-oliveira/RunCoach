"""Anthropic-backed implementation of the CoachNarrator protocol.

Turns the fact pack into 2-4 sentences of warm, grounded coach prose via Claude
Haiku. Two safety properties matter here:

- The model is told to use ONLY the numbers in the fact pack — it never invents
  paces/streaks/VDOT. The displayed hard numbers come from the deterministic
  recognition chips, not from this prose, so accuracy is guaranteed regardless.
- Generation is wrapped in a TTL cache keyed by the fact pack's content hash, so
  a given day's note is generated once and reused until something material
  changes (a new run, the day rolls over, the adaptation stance shifts). Any
  failure returns ``None`` so the caller falls back to the deterministic note.
"""

import hashlib
import json
import logging
from typing import Any, Optional

from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Persona + guardrails. Static so the prompt-cache prefix stays stable; marked
# cacheable below (engages once the prompt exceeds Haiku's min cacheable size).
_SYSTEM_PROMPT = """You are an experienced, perceptive running coach writing a \
short daily note to an athlete you have been coaching for weeks. You know their \
training history, and you speak to them directly — warm, honest, never \
saccharine.

Write 2 to 4 sentences, in the second person ("you"), as one flowing note — not \
a list. Shape it as:
1. Open by recognizing the athlete: their consistency, their streak, the effort \
they have actually put in. Make them feel seen.
2. Connect today to their journey — how far they have come (fitness, pace, \
efficiency) and where they are in the plan.
3. Close by framing today's session: what it is and why it matters right now.

Hard rules:
- Use ONLY the numbers and facts in the provided JSON. Never invent paces, \
distances, dates, VDOT values, streaks, or any metric that is not present.
- If something is not in the data, do not mention it and do not guess.
- No medical or injury advice.
- No emojis, no markdown, no headings, no preamble such as "Here is your note". \
Output only the note itself."""


class AnthropicCoachNarrator:
    """Generates the Coach's Note via Claude Haiku, with a content-keyed cache."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        cache_ttl_seconds: int = 12 * 3600,
        cache_maxsize: int = 256,
    ) -> None:
        # Lazy import so the module (and app startup) never hard-depends on the
        # SDK unless an AI narrator is actually constructed.
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._cache: TTLCache = TTLCache(maxsize=cache_maxsize, ttl=cache_ttl_seconds)

    def generate_note(self, context: dict[str, Any]) -> Optional[str]:
        key = hashlib.sha256(
            json.dumps(context, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        if key in self._cache:
            return self._cache[key]

        try:
            note = self._call(context)
        except Exception:  # never let a coach note break the page
            logger.warning("Coach note generation failed", exc_info=True)
            return None

        if note:
            self._cache[key] = note
        return note

    def _call(self, context: dict[str, Any]) -> Optional[str]:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=300,
            temperature=0.7,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Here is the athlete's training context as JSON:\n\n"
                        + json.dumps(context, indent=2, default=str)
                        + "\n\nWrite the coach's note now."
                    ),
                }
            ],
        )
        text = next(
            (b.text for b in response.content if getattr(b, "type", None) == "text"),
            "",
        ).strip()
        return text or None
