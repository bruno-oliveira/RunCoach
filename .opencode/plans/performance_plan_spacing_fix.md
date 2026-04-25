# Performance Plan Day Distribution Fix

## Problem
Performance plans with 4x/week schedules produce unbalanced weeks: 3 consecutive runs, then 3 rest days, then the long run.

## Root Cause
In `app/core/generators/performance_plan_generator.py:249-298`:
- Long run on Sunday (day 7), quality on Tue/Fri (days 2, 5)
- Easy runs assigned sequentially from `[1, 3, 4, 6]` (Mon, Wed, Thu, Sat)
- This clumps runs together for 4x/week schedules

## Solution

### File: `app/core/generators/performance_plan_generator.py`

#### Change 1: Move long run from Sunday → Saturday (lines 249-253)
```python
# OLD:
# Long run on Sunday (day 7)
workout_schedule.append({
    'day': 7,
    'workout_generator': lambda: generate_long_run(...)
})

# NEW:
# Long run on Saturday (day 6)
workout_schedule.append({
    'day': 6,
    'workout_generator': lambda: generate_long_run(...)
})
```

#### Change 2: Move quality days from Tue/Fri → Tue/Thu (line 257)
```python
# OLD:
quality_days = [2, 5] if runs_per_week >= 4 else [2]

# NEW:
quality_days = [2, 4] if runs_per_week >= 4 else [2]
```

#### Change 3: Update easy run pool with spacing-aware assignment (lines 284-298)
```python
# OLD:
scheduled_days = {w['day'] for w in daily_workouts}
available_days = [d for d in [1, 3, 4, 6] if d not in scheduled_days]

easy_runs_needed = runs_per_week - len(daily_workouts)
if easy_runs_needed > 0 and remaining_km > 0:
    easy_run_km = remaining_km / easy_runs_needed
    long_runs = [w for w in daily_workouts if w['type'] == 'long']
    long_dist = long_runs[0]['distance'] if long_runs else 0
    min_easy_km = max(3.0, long_dist * 0.20) if long_dist > 0 else 3.0
    easy_run_km = max(easy_run_km, min_easy_km)
    for i in range(easy_runs_needed):
        if i < len(available_days):
            workout = generate_easy_run(zones, easy_run_km)
            workout['day'] = available_days[i]
            daily_workouts.append(workout)

# NEW:
scheduled_days = {w['day'] for w in daily_workouts}
available_days = [d for d in [1, 3, 5, 7] if d not in scheduled_days]

# Sort available days by spacing quality (prefer days with rest on both sides)
def _spacing_score(day: int) -> int:
    return (1 if (day - 1) not in scheduled_days else 0) + \
           (1 if (day + 1) not in scheduled_days else 0)
available_days.sort(key=_spacing_score, reverse=True)

easy_runs_needed = runs_per_week - len(daily_workouts)
if easy_runs_needed > 0 and remaining_km > 0:
    easy_run_km = remaining_km / easy_runs_needed
    long_runs = [w for w in daily_workouts if w['type'] == 'long']
    long_dist = long_runs[0]['distance'] if long_runs else 0
    min_easy_km = max(3.0, long_dist * 0.20) if long_dist > 0 else 3.0
    easy_run_km = max(easy_run_km, min_easy_km)
    for i in range(easy_runs_needed):
        if i < len(available_days):
            workout = generate_easy_run(zones, easy_run_km)
            workout['day'] = available_days[i]
            daily_workouts.append(workout)
```

## Expected Results

### 4x/week (build/peak: 2 quality + 1 long + 1 easy)
| Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|-----|-----|-----|-----|-----|-----|-----|
| Easy | Quality | Rest | Quality | Rest | Long | Rest |

### 4x/week (base: 1 quality + 1 long + 2 easy)
| Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|-----|-----|-----|-----|-----|-----|-----|
| Easy | Quality | Rest | Rest | Easy | Long | Rest |

### 5x/week (2 quality + 1 long + 2 easy)
| Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|-----|-----|-----|-----|-----|-----|-----|
| Easy | Quality | Easy | Quality | Rest | Long | Rest |

