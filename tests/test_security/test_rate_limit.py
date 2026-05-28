"""Tests for the in-memory rate limiter's IP-resolution policy.

The right-most trusted hop in the X-Forwarded-For chain is the only IP
the limiter can trust; any IPs further left were sent by the client and
could be spoofed to split a rate-limit budget.
"""

from types import SimpleNamespace

import pytest

from app.infrastructure.config import settings
from app.rate_limit import RateLimiter


def _request(*, header=None, client_host="1.2.3.4"):
    headers = {}
    if header is not None:
        headers["x-forwarded-for"] = header
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host=client_host) if client_host else None,
    )


@pytest.fixture
def limiter():
    return RateLimiter(max_requests=2, window_seconds=60)


@pytest.fixture(autouse=True)
def _reset_hops():
    original = settings.trusted_proxy_hops
    try:
        yield
    finally:
        settings.trusted_proxy_hops = original


def test_missing_header_falls_back_to_request_client_host(limiter):
    settings.trusted_proxy_hops = 1
    assert limiter._client_ip(_request(header=None)) == "1.2.3.4"


def test_missing_header_and_no_client_returns_unknown(limiter):
    settings.trusted_proxy_hops = 1
    assert limiter._client_ip(_request(header=None, client_host=None)) == "unknown"


def test_single_ip_chain_with_one_hop_returns_that_ip(limiter):
    settings.trusted_proxy_hops = 1
    assert limiter._client_ip(_request(header="9.9.9.9")) == "9.9.9.9"


def test_chain_with_one_hop_returns_rightmost_trusted_ip(limiter):
    """An attacker who injects ``X-Forwarded-For: spoofed`` reaches the app
    via Fly.io's edge as ``real-client, spoofed``. With hops=1 we want the
    real (right-most) IP, not the spoofed one."""
    settings.trusted_proxy_hops = 1
    chain = "203.0.113.5, 198.51.100.42"
    assert limiter._client_ip(_request(header=chain)) == "198.51.100.42"


def test_chain_with_two_hops_returns_second_from_right(limiter):
    settings.trusted_proxy_hops = 2
    chain = "203.0.113.5, 198.51.100.42, 192.0.2.7"
    assert limiter._client_ip(_request(header=chain)) == "198.51.100.42"


def test_chain_shorter_than_hops_falls_back(limiter):
    """If the chain has fewer entries than the configured trust depth, the
    header can't be trusted at all — fall back to the socket peer."""
    settings.trusted_proxy_hops = 2
    assert limiter._client_ip(_request(header="9.9.9.9")) == "1.2.3.4"


def test_zero_hops_always_uses_request_client_host(limiter):
    """When the app sits directly on the network, X-Forwarded-For carries
    only attacker-supplied data and must be ignored."""
    settings.trusted_proxy_hops = 0
    assert limiter._client_ip(_request(header="9.9.9.9")) == "1.2.3.4"


def test_chain_with_whitespace_and_empty_entries_is_normalized(limiter):
    settings.trusted_proxy_hops = 1
    assert limiter._client_ip(_request(header="  10.0.0.1 ,  ,  10.0.0.2  ")) == (
        "10.0.0.2"
    )


def test_spoofed_left_ips_cannot_split_budget(limiter):
    """Two requests from the same trusted client but with different
    spoofed-left IPs should both hit the same bucket and trip the limit."""
    settings.trusted_proxy_hops = 1
    req1 = _request(header="spoof-1, 198.51.100.42")
    req2 = _request(header="spoof-2, 198.51.100.42")
    limiter.check(req1)
    limiter.check(req2)
    # The bucket is full after two hits; a third must 429.
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        limiter.check(_request(header="spoof-3, 198.51.100.42"))
    assert exc.value.status_code == 429
