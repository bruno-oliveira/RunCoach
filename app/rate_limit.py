"""Simple in-memory rate limiting for authentication endpoints."""

import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status

from app.infrastructure.config import settings


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _client_ip(self, request: Request) -> str:
        """Resolve the trusted client IP from X-Forwarded-For.

        The header chain reads ``client, hop1, hop2, ...``. With ``hops``
        trusted reverse-proxies in front of the app, the right-most trusted
        IP is at position ``-hops``; any IPs further left were sent by the
        client and must not be trusted (an attacker can inject extra IPs to
        try to split a rate-limit budget across spoofed entries).

        Falls back to ``request.client.host`` when the header is missing or
        the chain is shorter than ``hops``.
        """
        hops = settings.trusted_proxy_hops
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded and hops > 0:
            chain = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
            if len(chain) >= hops:
                return chain[-hops]
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
intervals_callback_limiter = RateLimiter(max_requests=5, window_seconds=60)
# Account deletion is a destructive op — cap retries from any single IP.
account_deletion_limiter = RateLimiter(max_requests=3, window_seconds=3600)
# Plan generation / PDF download are CPU-intensive; cap per-IP to avoid resource exhaustion.
plan_generation_limiter = RateLimiter(max_requests=5, window_seconds=60)
# FIT files are cheap to build and downloaded in batches (a week of workouts
# at a time), so they get their own, more generous budget than PDF/plan gen.
fit_download_limiter = RateLimiter(max_requests=30, window_seconds=60)
