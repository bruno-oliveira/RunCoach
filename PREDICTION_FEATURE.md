# Race Predictor Feature Specification

## Overview

The Race Predictor feature provides runners with performance predictions based on their current fitness level (VDOT), enabling goal setting and training plan validation.

**Core value proposition:** Help runners answer "What can I race?" based on "What have I raced?" — surfacing equivalent performance predictions and fitness trends.

---

## Current State: VDOT Infrastructure

### What Already Exists

The app already has a robust VDOT infrastructure built on Jack Daniels' running formula:

| Component | Location | Purpose |
|-----------|----------|---------|
| `VDOTCalculator.calculate_vdot()` | `app/core/vdot_calculator.py` | Race → VDOT |
| `VDOTCalculator.get_pace_zones()` | `app/core/vdot_calculator.py` | VDOT → Training zones (E, M, T, I, R) |
| `VDOTCalculator.inject_paces_into_description()` | `app/core/vdot_calculator.py` | Workout descriptions with specific paces |
| VDOT in plan generation | `plan_generator.py`, `performance_plan_generator.py` | Personalize training paces |
| VDOT in PlanRequest | `schemas.py` | Optional race result input when creating plan |

### What's Missing

The app currently does **one-directional** VDOT calculation (race → VDOT → training paces). It lacks:

1. **Reverse calculation** — VDOT → predicted race times
2. **VDOT persistence** — storing calculated VDOT on run logs for historical tracking
3. **Trend analysis** — comparing VDOT over time from multiple races
4. **Gap analysis** — comparing predicted times against goal race targets
5. **API exposure** — endpoints to retrieve predictions
6. **User-facing display** — UI to show predictions and trends

---

## Feature Architecture

### 1. Database Layer

**New column on `run_logs`:**
```sql
ALTER TABLE run_logs ADD COLUMN vdot FLOAT;
```

- Nullable (existing runs remain valid)
- Populated automatically when `workout_type='race'` is logged
- Can be backfilled for existing race-type runs

**Rationale:** Minimal schema change. VDOT is derived data — no new entity needed.

---

### 2. Core Logic Extension

#### 2.1 Add to `vdot_calculator.py`

**New method — `predict_time_for_distance()`:**
```python
@staticmethod
def predict_time_for_distance(vdot: float, distance_km: float) -> int:
    """
    Predict race time for a given VDOT and distance.

    Args:
        vdot: Current fitness level (25-85)
        distance_km: Target race distance (5.0, 10.0, 21.1, 42.2)

    Returns:
        Predicted time in seconds
    """
```

**New method — `predict_times()`:**
```python
@staticmethod
def predict_times(vdot: float) -> Dict[str, Dict]:
    """
    Get predicted times for all standard race distances.

    Returns:
        {
            "5K": {"seconds": 1380, "formatted": "23:00"},
            "10K": {"seconds": 2880, "formatted": "48:00"},
            "half_marathon": {"seconds": 6300, "formatted": "1:45:00"},
            "marathon": {"seconds": 13500, "formatted": "3:45:00"},
        }
    """
```

**New method — `get_confidence_range()`:**
```python
@staticmethod
def get_confidence_range(vdot: float, distance_km: float) -> Dict[str, int]:
    """
    Get optimistic and pessimistic time estimates.

    Returns:
        {"optimistic": 1320, "pessimistic": 1440}  # ±~1 VO2max
    """
```

**Algorithm notes:**
- Uses Jack Daniels' equivalent performance formula (inverse of VDOT calculation)
- Daniels showed that VO2 cost scales predictably with distance
- Confidence range: ±1 VO2max unit (approximately ±5 sec/km variation)
- Validate distances: 5.0, 10.0, 21.0975, 42.195

---

#### 2.2 Helper Utilities

**New in `vdot_calculator.py`:**
```python
@staticmethod
def format_duration(seconds: int) -> str:
    """Format seconds as HH:MM:SS or MM:SS"""

@staticmethod
def validate_race_distance(distance_km: float) -> bool:
    """Check if distance is valid for prediction"""
```

---

### 3. Backend Service

**New file: `app/services/race_predictor_service.py`**

```python
class RacePredictorService:
    """Service for race predictions and VDOT trend analysis."""

    @staticmethod
    def get_predictions_for_user(user_id: str, db: Session) -> Dict[str, Any]
    """
    Get race predictions based on user's best recent VDOT.

    Returns:
        {
            "current_vdot": 52.3,
            "vdot_trend": "improving",  # improving | stable | declining
            "predictions": {
                "5K": {"seconds": 1380, "formatted": "23:00", "range": {...}},
                ...
            },
            "last_race": {"date": "2026-03-15", "distance": 10.0, "vdot": 52.3},
            "race_count": 3,
        }
    """

    @staticmethod
    def calculate_vdot_from_run(run: RunLog) -> Optional[float]:
        """Calculate VDOT from a race-type run."""

    @staticmethod
    def get_vdot_history(user_id: str, weeks: int = 12, db: Session) -> List[Dict]:
        """Get VDOT history from recent race runs for trend analysis."""

    @staticmethod
    def analyze_fitness_gap(
        current_vdot: float,
        target_distance: float,
        goal_time_seconds: int,
        db: Session
    ) -> Dict[str, Any]:
        """
        Analyze gap between current fitness and race goal.

        Returns:
            {
                "predicted_time": 13500,  # seconds
                "goal_time": 12600,
                "gap_seconds": 900,
                "gap_label": "6:00 off predicted",
                "vdot_required": 54.2,
                "feasible": True,
                "recommendation": "Your goal requires VDOT 54.2. Build fitness with threshold work.",
            }
        """
```

