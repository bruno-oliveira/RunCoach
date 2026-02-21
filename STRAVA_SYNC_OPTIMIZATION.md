# Strava Sync Optimization

## Summary

Optimized Strava sync to only fetch recent activities by default and implement smart caching with dropdown-based filtering.

## Changes

### 1. Default Sync Period
- **Initial sync**: Changed from ALL activities to **30 days** (line 81 in `app/routers/strava.py`)
- **Manual sync**: Defaults to 30 days when no parameter provided
- **Nav sync button**: Now syncs 30 days instead of all time

### 2. Session-Based Caching (2h TTL)
- **New file**: `app/services/strava_cache.py` - In-memory cache with 2-hour TTL
- **Cache key format**: `{user_id}:{days_back}` (e.g., "user123:30")
- **Cache operations**:
  - `get()` - Retrieve cached result if valid
  - `set()` - Store result with timestamp
  - `invalidate()` - Clear specific or all entries for user
  - `clear()` - Clear entire cache

### 3. Analytics Page Integration
- **Period dropdown**: Already existed in UI (30, 60, 90, 365 days, All time)
- **Auto-sync on period change**: When user switches dropdown, automatically syncs Strava for that period if:
  - Strava is connected
  - Period is not "All time" (to avoid expensive full sync)
  - Data not already cached
- **Loading indicator**: Shows "Syncing Strava data..." spinner during sync
- **Default period**: Changed from 90 days to 30 days to match sync default

### 4. Smart Sync Behavior
- **Cache check first**: API checks cache before making Strava API call
- **Per-period caching**: Each time period (30, 60, 90, 365 days) cached separately
- **Per-user isolation**: Cache keys include user ID
- **Automatic reload**: After sync, analytics data is reloaded to show new runs

## Files Modified

1. `app/routers/strava.py`
   - Changed initial sync from `days_back=None` to `days_back=30`
   - Added cache dependency to `/sync` endpoint
   - Check cache before sync, store result after
   - Default `days_back` parameter to 30

2. `app/services/strava_cache.py` (NEW)
   - Session-based cache with 2h TTL
   - Per-user, per-period isolation
   - Automatic expiration

3. `app/dependencies.py`
   - Added `get_strava_cache()` dependency

4. `app/static/js/analytics_dashboard.js`
   - Added `checkStravaConnection()` method
   - Added `syncStravaPeriod()` method
   - Added `reloadRuns()` method
   - Added `showLoadingIndicator()` / `hideLoadingIndicator()` methods
   - Modified `init()` to sync 30 days on first load
   - Modified `bindPeriodSelector()` to sync on dropdown change
   - Changed default period from 90 to 30 days

5. `app/templates/analytics.html`
   - Changed default selected period from 90 to 30 days

6. `app/templates/components/nav.html`
   - Updated `syncStrava()` to use 30 days default
   - Added page reload after sync

7. `tests/test_strava_cache.py` (NEW)
   - Comprehensive tests for cache functionality
   - All 8 tests passing

## User Experience Flow

### First Visit to Analytics
1. User navigates to /analytics
2. If Strava connected, auto-syncs last 30 days (cached for 2h)
3. Shows analytics for last 30 days

### Changing Time Period
1. User selects "Last 60 days" from dropdown
2. Loading spinner appears: "Syncing Strava data..."
3. If not cached: Makes API call to `/api/strava/sync?days_back=60`
4. If cached: Uses cached result (no API call)
5. Reloads analytics data from database
6. Updates charts to show 60-day period
7. Hides loading spinner

### Subsequent Visits (within 2h)
1. Cache hit - no Strava API calls
2. Instant display of analytics

### After 2h TTL Expires
1. Cache miss - fresh sync from Strava
2. New 2h TTL starts

## Performance Benefits

- **Reduced API calls**: Cache prevents redundant Strava API requests
- **Faster initial load**: 30 days vs all-time history
- **User-friendly**: Dropdown makes it clear what time period is synced
- **Smart caching**: Only syncs when switching to new, uncached period
- **Stale data protection**: 2h TTL ensures data freshness

## Testing

Run cache tests:
```bash
python3 -m pytest tests/test_strava_cache.py -v
```

All 8 tests passing:
- Basic set/get operations
- Different periods isolation
- Different users isolation
- TTL expiration
- Specific invalidation
- User-wide invalidation
- None (all-time) handling
- Cache clear

## Notes

- "All time" period does NOT trigger Strava sync to avoid expensive operations
- Cache is in-memory (resets on app restart)
- For production, consider Redis for persistent cache across instances
