# RunCoach Caching Implementation Plan

## Overview
Implement comprehensive caching strategy to improve app speed by 50-70% and minimize loading times and network usage. This plan combines all Phase 1 quick wins with Phase 2 cachetools integration for maximum impact.

## Expected Performance Improvements
- `/generate-plan`: 2-5s → 0.8-2s (60-75% faster)
- `/download-pdf/{plan_id}`: 3-7s → 0.1-0.5s (90%+ faster on cache hit)
- `/my-plans`: 0.5-1s → 0.2-0.4s (50-70% faster)
- `/api/auth/google`: 0.3-0.8s → 0.1-0.3s (60-70% faster)
- Page loads (returning users): 50% reduction via static asset caching
- Memory usage: +15-25MB (well within 256MB Fly.io instance)

## Implementation Steps

### 1. Add Dependencies
**File:** `requirements.txt`
- Add `cachetools==5.3.2` for TTL and LRU caching

### 2. MealDatabase Singleton (HIGHEST IMPACT)
**Problem:** Loads 310KB of JSON (10,897 lines) on every nutrition/recipe request

**Files to modify:**
- `app/meal_database.py` - Add `@lru_cache` singleton pattern
- `app/core/nutrition_engine.py:10` - Use singleton getter instead of `MealDatabase()`
- `app/routers/recipes.py` - Use singleton getter

**Implementation:**
```python
# app/meal_database.py
from functools import lru_cache

@lru_cache(maxsize=1)
def get_meal_database() -> MealDatabase:
    """Get singleton MealDatabase instance (cached)."""
    return MealDatabase()

# Update all callers to use get_meal_database()
```

**Impact:** Eliminates 310KB JSON loading on every request, ~50-100ms improvement

### 3. Google OAuth Key Caching
**Problem:** Fetches Google's public keys via HTTPS on every authentication request

**File to modify:**
- `app/auth_service.py:46-50` - Add class-level cache with 1-hour TTL

**Implementation:**
```python
class AuthService:
    _cert_cache: Optional[Dict] = None
    _cert_cache_time: Optional[datetime] = None
    _cert_cache_ttl = timedelta(hours=1)

    async def _get_google_certs(self) -> dict:
        """Get Google's public keys with 1-hour cache."""
        now = datetime.utcnow()

        if (self._cert_cache and self._cert_cache_time and
            now - self._cert_cache_time < self._cert_cache_ttl):
            return self._cert_cache

        # Fetch from Google and update cache
        async with httpx.AsyncClient() as client:
            response = await client.get(self.google_cert_url)
            certs = response.json()
            AuthService._cert_cache = certs
            AuthService._cert_cache_time = now
            return certs
```

**Impact:** Eliminates HTTPS call to Google on 99% of auth requests, ~100-300ms improvement

### 4. PDF Filesystem Caching
**Problem:** Regenerates PDFs from scratch on every download (ReportLab is CPU-intensive)

**File to modify:**
- `app/core/pdf_generator.py:93-149` - Add filesystem cache with hash-based keys

**Implementation:**
```python
class PDFGenerator:
    def __init__(self, cache_dir: str = "./pdf_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

    def _get_cache_key(self, plan_data: list, training_plan) -> str:
        plan_str = json.dumps(plan_data, sort_keys=True)
        content_hash = hashlib.md5(plan_str.encode()).hexdigest()
        return f"{training_plan.id}_{content_hash}.pdf"

    def generate_pdf(self, plan_data: list, training_plan) -> str:
        cache_key = self._get_cache_key(plan_data, training_plan)
        cache_path = self.cache_dir / cache_key

        if cache_path.exists():
            logger.info(f"Using cached PDF: {cache_key}")
            return str(cache_path)

        # Generate PDF (existing logic)...
        # Move to cache and return path
```

**Impact:** 90%+ cache hit rate, reduces 2-5 second generation to <100ms

**Cleanup:** Add background job to delete PDFs older than 30 days or when cache exceeds 100MB

### 5. Static Asset Cache Headers
**Problem:** No cache headers on CSS/JS files (~47KB), browsers re-fetch on every page load

**File to modify:**
- `app/main.py:47` - Replace StaticFiles with custom CachedStaticFiles

**Implementation:**
```python
from fastapi.staticfiles import StaticFiles as BaseStaticFiles

class CachedStaticFiles(BaseStaticFiles):
    def __init__(self, *args, cache_max_age: int = 86400, **kwargs):
        self.cache_max_age = cache_max_age
        super().__init__(*args, **kwargs)

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = f"public, max-age={self.cache_max_age}"
        return response

# Replace line 47:
app.mount("/static", CachedStaticFiles(
    directory="app/static",
    cache_max_age=86400  # 24 hours
), name="static")
```

