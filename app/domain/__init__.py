"""Pure domain layer: events, repository interfaces, value objects.

Nothing in ``app.domain`` may import from ``app.infrastructure``,
``app.services``, ``app.models``, ``app.web.routers`` or any framework.
"""
