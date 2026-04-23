"""Application middleware configuration."""

import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings

_CSRF_EXEMPT = {"/api/auth/google", "/api/auth/logout", "/health"}
_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def set_anonymous_user_id_cookie(request: Request, call_next):
    """Set anonymous_user_id cookie if not present and add it to request state."""
    anonymous_user_id = request.cookies.get("anonymous_user_id")
    generated_new_id = False

    if not anonymous_user_id:
        anonymous_user_id = str(uuid.uuid4())
        generated_new_id = True

    request.state.anonymous_user_id = anonymous_user_id
    request.state.generated_new_anonymous_id = generated_new_id

    response = await call_next(request)

    if generated_new_id:
        response.set_cookie(
            key="anonymous_user_id",
            value=anonymous_user_id,
            max_age=settings.anonymous_cookie_max_age,
            httponly=True,
            samesite="lax",
            secure=not settings.debug,
        )

    return response


async def csrf_protection(request: Request, call_next):
    """Reject state-changing API requests without application/json Content-Type.

    Browsers cannot send application/json cross-origin without a CORS preflight,
    so requiring this header on POST/PUT/PATCH/DELETE prevents cross-site form
    submissions from reaching cookie-authenticated endpoints.
    """
    if (
        request.method in _STATE_CHANGING_METHODS
        and request.url.path.startswith("/api/")
        and request.url.path not in _CSRF_EXEMPT
    ):
        content_length = request.headers.get("content-length", "0")
        has_body = content_length != "0"
        if has_body:
            content_type = request.headers.get("content-type", "")
            if "application/json" not in content_type and "multipart/form-data" not in content_type:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Invalid Content-Type"},
                )

    return await call_next(request)