### 6x/week (2 quality + 1 long + 3 easy)
| Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|-----|-----|-----|-----|-----|-----|-----|
| Easy | Quality | Easy | Quality | Easy | Long | Easy |

Note: 3+ consecutive runs are acceptable for 5x/6x weeks (unavoidable with that volume).

## Tests to Add

Create `tests/test_performance_plan_distribution.py`:

```python
"""Tests for performance plan day distribution and spacing."""

import pytest
from app.core.generators.performance_plan_generator import PerformancePlanGenerator


class TestPerformancePlanDayDistribution:
    """Verify performance plans have balanced day distribution."""

    @pytest.fixture
    def generator(self):
        return PerformancePlanGenerator()

    def _get_run_days(self, plan):
        """Extract days with runs (non-rest) from a plan."""
        run_days = []
        for week in plan['weeks']:
            for day in week['daily_workouts']:
                if day['type'] != 'rest':
                    run_days.append((week['week'], day['day']))
        return run_days

    def _has_max_consecutive_runs(self, plan, max_consecutive):
        """Check if any week has more than max_consecutive run days."""
        for week in plan['weeks']:
            run_flags = [0] * 8  # index 0 unused, 1-7 = days
            for day in week['daily_workouts']:
                if day['type'] != 'rest':
                    run_flags[day['day']] = 1
            
            max_streak = 0
            current_streak = 0
            for d in range(1, 8):
                if run_flags[d]:
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 0
            
            if max_streak > max_consecutive:
                return True
        return False

    @pytest.mark.parametrize("runs_per_week", [2, 3, 4])
    def test_no_three_consecutive_runs_low_volume(self, generator, runs_per_week):
        """2x, 3x, 4x/week plans should never have 3+ consecutive run days."""
        plan = generator.generate_plan(
            target_distance=10.0,
            current_pace=5.5,
            goal_pace=5.0,
            weeks=8,
            current_weekly_km=40,
            runs_per_week=runs_per_week,
        )
        assert not self._has_max_consecutive_runs(plan, 2), \
            f"Found 3+ consecutive runs in {runs_per_week}x/week plan"

    @pytest.mark.parametrize("runs_per_week", [2, 3, 4, 5, 6])
    def test_long_run_on_saturday(self, generator, runs_per_week):
        """Long run should always be on Saturday (day 6)."""
        plan = generator.generate_plan(
            target_distance=10.0,
            current_pace=5.5,
            goal_pace=5.0,
            weeks=8,
            current_weekly_km=40,
            runs_per_week=runs_per_week,
        )
        for week in plan['weeks']:
            long_runs = [d for d in week['daily_workouts'] if d['type'] == 'long']
            assert len(long_runs) == 1, f"Expected 1 long run, got {len(long_runs)}"
            assert long_runs[0]['day'] == 6, \
                f"Long run on day {long_runs[0]['day']}, expected 6 (Saturday)"

    @pytest.mark.parametrize("phase", ['base', 'build', 'peak', 'taper'])
    def test_quality_workouts_on_tuesday_thursday(self, generator, phase):
        """Quality workouts should be on Tuesday (2) and Thursday (4) for 4x/week."""
        plan = generator.generate_plan(
            target_distance=10.0,
            current_pace=5.5,
            goal_pace=5.0,
            weeks=8,
            current_weekly_km=40,
            runs_per_week=4,
        )
        # Check first non-recovery week of the phase
        for week in plan['weeks']:
            if week['phase'] == phase and not week.get('is_recovery', False):
                quality_days = [
                    d['day'] for d in week['daily_workouts']
                    if d.get('quality', False)
                ]
                assert 2 in quality_days, "Quality workout missing on Tuesday"
                if len(quality_days) >= 2:
                    assert 4 in quality_days, "Second quality workout should be on Thursday"
                break
```

## Execution Steps

1. Apply the 3 changes to `performance_plan_generator.py`
2. Create `tests/test_performance_plan_distribution.py` with the tests above
3. Run `python3 -m pytest tests/test_performance_plan_distribution.py -v`
4. Run `python3 -m pytest tests/test_performance_heart_rate.py -v` to verify no regressions
5. Run `python3 -m pytest` to ensure full test suite passes
