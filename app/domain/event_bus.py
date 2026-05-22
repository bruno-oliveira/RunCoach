"""In-process domain event bus.

A minimal pub/sub bus for ``DomainEvent`` subclasses. Synchronous fan-out by
default — handlers run inline so failures bubble to the caller unless wrapped.
Use ``publish_safe`` for fire-and-forget semantics where a handler crash must
not affect the publisher (e.g. adaptation evaluation after a run log).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from threading import Lock
from typing import Callable, Type

from app.domain.events import DomainEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[DomainEvent], None]


class EventBus:
    """Synchronous in-process event bus."""

    def __init__(self) -> None:
        self._handlers: dict[Type[DomainEvent], list[EventHandler]] = defaultdict(list)
        self._lock = Lock()

    def subscribe(self, event_type: Type[DomainEvent], handler: EventHandler) -> None:
        with self._lock:
            self._handlers[event_type].append(handler)

    def publish(self, event: DomainEvent) -> None:
        """Dispatch ``event`` to all handlers; propagates the first exception."""
        for handler in self._handlers_for(type(event)):
            handler(event)

    def publish_safe(self, event: DomainEvent) -> None:
        """Dispatch ``event`` to all handlers; swallows + logs handler errors.

        Use when the publisher should never be blocked by a handler failure
        (analytics, adaptive recalc, etc.).
        """
        for handler in self._handlers_for(type(event)):
            try:
                handler(event)
            except Exception:
                logger.warning(
                    "Event handler %r failed for %s",
                    handler,
                    type(event).__name__,
                    exc_info=True,
                )

    def _handlers_for(self, event_type: Type[DomainEvent]) -> list[EventHandler]:
        with self._lock:
            handlers: list[EventHandler] = []
            for registered_type, registered_handlers in self._handlers.items():
                if issubclass(event_type, registered_type):
                    handlers.extend(registered_handlers)
            return handlers

    def clear(self) -> None:
        """Reset all subscriptions (test helper)."""
        with self._lock:
            self._handlers.clear()


# Module-level shared bus. Most callers should publish via this rather than
# constructing their own — handlers wire up to this single instance.
event_bus = EventBus()