**VDOT Trend Calculation:**
- Look at VDOT values from races in last 12 weeks
- "improving": VDOT increased >0.5 from earliest to latest race
- "stable": VDOT within ±0.5
- "declining": VDOT decreased >0.5

**Best VDOT Selection:**
- Use best VDOT from last 12 weeks (not average)
- Rationale: fitness is about peak capability, not average

---

### 4. API Endpoints

**Add to existing `runs_router` (not new router):**

```
GET /api/runs/predictions
```

Response:
```json
{
    "current_vdot": 52.3,
    "vdot_trend": "improving",
    "predictions": {
        "5K": {
            "distance_km": 5.0,
            "seconds": 1380,
            "formatted": "23:00",
            "range": {"fast": "22:15", "slow": "23:45"}
        },
        "10K": {...},
        "half_marathon": {...},
        "marathon": {...}
    },
    "last_race": {
        "date": "2026-03-15",
        "distance_km": 10.0,
        "time": "48:30",
        "vdot": 52.3
    },
    "has_sufficient_data": true
}
```

```
GET /api/runs/predictions?target_distance=42.2
```

Response (gap analysis):
```json
{
    "target_distance": 42.2,
    "predicted_time": "3:45:00",
    "goal_time": null,
    "vdot_required_for_goal": null,
    "message": "Log a goal time to see gap analysis"
}
```

```
GET /api/runs/predictions?target_distance=42.2&goal_time=3:55:00
```

Response:
```json
{
    "target_distance": 42.2,
    "predicted_time": "3:45:00",
    "goal_time_seconds": 14100,
    "goal_time_formatted": "3:55:00",
    "gap_seconds": 600,
    "gap_formatted": "10:00 slower than predicted",
    "vdot_required_for_goal": 54.0,
    "feasible": true,
    "recommendation": "Your goal is ambitious but achievable. Focus on threshold work to bridge the gap."
}
```

---

### 5. Run Logging Integration

**Auto-calculate VDOT on race save:**
```python
# In runs_router.create_run_log()
if run_log.workout_type == 'race':
    vdot = VDOTCalculator.calculate_vdot(
        run_log.distance_km,
        run_log.duration_minutes * 60
    )
    new_run.vdot = vdot
```

**Note:** `workout_type='race'` must be added to validation. Currently valid types are: `easy`, `tempo`, `interval`, `long`, `hill`, `rest`.

---

### 6. Schema Updates

**Update `RunLogResponse` in `schemas.py`:**
```python
class RunLogResponse(RunLogBase):
    # ... existing fields ...
    vdot: Optional[float] = None  # New field
```

**Update `RunLogCreate` validation:**
```python
@field_validator("workout_type")
@classmethod
def validate_workout_type(cls, v: Optional[str]) -> Optional[str]:
    if v is not None:
        valid_types = ["easy", "tempo", "interval", "long", "hill", "rest", "race"]
        if v not in valid_types:
            raise ValueError(...)
    return v
```

---

### 7. UI Integration

#### 7.1 Analytics Dashboard (Primary Location)

Add a collapsible card at the bottom of the existing Analytics page:

```
┌─────────────────────────────────────────────────────────────────┐
│ ▶ Race Predictions                                      [Hide] │
├─────────────────────────────────────────────────────────────────┤
│  Your Current Fitness: VDOT 52.3 (Improving ↑)                  │
│                                                                 │
│  Predicted Race Times                                           │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐      │
│  │    5K       │    10K      │   Half      │   Marathon  │      │
│  │  23:00      │  48:00      │  1:45:00    │  3:45:00    │      │
│  │ 22:15-23:45 │ 47:00-49:00 │ 1:42-1:48   │ 3:38-3:52   │      │
│  └─────────────┴─────────────┴─────────────┴─────────────┘      │
│                                                                 │
│  Based on: 10K race on March 15 (48:30)                         │
│                                                                 │
│  [Compare with goal]  [Start training plan]                     │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**
- Only visible when user has ≥1 race-type run with VDOT
- Uses existing card/component styles from `analytics.css`
- Collapsible to avoid visual noise

#### 7.2 Run Logging Toast (Post-Save)

After saving a race-type run:

```
┌──────────────────────────────────────────────────────────────┐
│ 🎯 Race logged! Based on your performance:                  │
│                                                              │
│   5K: 23:00  •  10K: 48:00  •  Half: 1:45:00  •  Full: 3:45 │
│                                                              │
│                                          [Dismiss] [View]    │
└──────────────────────────────────────────────────────────────┘
```

**Implementation:**
- One-time display per session (sessionStorage flag)
- "View" opens Analytics dashboard at predictions section

#### 7.3 Performance Plan Page (Optional Enhancement)

On the plan generation page, show a small comparison:

```
┌─────────────────────────────────────────┐
│ Fitness Check                           │
│                                         │
│ Current VDOT: 52.3                      │
│ Goal requires: VDOT 54.0               │
│ Gap: 1.7 VDOT units                    │
│ Status: Challenging but achievable     │
└─────────────────────────────────────────┘
```

**Implementation:**
- Only shown when user has logged races AND is generating a plan
- Does not block plan generation

---

### 8. Retroactive Compatibility

#### 8.1 Backfill Script

```python
# scripts/backfill_race_vdot.py

