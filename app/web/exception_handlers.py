"""Global exception handlers.

Centralizes translation of the domain exception hierarchy
(``RunCoachException``) into HTTP responses, so any endpoint that raises one
renders the friendly ``user_message``/``suggestion`` without each router
having to catch it. Routers that need bespoke HTML error pages (e.g. the plan
generation form flow) still catch locally; this is the JSON safety net for
everything else.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exceptions import (
    DatabaseException,
    PlanGenerationException,
    RunCoachException,
    UnverifiedEmailException,
    ValidationException,
)

logger = logging.getLogger(__name__)


def _status_for(exc: RunCoachException) -> int:
    """Map a domain exception to an HTTP status code."""
    if isinstance(exc, UnverifiedEmailException):
        return 403
    if isinstance(exc, ValidationException):
        return 400
    if isinstance(exc, (DatabaseException, PlanGenerationException)):
        return 500
    return 400


def register_exception_handlers(app: FastAPI) -> None:
    """Register domain exception handlers on the application."""

    @app.exception_handler(RunCoachException)
    async def _handle_runcoach_exception(
        request: Request, exc: RunCoachException
    ) -> JSONResponse:
        status_code = _status_for(exc)
        if status_code >= 500:
            logger.exception("Unhandled %s on %s", type(exc).__name__, request.url.path)
        body: dict[str, str] = {
            "detail": exc.user_message,
            "error_type": type(exc).__name__,
        }
        suggestion = getattr(exc, "suggestion", None)
        if suggestion:
            body["suggestion"] = suggestion
        return JSONResponse(status_code=status_code, content=body)
