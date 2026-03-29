# Zero Mileage Plan Generation - Implementation Complete

## Problem Statement

When a user enters `0` weekly mileage, the current implementation:
1. Passes validation (line 214 in `schemas.py` has `current_km > 0` check)
2. Generates a plan using ideal peak values without beginner-appropriate progression
3. Does not distinguish between achievable goals (5K/10K) and unrealistic goals (Half Marathon, Marathon, Trail)

## Design Decisions

| Decision | Choice |
|----------|--------|
| Minimum weeks for Couch to 5K | **Enforce 8 weeks minimum** |
| 10K from zero approach | **Extension of Couch to 5K** (weeks 1-8 = 5K, weeks 9+ = 10K build) |
| Pace zones for beginners | **Skip** - no VDOT calculations, no pace targets |
| Workout descriptions | **Include detailed walk/run interval instructions** |

---

## Implementation Summary

### Files Modified

| File | Changes |
|------|---------|
| `app/exceptions.py` | Added `ZeroMileageUnsupportedException` |
| `app/schemas.py` | Updated `validate_current_mileage` with 0-mileage handling, 8-week minimum |
| `app/routers/plans.py` | Added exception handler for `ZeroMileageUnsupportedException` |
| `app/core/plan_generator.py` | Added routing to `BeginnerPlanGenerator` when `current_km == 0` |
| `app/core/beginner_plan_generator.py` | **NEW FILE** - Couch to 5K plan generator |
| `app/templates/index.html` | Added frontend JS validation, updated help text |
| `app/templates/plan.html` | Added beginner badge, run/walk interval display |
| `app/static/css/plan.css` | Added beginner plan styles |

---

## Couch to 5K Structure (8 weeks minimum)

| Week | Structure | Notes |
|------|-----------|-------|
| 1 | 1min run / 1.5min walk × 8 | "Week 1: Run 1 minute, Walk 1.5 minutes. Repeat 8 times (20 min total)." |
| 2 | 1.5min run / 2min walk × 6 | Total: 21 min |
| 3 | 3min run / 3min walk × 4 | Total: 24 min |
| 4 | 5min run / 3min walk × 4 | Total: 32 min |
| 5 | 8min run / 5min walk × 3 | Total: 39 min |
| 6 | 10min run / 3min walk × 3 | Total: 39 min |
| 7 | 15min run / 3min walk × 2 | Total: 36 min |
| 8 | 20min continuous run | "Week 8: Run 20 minutes continuously - you did it!" |

### 10K Extension (weeks 9+)

| Week | Structure |
|------|-----------|
| 9 | 25 min easy run |
| 10 | 30 min easy run |
| 11 | 35 min with 5 min tempo |
| 12+ | Progressive distance building to 10K |

---

## Test Cases

| Test | Input | Expected Result |
|------|-------|-----------------|
| 0 km + 5K + 8 weeks | Valid | Couch to 5K plan generated |
| 0 km + 5K + 6 weeks | Invalid | Error: minimum 8 weeks required |
| 0 km + 10K + 12 weeks | Valid | Couch to 5K + 10K extension |
| 0 km + Half Marathon | Invalid | Error: unsupported distance |
| 0 km + Marathon | Invalid | Error: unsupported distance |
| 0 km + Trail | Invalid | Error: unsupported distance |
| 5 km + 5K + 8 weeks | Valid | Standard plan (existing logic) |

---

## How to Test

1. **Start the server:**
   ```bash
   python3 -m uvicorn app.main:app --reload --port 8000
   ```

2. **Test valid beginner plan:**
   - Go to http://localhost:8000
   - Enter 0 for weekly mileage
   - Select 5K
   - Enter 8 weeks
   - Should generate Couch to 5K plan

3. **Test invalid distance:**
   - Enter 0 for weekly mileage
   - Select Half Marathon
   - Should show error message

4. **Test insufficient weeks:**
   - Enter 0 for weekly mileage
   - Select 5K
   - Enter 6 weeks
   - Should show error about minimum 8 weeks