**Impact:** Eliminates 47KB+ transfers on repeat visits, ~200-500ms improvement

### 6. Database Indexes
**Problem:** No indexes on frequently queried columns (user_id, date, foreign keys)

**Files to modify:**
- `app/models/run_log.py` - Add indexes on user_id, date, training_plan_id
- `app/models/weekly_plan.py` - Add index on training_plan_id
- `app/models/daily_workout.py` - Add index on weekly_plan_id
- `app/models/training_plan.py` - Add index on user_id

**Implementation:**
```python
# Example for app/models/run_log.py
from sqlalchemy import Index

class RunLog(Base):
    __tablename__ = "run_logs"
    # ... existing columns ...

    __table_args__ = (
        Index('idx_run_log_user_id', 'user_id'),
        Index('idx_run_log_date', 'date'),
        Index('idx_run_log_user_date', 'user_id', 'date'),
        Index('idx_run_log_training_plan', 'training_plan_id'),
    )
```

**Impact:** Reduces run log queries from O(n) to O(log n), ~50-200ms improvement on analytics queries

**Note:** Indexes auto-created on next deployment via `Base.metadata.create_all()` - no migration needed

### 7. Training Tips Module-Level Cache
**Problem:** 1,300+ lines of training tips loaded in memory on every plan generation

**File to modify:**
- `app/core/plan_generator.py:747-1061` - Extract to module-level constant

**Implementation:**
```python
# Move to top of file (before class definition)
TRAINING_TIP_DATABASE = {
    "foundation": [...],
    "routine": [...],
    # ... all 1,300+ lines of tips
}

class TrainingPlanGenerator:
    def _generate_training_tips(self, week_number: int, target_distance: float) -> List[str]:
        # Use TRAINING_TIP_DATABASE instead of creating dict
        selected_tips = []
        # ... selection logic ...
        return selected_tips
```

**Impact:** Eliminates repeated dictionary creation, ~5-10% improvement in plan generation

### 8. Nutrition Calculation Caching
**Problem:** Identical calculations repeated for same parameters

**File to modify:**
- `app/core/nutrition_engine.py:14-54` - Add `@lru_cache` to calculation function

**Implementation:**
```python
from functools import lru_cache

@lru_cache(maxsize=256)
def _calculate_nutrition_needs_cached(
    weekly_km: float,
    target_distance: float,
    body_weight: float
) -> tuple:
    """Pure function for calculating nutrition needs (cached)."""
    # Calculation logic
    return (calories, protein, fiber, carbs, fat)

class NutritionEngine:
    def calculate_nutrition_needs(self, weekly_km: float, target_distance: float, body_weight: float = 70):
        calories, protein, fiber, carbs, fat = _calculate_nutrition_needs_cached(
            weekly_km, target_distance, body_weight
        )
        return {"calories": calories, "protein": protein, ...}
```

**Impact:** Eliminates redundant calculations, ~5-10ms improvement per request

### 9. User Plans List Caching
**Problem:** Database queries on every "My Plans" page visit even when data unchanged

**File to modify:**
- `app/routers/plans.py:518-538` - Add TTLCache with 5-minute expiry

**Implementation:**
```python
from cachetools import TTLCache

# Module-level cache
user_plans_cache = TTLCache(maxsize=1000, ttl=300)  # 5 minutes

@router.get("/my-plans")
async def my_plans(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cache_key = f"plans_{current_user.id}"

    if cache_key in user_plans_cache:
        plans = user_plans_cache[cache_key]
    else:
        plans = db.query(TrainingPlan).filter(
            TrainingPlan.user_id == current_user.id
        ).order_by(TrainingPlan.created_at.desc()).all()
        user_plans_cache[cache_key] = plans

    return templates.TemplateResponse(...)

# Invalidate cache on plan creation (in create_plan endpoint)
user_plans_cache.pop(f"plans_{current_user.id}", None)
```

**Impact:** Reduces database queries for frequent viewers, ~50-150ms improvement

### 10. Database Batch Inserts
**Problem:** Individual INSERT statements in loops when saving weekly plans

**File to modify:**
- `app/services/plan_service.py:69-98` - Use `bulk_insert_mappings`

