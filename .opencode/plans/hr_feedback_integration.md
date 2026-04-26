# HR Zone & Feedback Integration into Plan Adaptation

## Overview

Integrate **two new signals** into the adaptation multiplier calculation:
1. **HR Zone Deviation Signal** — penalizes when runner consistently trains above/below target HR zones
2. **RunFeedback Sentiment Signal** — consumes already-generated feedback warnings/positives as adaptation input

## Implementation Steps

### Step 1: Add `hr_zone_deviation` Column to RunLog Model

**File:** `app/models/run_log.py`

Add after line 40 (after `predicted_time_seconds`):
```python
hr_zone_deviation = Column(Integer, nullable=True)
```

This stores the numeric zone deviation (e.g., +1 means 1 zone above target, -1 means 1 zone below).

---

### Step 2: Create Database Migration

Run Alembic migration to add the column:
```bash
cd /Users/boliveira/Documents/RunCoach
alembic revision --autogenerate -m "add hr_zone_deviation to run_logs"
alembic upgrade head
```

---

### Step 3: Add `compute_hr_zone_deviation()` Function

**File:** `app/core/coaching/hr_feedback.py`

Add new function after `hr_zone_feedback()`:

```python
def compute_hr_zone_deviation(run_log, planned_workout, hr_zones) -> Optional[int]:
    """Compute numeric HR zone deviation for a run.
    
    Returns:
        Signed integer: actual_zone - target_zone
        None if HR data or zones unavailable.
    """
    if not hr_zones or not run_log.avg_heart_rate:
        return None
    
    actual_zone = HRZoneCalculator.classify_hr(
        run_log.avg_heart_rate, hr_zones
    )
    
    target_zone = None
    if planned_workout and hasattr(planned_workout, "hr_zone_target"):
        target_zone = planned_workout.hr_zone_target
    if not target_zone:
        wtype = (
            run_log.workout_type or "easy"
        ).lower()
        target_zone = HRZoneCalculator.get_workout_zone(wtype)
    
    return actual_zone - target_zone
```

---

### Step 4: Modify `feedback_service.py` to Store Deviation

**File:** `app/services/feedback_service.py`

In `generate_and_store()` method, after line 62 (after `fb = CoachingFeedbackEngine.generate_feedback(...)`), add:

```python
# Compute and store numeric HR zone deviation on the run log
from app.core.coaching.hr_feedback import compute_hr_zone_deviation

hr_deviation = compute_hr_zone_deviation(run_log, planned_workout, hr_zones)
if hr_deviation is not None:
    run_log.hr_zone_deviation = hr_deviation
    db.commit()
```

---

### Step 5: Create HRZoneAnalyzer Module

**File:** `app/services/adaptation/hr_zone_analyzer.py` (NEW)

