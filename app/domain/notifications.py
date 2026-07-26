"""Outbound-notification port.

Every surface in RunCoach is pull: the runner opens the app and the coach
speaks. This is the one seam that lets it push — so it is deliberately narrow
(one message, one recipient, one boolean) and defined in the domain layer so
the application service never imports SMTP.

``send`` returns whether the message was *actually delivered*. A mailer that
isn't configured must return ``False`` rather than swallowing the message and
reporting success — the nudge service records "we emailed this runner" from
that boolean, and a false positive would silence the real email that follows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class EmailMessage:
    """One outbound email.

    ``text`` is the message; ``html`` is optional and, when present, sent as
    the richer alternative of the same content. Plain text is never omitted —
    a coaching nudge has to be readable in any client.
    """

    to: str
    subject: str
    text: str
    html: Optional[str] = None


class Mailer(Protocol):
    """Sends an :class:`EmailMessage`. Returns ``True`` only on delivery."""

    def send(self, message: EmailMessage) -> bool: ...
