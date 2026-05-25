"""Coaching domain protocols.

Pure interface for the AI "Coach's Note" voice layer. The application layer
depends on this protocol; infrastructure (``AnthropicCoachNarrator``) implements
it. Keeping it here means the application code never imports the SDK and tests
can inject a fake narrator.
"""

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class CoachNarrator(Protocol):
    """Turns a structured fact pack into a short, warm coach's note.

    Implementations must return ``None`` (never raise) when generation is
    unavailable or fails, so the caller can fall back to a deterministic note.
    """

    def generate_note(self, context: dict[str, Any]) -> Optional[str]: ...
