"""Request-scoped, user-local date/time helpers.

The app is deployed in a single region (Fly.io, UTC clock) while users live in
their own timezones. Every ``date.today()`` evaluated on the server therefore
drifts by up to a full day around midnight: an Amsterdam user (UTC+2) opening
the app at 00:30 local time would see *yesterday's* workout highlighted, log
readiness against the wrong date, and have "current week" flip a day late.

Fix: the web layer captures the browser's IANA timezone (``X-Timezone`` header
for API calls, ``rc_tz`` cookie for plain page navigations) into a
``ContextVar`` for the duration of the request. All "what day is it for this
user?" logic goes through :func:`local_today` instead of ``date.today()``.

This module is pure stdlib (``zoneinfo`` + ``contextvars``) so it lives in
``app/core`` and may be imported from any layer per the dependency rules.
Outside a request (scripts, startup tasks, tests that don't set a tz) it falls
back to UTC, matching the previous server-clock behaviour.
"""

from contextvars import ContextVar, Token
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_MAX_TZ_NAME_LEN = 64

_request_tz: ContextVar[Optional[ZoneInfo]] = ContextVar("request_tz", default=None)


def parse_timezone(name: Optional[str]) -> Optional[ZoneInfo]:
    """Validate an IANA timezone name; return a ``ZoneInfo`` or ``None``.

    Invalid, missing, or absurdly long names are rejected silently — callers
    fall back to UTC rather than failing the request over a bad header.
    """
    if not name:
        return None
    name = name.strip()
    if not name or len(name) > _MAX_TZ_NAME_LEN:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return None


def set_request_timezone(name: Optional[str]) -> Token:
    """Bind the user's timezone for the current request context."""
    return _request_tz.set(parse_timezone(name))


def reset_request_timezone(token: Token) -> None:
    """Restore the previous timezone binding (call in ``finally``)."""
    _request_tz.reset(token)


def request_timezone() -> timezone | ZoneInfo:
    """The active user timezone, falling back to UTC."""
    return _request_tz.get() or timezone.utc


def local_now() -> datetime:
    """Timezone-aware 'now' in the user's timezone (UTC fallback)."""
    return datetime.now(request_timezone())


def local_today() -> date:
    """Today's date as the user experiences it (UTC fallback).

    Use this instead of ``date.today()`` for anything user-facing: current
    training week, today's workout, readiness log dates, adherence windows.
    """
    return local_now().date()
