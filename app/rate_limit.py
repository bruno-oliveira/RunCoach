"""Rate limiting for authentication and other abuse-prone endpoints.

Counters live behind a :class:`RateLimitStore`. The default store is in-process
and in-memory, so the limits bound abuse against *one* machine — correct for
this deployment (Fly runs a single scale-to-zero machine, and a failed
readiness check drains it) but silently false the moment the app scales out:
two machines would each grant the full budget. Scaling out therefore needs a
genuinely shared store, and the seam exists so that swap is an injected
dependency rather than a rewrite of every call site — see
:func:`use_shared_store`.

A store backed by this app's own SQLite database would *not* qualify: Fly
attaches a volume to a single machine, so two machines do not share one file.
Such a store would look shared while granting each machine the full budget,
which is worse than an honest in-memory dict.

Each limiter namespaces its keys with its ``scope``, so one shared store can
hold every limiter's counters without mixing their budgets.
"""

import time
from threading import Lock
from typing import Optional, Protocol

from fastapi import HTTPException, Request, status

from app.infrastructure.config import settings

# Buckets for IPs that never come back are swept out every this many calls, so
# a long-lived machine does not retain one entry per IP that has ever called.
_SWEEP_EVERY = 256


class RateLimitStore(Protocol):
    """Where a limiter's hit timestamps live.

    Implemented in-process by :class:`InMemoryRateLimitStore`; swap in a shared
    backend (Redis, or any store both machines can reach) to keep the limits
    meaningful after scaling past one process.
    """

    def hit(self, key: str, *, max_requests: int, window_seconds: int) -> bool:
        """Record a hit for ``key`` and report whether it is still in budget.

        Must be atomic: deciding and recording happen in one step, or two
        concurrent callers can both pass a budget with one slot left.
        """
        ...

    def clear(self) -> None:
        """Forget every counter (tests, and an operator-visible reset)."""
        ...


class InMemoryRateLimitStore:
    """Per-process store: correct for one machine, blind across many."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._calls_since_sweep = 0
        self._lock = Lock()

    def _sweep(self, cutoff: float) -> None:
        """Drop buckets with nothing left in the window. Caller holds the lock.

        Without this the dict grew monotonically: every distinct key kept its
        list forever, including the single timestamp of an IP that called once
        months ago and never returned. Pruning the *current* key alone would not
        help — the abandoned ones are exactly the ones that never call again to
        trigger their own cleanup.
        """
        expired = [
            key for key, hits in self._hits.items() if not any(h > cutoff for h in hits)
        ]
        for key in expired:
            del self._hits[key]

    def hit(self, key: str, *, max_requests: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            self._calls_since_sweep += 1
            if self._calls_since_sweep >= _SWEEP_EVERY:
                self._calls_since_sweep = 0
                self._sweep(cutoff)

            timestamps = [t for t in self._hits.get(key, ()) if t > cutoff]
            if len(timestamps) >= max_requests:
                self._hits[key] = timestamps
                return False
            timestamps.append(now)
            self._hits[key] = timestamps
            return True

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()
            self._calls_since_sweep = 0


class RateLimiter:
    """Per-IP budget for one scope, backed by an injectable store."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        *,
        scope: str = "",
        store: Optional[RateLimitStore] = None,
    ):
        self._max = max_requests
        self._window = window_seconds
        # Keys are namespaced per limiter so that pointing several limiters at
        # one shared store does not let them spend each other's budget.
        self._scope = scope
        self._store: RateLimitStore = (
            store if store is not None else InMemoryRateLimitStore()
        )

    def use_store(self, store: RateLimitStore) -> None:
        """Point this limiter at a different backend (see ``use_shared_store``)."""
        self._store = store

    def clear(self) -> None:
        """Forget every counter for this limiter."""
        self._store.clear()

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
        key = f"{self._scope}:{ip}" if self._scope else ip
        if not self._store.hit(
            key, max_requests=self._max, window_seconds=self._window
        ):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )


_LIMITERS: list[RateLimiter] = []


def _limiter(scope: str, *, max_requests: int, window_seconds: int) -> RateLimiter:
    """Build a module-level limiter and register it for store swapping."""
    limiter = RateLimiter(max_requests, window_seconds, scope=scope)
    _LIMITERS.append(limiter)
    return limiter


def use_shared_store(store: RateLimitStore) -> None:
    """Point every module-level limiter at ``store``.

    Call this once at startup when the app runs more than one process — without
    it each process grants the full budget independently. Every process must be
    given a store they all reach, and each limiter keeps its own key namespace,
    so one store holds every limiter's counters without mixing their budgets.
    """
    for limiter in _LIMITERS:
        limiter.use_store(store)


auth_limiter = _limiter("auth", max_requests=10, window_seconds=60)
intervals_callback_limiter = _limiter(
    "intervals_callback", max_requests=5, window_seconds=60
)
# Account deletion is a destructive op — cap retries from any single IP.
account_deletion_limiter = _limiter(
    "account_deletion", max_requests=3, window_seconds=3600
)
# Plan generation / PDF download are CPU-intensive; cap per-IP to avoid resource exhaustion.
plan_generation_limiter = _limiter("plan_generation", max_requests=5, window_seconds=60)
# FIT files are cheap to build and downloaded in batches (a week of workouts
# at a time), so they get their own, more generous budget than PDF/plan gen.
fit_download_limiter = _limiter("fit_download", max_requests=30, window_seconds=60)
# Pushing a workout to Intervals.icu hits their API; keep it generous enough to
# send a week of workouts one tap at a time, but capped to avoid abuse.
intervals_push_limiter = _limiter("intervals_push", max_requests=30, window_seconds=60)
# Syncing pulls from Intervals.icu's API. Each sync is a couple of calls, and a
# real "check for new runs" tap happens a handful of times a day at most — cap
# per-IP so an accidental polling loop (or abuse) can't hammer their API.
intervals_sync_limiter = _limiter("intervals_sync", max_requests=12, window_seconds=60)
# Registering a push subscription is a row per call; a test push is a real
# outbound request to Apple/Google/Mozilla on the runner's behalf.
push_subscribe_limiter = _limiter("push_subscribe", max_requests=20, window_seconds=60)
push_test_limiter = _limiter("push_test", max_requests=3, window_seconds=60)
# The check-in prefill may call Intervals.icu's wellness endpoint.
wellness_prefill_limiter = _limiter(
    "wellness_prefill", max_requests=12, window_seconds=60
)
