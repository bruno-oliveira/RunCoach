"""In-memory cache for Strava sync results with TTL."""

import time
from typing import Dict, Optional, Any


class StravaSyncCache:
    """
    Simple in-memory cache for Strava sync results per user session.

    Cache key format: f"{user_id}:{days_back}"
    TTL: 2 hours (7200 seconds)
    """

    TTL_SECONDS = 7200  # 2 hours

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _make_key(self, user_id: str, days_back: Optional[int]) -> str:
        """Create cache key from user_id and days_back."""
        period = str(days_back) if days_back is not None else "all"
        return f"{user_id}:{period}"

    def get(self, user_id: str, days_back: Optional[int]) -> Optional[Dict[str, Any]]:
        """
        Get cached sync result if it exists and hasn't expired.

        Returns:
            Cached data dict if found and valid, None otherwise.
        """
        key = self._make_key(user_id, days_back)
        entry = self._cache.get(key)

        if entry is None:
            return None

        # Check if expired
        if time.time() - entry["timestamp"] > self.TTL_SECONDS:
            del self._cache[key]
            return None

        return entry["data"]

    def set(self, user_id: str, days_back: Optional[int], data: Dict[str, Any]) -> None:
        """
        Store sync result in cache with current timestamp.

        Args:
            user_id: User ID
            days_back: Number of days back synced (None for all time)
            data: Sync result dict to cache
        """
        key = self._make_key(user_id, days_back)
        self._cache[key] = {
            "data": data,
            "timestamp": time.time()
        }

    def invalidate(self, user_id: str, days_back: Optional[int] = None) -> None:
        """
        Invalidate cache entry for specific user and period.

        Args:
            user_id: User ID
            days_back: If provided, invalidate specific period. If None, invalidate all periods for user.
        """
        if days_back is not None:
            key = self._make_key(user_id, days_back)
            self._cache.pop(key, None)
        else:
            # Invalidate all entries for this user
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(f"{user_id}:")]
            for key in keys_to_delete:
                del self._cache[key]

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()


# Global singleton instance
_strava_cache = StravaSyncCache()


def get_strava_cache() -> StravaSyncCache:
    """Get the global Strava cache instance."""
    return _strava_cache