```python
"""HR zone analyzer — aggregate HR zone data for adaptation signals."""

from typing import List, Optional, Dict, Any
from datetime import date

from app.core.training.hr_zone_calculator import HRZoneCalculator
from app.utils import to_date as _to_date


class HRZoneAnalyzer:
    """Analyze HR zone adherence across a set of runs."""

    @staticmethod
    def analyze_runs(
        runs: List,
        hr_zones: list[dict],
        *,
        recency_weight_fn=None,
        today=None,
    ) -> Dict[str, Any]:
        """Analyze HR zone adherence for a list of runs.
        
        Args:
            runs: List of RunLog instances with avg_heart_rate
            hr_zones: Zone list from HRZoneCalculator.calculate_zones()
            recency_weight_fn: Function to weight by recency
            today: Reference date for weighting
            
        Returns:
            Dict with adherence metrics and trend.
        """
        if not hr_zones or not runs:
            return {
                "adherence_rate": 1.0,
                "avg_deviation": 0.0,
                "avg_abs_deviation": 0.0,
                "high_zone_run_count": 0,
                "trend": "insufficient_data",
                "per_type_adherence": {},
                "run_count": 0,
            }

        deviations = []
        weighted_dev_sum = 0.0
        weighted_abs_dev_sum = 0.0
        weight_sum = 0.0
        on_target_count = 0
        high_zone_count = 0
        
        from collections import defaultdict
        per_type_on_target: Dict[str, int] = defaultdict(int)
        per_type_total: Dict[str, int] = defaultdict(int)

        for run in runs:
            if not run.avg_heart_rate:
                continue
            
            actual_zone = HRZoneCalculator.classify_hr(
                run.avg_heart_rate, hr_zones
            )
            
            target_zone = None
            if hasattr(run, 'daily_workout') and run.daily_workout:
                if hasattr(run.daily_workout, 'hr_zone_target'):
                    target_zone = run.daily_workout.hr_zone_target
            
            if not target_zone:
                wtype = (run.workout_type or "easy").lower()
                target_zone = HRZoneCalculator.get_workout_zone(wtype)
            
            deviation = actual_zone - target_zone
            
            run_date = _to_date(run.date) if run.date else today
            weight = recency_weight_fn(run_date) if recency_weight_fn else 1.0
            
            deviations.append((deviation, weight, run.workout_type or "easy"))
            weighted_dev_sum += deviation * weight
            weighted_abs_dev_sum += abs(deviation) * weight
            weight_sum += weight
            
            if deviation == 0:
                on_target_count += 1
                per_type_on_target[run.workout_type or "easy"] += 1
            
            if deviation >= 2:
                high_zone_count += 1
            
            per_type_total[run.workout_type or "easy"] += 1

        if weight_sum == 0:
            return {
                "adherence_rate": 1.0,
                "avg_deviation": 0.0,
                "avg_abs_deviation": 0.0,
                "high_zone_run_count": 0,
                "trend": "insufficient_data",
                "per_type_adherence": {},
                "run_count": 0,
            }

        avg_deviation = weighted_dev_sum / weight_sum
        avg_abs_deviation = weighted_abs_dev_sum / weight_sum
        adherence_rate = on_target_count / len(deviations) if deviations else 1.0
        
        # Compute trend
        trend = HRZoneAnalyzer._compute_trend(deviations)
        
        # Per-type adherence
        per_type_adherence = {}
        for wtype in per_type_total:
            total = per_type_total[wtype]
            on_target = per_type_on_target.get(wtype, 0)
            per_type_adherence[wtype] = on_target / total if total > 0 else 1.0

        return {
            "adherence_rate": round(adherence_rate, 2),
            "avg_deviation": round(avg_deviation, 2),
            "avg_abs_deviation": round(avg_abs_deviation, 2),
            "high_zone_run_count": high_zone_count,
            "trend": trend,
            "per_type_adherence": per_type_adherence,
            "run_count": len(deviations),
        }

    @staticmethod
    def _compute_trend(deviations: List[tuple]) -> str:
        """Compute HR zone deviation trend.
        
        Args:
            deviations: List of (deviation, weight, workout_type) tuples
            
        Returns:
            "improving", "degrading", "stable", or "insufficient_data"
        """
        if len(deviations) < 4:
            return "insufficient_data"
        
        mid_point = len(deviations) // 2
        first_half = [d[0] for d in deviations[:mid_point]]
        second_half = [d[0] for d in deviations[mid_point:]]
        
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        
        diff = second_avg - first_avg
        
        if diff > 0.5:
            return "degrading"  # Deviation increasing (getting worse)
        elif diff < -0.5:
            return "improving"  # Deviation decreasing (getting better)
        return "stable"
```

---

### Step 6: Modify `signal_computer.py`

**File:** `app/services/adaptation/signal_computer.py`

#### 6a. Update Phase Weights

Replace lines 11-16 with:
```python
_PHASE_WEIGHTS = {
    "base":   (0.40, 0.20, 0.20, 0.12, 0.08),  # vol, effort, compl, hr, feedback
    "build":  (0.35, 0.22, 0.18, 0.15, 0.10),
    "peak":   (0.30, 0.22, 0.18, 0.18, 0.12),
    "taper":  (0.12, 0.22, 0.25, 0.25, 0.16),
}
```

#### 6b. Add Imports

Add after line 8:
```python
from app.models import RunFeedback
from app.services.adaptation.hr_zone_analyzer import HRZoneAnalyzer
```

#### 6c. Update Function Signature

Modify `compute_adjustment_signals()` signature (line 40-51) to add:
```python
    hr_zones: Optional[list[dict]] = None,
    run_feedback_list: Optional[List] = None,
```

#### 6d. Add HR Zone Signal Computation

Add after line 121 (after effort_trend computation):

