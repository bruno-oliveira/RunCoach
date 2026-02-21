"""Tests for Strava sync cache."""

import time
import pytest
from app.services.strava_cache import StravaSyncCache


def test_cache_basic_set_get():
    """Test basic cache set and get operations."""
    cache = StravaSyncCache()
    cache.clear()

    user_id = "user123"
    days_back = 30
    data = {"synced": 5, "skipped": 10, "errors": []}

    # Set cache
    cache.set(user_id, days_back, data)

    # Get cache
    result = cache.get(user_id, days_back)
    assert result is not None
    assert result == data


def test_cache_different_periods():
    """Test cache differentiates between different periods."""
    cache = StravaSyncCache()
    cache.clear()

    user_id = "user123"

    data_30 = {"synced": 5, "skipped": 10, "errors": []}
    data_60 = {"synced": 8, "skipped": 15, "errors": []}

    cache.set(user_id, 30, data_30)
    cache.set(user_id, 60, data_60)

    assert cache.get(user_id, 30) == data_30
    assert cache.get(user_id, 60) == data_60


def test_cache_different_users():
    """Test cache differentiates between different users."""
    cache = StravaSyncCache()
    cache.clear()

    data_user1 = {"synced": 5, "skipped": 10, "errors": []}
    data_user2 = {"synced": 8, "skipped": 15, "errors": []}

    cache.set("user1", 30, data_user1)
    cache.set("user2", 30, data_user2)

    assert cache.get("user1", 30) == data_user1
    assert cache.get("user2", 30) == data_user2


def test_cache_expiration():
    """Test cache entries expire after TTL."""
    cache = StravaSyncCache()
    cache.clear()
    cache.TTL_SECONDS = 1  # Set short TTL for testing

    user_id = "user123"
    days_back = 30
    data = {"synced": 5, "skipped": 10, "errors": []}

    cache.set(user_id, days_back, data)

    # Should exist immediately
    assert cache.get(user_id, days_back) == data

    # Wait for expiration
    time.sleep(1.1)

    # Should be expired
    assert cache.get(user_id, days_back) is None


def test_cache_invalidate_specific():
    """Test invalidating specific cache entry."""
    cache = StravaSyncCache()
    cache.clear()

    user_id = "user123"
    data_30 = {"synced": 5, "skipped": 10, "errors": []}
    data_60 = {"synced": 8, "skipped": 15, "errors": []}

    cache.set(user_id, 30, data_30)
    cache.set(user_id, 60, data_60)

    # Invalidate 30 days
    cache.invalidate(user_id, 30)

    assert cache.get(user_id, 30) is None
    assert cache.get(user_id, 60) == data_60


def test_cache_invalidate_all_user():
    """Test invalidating all cache entries for a user."""
    cache = StravaSyncCache()
    cache.clear()

    user_id = "user123"
    data_30 = {"synced": 5, "skipped": 10, "errors": []}
    data_60 = {"synced": 8, "skipped": 15, "errors": []}

    cache.set(user_id, 30, data_30)
    cache.set(user_id, 60, data_60)

    # Invalidate all for user
    cache.invalidate(user_id)

    assert cache.get(user_id, 30) is None
    assert cache.get(user_id, 60) is None


def test_cache_none_days_back():
    """Test cache handles None days_back (all time)."""
    cache = StravaSyncCache()
    cache.clear()

    user_id = "user123"
    data = {"synced": 100, "skipped": 50, "errors": []}

    cache.set(user_id, None, data)

    result = cache.get(user_id, None)
    assert result == data

    # Should be different from 30 days
    assert cache.get(user_id, 30) is None


def test_cache_clear():
    """Test clearing entire cache."""
    cache = StravaSyncCache()
    cache.clear()

    cache.set("user1", 30, {"synced": 5})
    cache.set("user2", 60, {"synced": 10})

    cache.clear()

    assert cache.get("user1", 30) is None
    assert cache.get("user2", 60) is None
