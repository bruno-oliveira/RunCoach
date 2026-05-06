"""Simple in-memory rate limiting for authentication endpoints."""

import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def check(self, request: Request) -> None:
        ip = self._client_ip(request)
        now = time.monotonic()
        cutoff = now - self._window

        with self._lock:
            timestamps = self._hits[ip]
            self._hits[ip] = [t for t in timestamps if t > cutoff]
            if len(self._hits[ip]) >= self._max:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later.",
                )
            self._hits[ip].append(now)


auth_limiter = RateLimiter(max_requests=10, window_seconds=60)
strava_callback_limiter = RateLimiter(max_requests=5, window_seconds=60)
# Account deletion is a destructive op — cap retries from any single IP.
account_deletion_limiter = RateLimiter(max_requests=3, window_seconds=3600)