def backfill_race_vdot():
    """Backfill VDOT for all existing race-type runs."""
    # Query all runs with workout_type='race' and no vdot
    # Calculate VDOT for each
    # Update vdot column
    pass
```

**Execution:**
```bash
python scripts/backfill_race_vdot.py
```

**Safety:**
- Idempotent (can be run multiple times)
- Only updates runs without existing vdot
- Logs progress and any errors

#### 8.2 Graceful Degradation

| Scenario | Behavior |
|----------|----------|
| No race logged | Predictions section hidden on Analytics |
| Race logged but no VDOT calculated | Show "Calculating..." then result |
| Old races (>12 weeks) | Use oldest within 12 weeks, show warning |
| User deletes all race data | Predictions disappear gracefully |
| VDOT calculation fails | Log error, hide predictions |

---

### 9. Edge Cases

#### 9.1 Multiple Races

- Use best VDOT from last 12 weeks
- Show both "best recent" and "latest" VDOT if they differ >1.0

#### 9.2 VDOT Drift

- If latest race VDOT is significantly different from best (declining), show warning
- Suggest reviewing recent training load

#### 9.3 Very Fast/Slow Runners

- VDOT clamped to 25-85 in calculator
- Predictions for extreme VDOTs show confidence message

#### 9.4 Invalid Race Data

- If distance or duration seems unrealistic (e.g., 42km in 1 hour), skip VDOT calculation
- Log for debugging but don't fail silently

---

### 10. Performance Considerations

- Predictions endpoint: <50ms response time
- Cache VDOT calculations on run log (don't recalculate on every request)
- Analytics dashboard: load predictions async after main data

---

### 11. Implementation Order

| Step | Task | Files Changed |
|------|------|---------------|
| 1 | Add `race` to workout_type validation | `schemas.py` |
| 2 | Add `vdot` column migration | `main.py` |
| 3 | Add prediction methods to VDOTCalculator | `vdot_calculator.py` |
| 4 | Create RacePredictorService | `race_predictor_service.py` (new) |
| 5 | Add API endpoint | `routers/runs.py` |
| 6 | Update RunLogResponse schema | `schemas.py` |
| 7 | Auto-calculate VDOT on race save | `routers/runs.py` |
| 8 | Create backfill script | `scripts/backfill_race_vdot.py` (new) |
| 9 | Run backfill on existing data | - |
| 10 | Add analytics dashboard card | `templates/analytics.html`, `static/css/analytics.css` |
| 11 | Add post-race toast | `templates/plan.html` (or relevant) |
| 12 | Update AGENTS.md | `AGENTS.md` |

---

### 12. Testing

#### Unit Tests
- `VDOTCalculator.predict_time_for_distance()` for all distances
- `VDOTCalculator.predict_times()` returns all 4 distances
- `RacePredictorService.get_predictions_for_user()` with mocked data
- Gap analysis edge cases

#### Integration Tests
- Race logged → VDOT calculated → predictions endpoint returns correct value
- Multiple races → trend correctly identified
- Backfill script updates existing runs

#### UI Tests
- Predictions card hidden when no race data
- Predictions card visible with race data
- Toast appears after race save

---

### 13. Metrics & Success Criteria

- Predictions visible for users with ≥1 race-type run
- Gap analysis accurate within ±30 seconds for predicted times
- No regression in plan generation times
- Backfill completes in <5 seconds for 10,000 runs
- API response <50ms p95

---

### 14. Future Enhancements (Out of Scope for V1)

- **Race comparison:** Compare two race results to see if fitness improved
- **Training load impact:** Show how current training affects predicted race times
- **Goal pacing strategy:** Break down goal race into pacing strategy
- **Strava integration:** Auto-detect race activities from Strava
- **Season planning:** Plan multiple races and track VDOT progression
- **Custom distances:** Allow prediction for non-standard distances (e.g., 8K)

---

### 15. Dependencies

- `vdot_calculator.py` — existing, no changes needed except new methods
- `schemas.py` — update RunLogResponse
- `runs_router.py` — add endpoint, update create_run_log
- `analytics.css` — existing, add card styles
- `analytics.html` — add predictions section

No new dependencies required.
