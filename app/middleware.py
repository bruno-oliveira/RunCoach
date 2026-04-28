"""Application middleware configuration."""

import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings

_CSRF_EXEMPT = {"/api/auth/google", "/api/auth/logout", "/health"}
_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "X-XSS-Protection": "0",
}
if not settings.debug:
    _SECURITY_HEADERS["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )


def _cookie_secure() -> bool:
    return settings.force_secure_cookies and not settings.debug


async def security_headers(request: Request, call_next):
    """Add security headers to every response."""
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value
    return response


async def request_size_limit(request: Request, call_next):
    """Reject requests whose Content-Length exceeds the configured limit."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_request_body_bytes:
        return JSONResponse(
            status_code=413,
            content={"detail": "Request body too large"},
        )
    return await call_next(request)


_COOKIE_REQUIRED_PREFIXES = ("/generate-plan", "/generate-fitness-plan", "/api/")


async def set_anonymous_user_id_cookie(request: Request, call_next):
    """Set anonymous_user_id cookie if not present and add it to request state.

    The cookie is only created when the user interacts with plan generation
    or API endpoints — not on first page load — so that the tracking cookie
    is not set before the user has seen the cookie notice.
    """
    anonymous_user_id = request.cookies.get("anonymous_user_id")
    generated_new_id = False

    if not anonymous_user_id:
        anonymous_user_id = str(uuid.uuid4())
        generated_new_id = True

    request.state.anonymous_user_id = anonymous_user_id
    request.state.generated_new_anonymous_id = generated_new_id

    response = await call_next(request)

    if generated_new_id:
        path = request.url.path
        needs_cookie = any(path.startswith(p) for p in _COOKIE_REQUIRED_PREFIXES)
        if needs_cookie:
            response.set_cookie(
                key="anonymous_user_id",
                value=anonymous_user_id,
                max_age=settings.anonymous_cookie_max_age,
                httponly=True,
                samesite="lax",
                secure=_cookie_secure(),
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