```python
    # HR Zone Signal
    hr_result = HRZoneAnalyzer.analyze_runs(
        all_plan_runs,
        hr_zones,
        recency_weight_fn=recency_weight_fn,
        today=today,
    )
    
    avg_zone_deviation = hr_result["avg_deviation"]
    hr_zone_adherence = hr_result["adherence_rate"]
    hr_zone_trend = hr_result["trend"]
    
    # Map deviation to factor
    if avg_zone_deviation >= 1.5:
        hr_zone_factor = 0.90
    elif avg_zone_deviation >= 1.0:
        hr_zone_factor = 0.95
    elif avg_zone_deviation <= -1.0:
        hr_zone_factor = 1.05
    elif avg_zone_deviation <= -0.5:
        hr_zone_factor = 1.02
    else:
        hr_zone_factor = 1.0
    
    # If no HR data, distribute weight to other signals
    if hr_zones is None or hr_result["run_count"] == 0:
        hr_zone_factor = 1.0
        hr_zone_weight = 0.0
        # Redistribute weight proportionally
        total_other = volume_weight + effort_weight + completion_weight + feedback_weight
        if total_other > 0:
            scale = 1.0 + hr_zone_weight / total_other
            volume_weight *= scale
            effort_weight *= scale
            completion_weight *= scale
            feedback_weight *= scale
```

#### 6e. Add Feedback Sentiment Signal

Add after HR zone signal computation:

```python
    # Feedback Sentiment Signal
    if run_feedback_list and len(run_feedback_list) > 0:
        warning_weighted = 0.0
        positive_weighted = 0.0
        total_weighted = 0.0
        
        for fb in run_feedback_list:
            run_date = None
            for run in all_plan_runs:
                if run.id == fb.run_log_id:
                    run_date = _to_date(run.date) if run.date else today
                    break
            
            if run_date:
                w = recency_weight_fn(run_date)
            else:
                w = 1.0
            
            total_weighted += w
            if fb.overall_sentiment == "warning":
                warning_weighted += w
            elif fb.overall_sentiment == "positive":
                positive_weighted += w
        
        if total_weighted > 0:
            warning_ratio = warning_weighted / total_weighted
            positive_ratio = positive_weighted / total_weighted
            
            if warning_ratio > 0.6:
                feedback_factor = 0.92
            elif warning_ratio > 0.4:
                feedback_factor = 0.96
            elif positive_ratio > 0.6:
                feedback_factor = 1.05
            elif positive_ratio > 0.4:
                feedback_factor = 1.02
            else:
                feedback_factor = 1.0
        else:
            feedback_factor = 1.0
            warning_ratio = 0.0
            positive_ratio = 0.0
    else:
        feedback_factor = 1.0
        warning_ratio = 0.0
        positive_ratio = 0.0
```

#### 6f. Update Multiplier Calculation

Replace lines 150-154 with:
```python
    raw_multiplier = (
        (volume_ratio * volume_weight)
        + (effort_factor * effort_weight)
        + (completion_factor * completion_weight)
        + (hr_zone_factor * hr_zone_weight)
        + (feedback_factor * feedback_weight)
    )
```

#### 6g. Enhanced Overreach Detection

Replace lines 158-161 with:
```python
    overreach_detected = False
    if volume_ratio > 1.2 and avg_effort is not None and avg_effort > 8.0:
        raw_multiplier = min(raw_multiplier, 0.88)
        overreach_detected = True
    
    # HR-based overreach detection
    if hr_zone_adherence < 0.3 and hr_result.get("avg_abs_deviation", 0) > 1.0:
        raw_multiplier = min(raw_multiplier, 0.85)
        overreach_detected = True
```

#### 6h. Update Return Dictionary

Add to the return dict (after line 191):
```python
        "hr_zone_adherence": hr_zone_adherence,
        "avg_zone_deviation": round(avg_zone_deviation, 2),
        "hr_zone_trend": hr_zone_trend,
        "hr_zone_factor": round(hr_zone_factor, 2),
        "warning_ratio": round(warning_ratio, 2),
        "positive_ratio": round(positive_ratio, 2),
        "feedback_factor": round(feedback_factor, 2),
```

---

### Step 7: Modify `plan_adjuster.py`

**File:** `app/services/adaptation/plan_adjuster.py`

#### 7a. Fetch HR Zones

After line 44 (after `backfill_baselines`), add:
```python
    # Fetch HR zones from training plan
    hr_zones = None
    if training_plan.hr_zones_data:
        try:
            hr_zones = training_plan.hr_zones_data.get("zones")
        except (AttributeError, TypeError):
            pass
```

#### 7b. Fetch RunFeedback

After line 55 (after `all_plan_runs` query), add:
```python
    # Fetch feedback for all runs
    run_ids = [run.id for run in all_plan_runs]
    run_feedback_list = (
        db.query(RunFeedback)
        .filter(RunFeedback.run_log_id.in_(run_ids))
        .all()
    ) if run_ids else []
```

