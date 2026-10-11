"""Which language the current request is in.

The language toggle lives in the browser (``localStorage``), so the server only
learns it when the browser says so: ``X-Lang`` on API calls, the ``rc_lang``
cookie on page navigations — the same two channels the timezone travels on, and
bound to a ``ContextVar`` for the same reason. Work with no request around it
(the daily sweep, a webhook) reads the runner's stored ``users.language``
instead and passes it explicitly.
"""

from contextvars import ContextVar, Token

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "pt")

_request_language: ContextVar[str | None] = ContextVar("request_language", default=None)


def normalize_language(value: str | None) -> str | None:
    """Return a supported language code, or ``None`` when ``value`` is not one.

    Accepts a regional tag (``pt-PT``, ``pt_BR``) and keeps only the language.
    """
    if not value:
        return None
    code = value.strip().lower().replace("_", "-").split("-", 1)[0]
    return code if code in SUPPORTED_LANGUAGES else None


def set_request_language(value: str | None) -> Token:
    """Bind the runner's language for the current request context."""
    return _request_language.set(normalize_language(value))


def reset_request_language(token: Token) -> None:
    """Restore the previous language binding (call in ``finally``)."""
    _request_language.reset(token)


def request_language() -> str:
    """The active language, falling back to English."""
    return _request_language.get() or DEFAULT_LANGUAGE


def stated_request_language() -> str | None:
    """The language this request named, or ``None`` when it named none.

    Distinct from :func:`request_language` so that a request with no cookie
    (a webhook, an API client) cannot overwrite a stored Portuguese with the
    English default.
    """
    return _request_language.get()