**Implementation:**
```python
def _save_weekly_plans(self, training_plan_id: str, plan_data: list):
    weekly_plans = []
    daily_workouts = []

    for week_data in plan_data:
        week_id = str(uuid.uuid4())
        weekly_plans.append({
            'id': week_id,
            'training_plan_id': training_plan_id,
            'week_number': week_data['week'],
            'total_km': week_data['total_km'],
            'workout_types': json.dumps(week_data.get('workout_types', {}))
        })

        for workout in week_data['workouts']:
            daily_workouts.append({
                'id': str(uuid.uuid4()),
                'weekly_plan_id': week_id,
                'day_number': workout['day'],
                # ... other fields
            })

    # Batch insert
    self.db.bulk_insert_mappings(WeeklyPlan, weekly_plans)
    self.db.bulk_insert_mappings(DailyWorkout, daily_workouts)
    self.db.commit()
```

**Impact:** Reduces INSERT operations from O(n) to O(1) per batch, ~100-300ms improvement for large plans

## Testing Strategy

### Unit Tests
- Add tests for cache hit/miss scenarios
- Verify MealDatabase singleton (test multiple calls return same instance)
- Test OAuth cert cache expiry and refresh
- Test PDF cache key generation and retrieval

### Integration Tests
- Load test plan generation with and without cache
- Measure PDF download latency (first vs cached)
- Verify static assets have correct cache headers (inspect response)
- Test user plans cache invalidation on create/update

### Performance Benchmarks
- Measure endpoint latencies before and after
- Track cache hit rates in logs
- Monitor memory usage (<100MB total)

## Deployment Checklist

1. **Add cachetools to requirements.txt**
2. **Update all model files with database indexes**
3. **Implement MealDatabase singleton** (meal_database.py, nutrition_engine.py, recipes.py)
4. **Add OAuth key caching** (auth_service.py)
5. **Implement PDF filesystem cache** (pdf_generator.py)
6. **Add CachedStaticFiles** (main.py)
7. **Extract training tips to module level** (plan_generator.py)
8. **Add nutrition calculation caching** (nutrition_engine.py)
9. **Add user plans list caching** (plans.py)
10. **Implement batch inserts** (plan_service.py)
11. **Create pdf_cache directory** (ensure it's in .gitignore)
12. **Add logging for cache hit rates**
13. **Test locally with existing test suite**
14. **Deploy to Fly.io staging** (test cache effectiveness)
15. **Monitor logs for errors and cache statistics**
16. **Deploy to production**

## Monitoring

### Log Cache Statistics
Add logging to track cache effectiveness:
```python
logger.info(f"MealDatabase cache hit - using singleton")
logger.info(f"OAuth certs cache hit - age: {cache_age}s")
logger.info(f"PDF cache hit: {cache_key}")
logger.info(f"User plans cache hit rate: {hits}/{total}")
```

### Metrics to Track
- Endpoint latencies (before/after comparison)
- Cache hit rates per cache type
- Memory usage trends
- PDF cache disk usage
- Database query times

## Rollback Plan

If issues arise:
1. **MealDatabase:** Remove `@lru_cache`, restore direct instantiation
2. **OAuth caching:** Remove cache logic, restore original httpx call
3. **PDF caching:** Remove cache check, always regenerate
4. **Static headers:** Restore original StaticFiles mount
5. **Database indexes:** Not easily reversible, but low risk (only improves performance)
6. **Cachetools changes:** Remove library and cache decorators

## Critical Files Summary

### Files to Modify (10 total)
1. `requirements.txt` - Add cachetools
2. `app/meal_database.py` - Singleton pattern
3. `app/core/nutrition_engine.py` - Use meal DB singleton, cache calculations
4. `app/routers/recipes.py` - Use meal DB singleton
5. `app/auth_service.py` - OAuth cert caching
6. `app/core/pdf_generator.py` - Filesystem cache
7. `app/main.py` - CachedStaticFiles
8. `app/core/plan_generator.py` - Extract training tips
9. `app/routers/plans.py` - User plans caching
10. `app/services/plan_service.py` - Batch inserts

### Model Files to Modify (4 total)
11. `app/models/run_log.py` - Add indexes
12. `app/models/weekly_plan.py` - Add indexes
13. `app/models/daily_workout.py` - Add indexes
14. `app/models/training_plan.py` - Add indexes

## Success Criteria
- ✅ `/generate-plan` latency reduced by >50%
- ✅ `/download-pdf` cache hit rate >90%
- ✅ Static assets load from browser cache on repeat visits
- ✅ Database queries use indexes (verify with EXPLAIN)
- ✅ Memory usage stays <100MB
- ✅ No increase in error rates
- ✅ Cache hit rates logged and monitored

## Future Enhancements (Not Included)
- Redis for distributed caching (when scaling beyond single instance)
- CDN for static assets (when traffic >5000 requests/day)
- PostgreSQL migration (when data >1GB)
- Asset versioning/fingerprinting
- Service workers for offline support