#### 7c. Pass to Signal Computation

Modify the `compute_adjustment_signals()` call (lines 94-99) to:
```python
    signals = compute_adjustment_signals(
        all_plan_runs, past_workouts, past_workout_ids,
        today, plan_id, db, _recency_weight,
        current_phase=_get_current_phase(training_plan, current_week),
        adaptation_history=training_plan.adaptation_history,
        hr_zones=hr_zones,
        run_feedback_list=run_feedback_list,
    )
```

#### 7d. Update Reason/Logging

After line 163, add to reason_parts:
```python
    hr_zone_adherence = signals.get("hr_zone_adherence")
    if hr_zone_adherence is not None:
        reason_parts.append(
            f"HR zone adherence: {round(hr_zone_adherence * 100)}% "
            f"(trend: {signals.get('hr_zone_trend', 'unknown')})."
        )
    
    warning_ratio = signals.get("warning_ratio")
    if warning_ratio is not None and warning_ratio > 0:
        reason_parts.append(
            f"Feedback warnings: {round(warning_ratio * 100)}% of runs."
        )
```

---

### Step 8: Create Backfill Script

**File:** `scripts/backfill_hr_zone_deviation.py` (NEW)

```python
"""Backfill hr_zone_deviation for existing runs."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.coaching.hr_feedback import compute_hr_zone_deviation
from app.models import DailyWorkout, RunLog, TrainingPlan
from app.database import SessionLocal


def backfill():
    db = SessionLocal()
    try:
        plans = db.query(TrainingPlan).all()
        
        for plan in plans:
            if not plan.hr_zones_data:
                continue
            
            hr_zones = plan.hr_zones_data.get("zones")
            if not hr_zones:
                continue
            
            runs = (
                db.query(RunLog)
                .filter(
                    RunLog.training_plan_id == plan.id,
                    RunLog.hr_zone_deviation.is_(None),
                    RunLog.avg_heart_rate.isnot(None),
                )
                .all()
            )
            
            for run in runs:
                workout = None
                if run.daily_workout_id:
                    workout = (
                        db.query(DailyWorkout)
                        .filter(DailyWorkout.id == run.daily_workout_id)
                        .first()
                    )
                
                deviation = compute_hr_zone_deviation(run, workout, hr_zones)
                if deviation is not None:
                    run.hr_zone_deviation = deviation
            
            if runs:
                db.commit()
                print(f"Backfilled {len(runs)} runs for plan {plan.id}")
        
        print("Backfill complete.")
    finally:
        db.close()


if __name__ == "__main__":
    backfill()
```

Run with:
```bash
cd /Users/boliveira/Documents/RunCoach
python3 scripts/backfill_hr_zone_deviation.py
```

---

### Step 9: Run Tests

```bash
cd /Users/boliveira/Documents/RunCoach
python3 -m pytest -xvs
```

## Testing Strategy

1. **Unit tests for HRZoneAnalyzer** — Test adherence calculation, trend detection, edge cases
2. **Unit tests for compute_hr_zone_deviation** — Test with various HR values and zones
3. **Integration test for signal_computer** — Verify new signals affect multiplier correctly
4. **Integration test for plan_adjuster** — Verify HR zones and feedback are passed through
5. **Backward compatibility test** — Verify plans without HR data still work (graceful degradation)

## Expected Behavior

### Scenario 1: Runner consistently above target HR zones
- avg_zone_deviation = +1.2
- hr_zone_factor = 0.95
- Multiplier decreases → plan reduces volume to protect recovery

### Scenario 2: Runner consistently below target HR zones  
- avg_zone_deviation = -1.1
- hr_zone_factor = 1.05
- Multiplier increases → runner ready for more intensity

### Scenario 3: Many feedback warnings
- warning_ratio = 0.65
- feedback_factor = 0.92
- Multiplier decreases → plan adjusts based on user-reported issues

### Scenario 4: No HR data
- hr_zone_factor = 1.0 (neutral)
- Weight redistributed to other signals
- Plan works as before

## Summary

This implementation:
- ✅ Integrates HR zone data into adaptation signals
- ✅ Consumes RunFeedback sentiment in adaptation pipeline
- ✅ Maintains backward compatibility (graceful degradation)
- ✅ Adds enhanced overreach detection
- ✅ Provides detailed logging and history tracking
- ✅ Includes backfill script for existing data
