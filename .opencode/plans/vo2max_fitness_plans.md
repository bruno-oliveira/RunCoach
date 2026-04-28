# VO2Max Fitness Plans

## Overview

Add a third plan category — **Fitness Goal** (VO2Max improvement) — alongside the existing "Distance Goal" and "Time Goal" modes. This plan type focuses on expanding the runner's aerobic ceiling and improving VDOT, rather than targeting a specific race distance or finish time.

### User-facing concept

Three modes on the home page:
1. **Distance Goal** (existing) — "I want to run a 10K"
2. **Time Goal** (existing) — "I want to run 5K in 22min"
3. **Fitness Goal** (new) — "I want to get faster and fitter"

The Fitness plan differs from performance plans by:
- **Focus**: Higher density of VO2max (I-pace) interval sessions
- **Progression**: Emphasis on expanding aerobic ceiling rather than hitting a specific race time
- **Duration**: 6–12 week blocks (VO2max adaptations plateau; plans cycle through focus areas)
- **Periodization**: More polarized training (hard days hard, easy days easy)
- **Success metric**: VDOT improvement over time, not race finish
- **No race distance required**: User picks a *focus distance* only for pacing context, not as a race goal

---

## Architecture

```
plan_type = "fitness"  (new value alongside "distance" and "performance")
```

Follows the established pattern: schema → service → generator → router → template.

---

## New Files to Create

### 1. `app/schemas/fitness_schemas.py` — Request schema

```python
class FitnessPlanRequest(BaseModel):
    """Request schema for VO2Max/fitness improvement plans."""

    current_km: float = Field(..., ge=0, le=200)
    weeks: int = Field(..., ge=6, le=12)
    runs_per_week: int = Field(default=4, ge=3, le=6)
    body_weight_kg: float = Field(default=70.0, ge=30.0, le=250.0)
    focus_distance: float = Field(..., description="Pacing reference distance (5, 10, 21.1, 42.2)")
    recent_race_distance_km: Optional[float] = None
    recent_race_time: Optional[str] = None
    max_heart_rate: Optional[int] = Field(None, ge=120, le=220)
    focus_area: str = Field(default="vo2max", description="vo2max, threshold, or balanced")

    # Validators:
    # - focus_distance must be in SUPPORTED_DISTANCES (excluding trail/30.0)
    # - current_km >= 10 (fitness plans need a base)
    # - weeks 6-12
    # - runs_per_week >= 3 (need frequency for VO2max work)
    # - Auto-compute VDOT from recent race if provided
```

### 2. `app/core/generators/fitness_plan_generator.py` — Plan generator

Key design decisions:
- Reuses shared modules: `phase_calculator`, `mileage_progression`, `key_workout_library`, `quality_caps`
- Distinct phase metadata with higher VO2max emphasis
- Polarized training distribution (more easy + more VO2max, less tempo)
- Three focus areas that shift the workout mix:

| Focus Area | Base | Build | Peak | Taper |
|---|---|---|---|---|
| **vo2max** | vo2max, easy | vo2max, vo2max | vo2max, race_pace | vo2max, easy |
| **threshold** | tempo, easy | tempo, vo2max | tempo, tempo | tempo, easy |
| **balanced** | tempo, easy | vo2max, tempo | vo2max, race_pace | tempo, easy |

Phase quality percentages (higher than performance plans):
```python
_PHASE_METADATA = {
    'base':  {'quality_percent': 35, 'description': 'Build aerobic engine with VO2max introductions'},
    'build': {'quality_percent': 55, 'description': 'Heavy VO2max volume — primary adaptation phase'},
    'peak':  {'quality_percent': 65, 'description': 'Peak VO2max intensity with race-pace sharpening'},
    'taper': {'quality_percent': 35, 'description': 'Reduce volume, preserve VO2max sharpness'},
}
```

Workout types:
```python
self.workout_types = {
    'vo2max':    {'zone': 'zone_4', 'description': 'VO2 max intervals — primary focus', 'quality': True},
    'tempo':     {'zone': 'zone_3', 'description': 'Threshold/tempo runs', 'quality': True},
    'race_pace': {'zone': 'zone_5', 'description': 'Race pace efforts at focus distance', 'quality': True},
    'fartlek':   {'zone': 'mixed',  'description': 'Unstructured VO2max play', 'quality': True},
    'long':      {'zone': 'zone_1', 'description': 'Long aerobic run', 'quality': False},
    'easy':      {'zone': 'zone_1', 'description': 'Easy recovery run', 'quality': False},
    'recovery':  {'zone': 'zone_1', 'description': 'Very easy recovery', 'quality': False},
    'rest':      {'zone': None,     'description': 'Rest day', 'quality': False},
}
```

Training zones derived from VDOT (not goal pace):
- If user has a recent race → VDOT-based zones (preferred)
- If no race data → estimate VDOT from `current_km` and `runs_per_week` using a conservative formula
- Zone 4 (VO2max/I-pace) is the primary training zone

`generate_plan()` entry point:
```python
def generate_plan(
    self,
    focus_distance: float,
    current_weekly_km: float,
    weeks: int,
    runs_per_week: int = 4,
    vdot: Optional[float] = None,
    max_heart_rate: Optional[int] = None,
    focus_area: str = "vo2max",
) -> Dict[str, Any]:
```

### 3. `app/services/fitness_service.py` — Service layer

```python
class FitnessService:
    """Service for VO2Max/fitness improvement training plans."""

    def create_fitness_plan(
        self,
        user: User,
        focus_distance: float,
        current_weekly_km: float,
        weeks: int,
        runs_per_week: int = 4,
        vdot: Optional[float] = None,
        max_heart_rate: Optional[int] = None,
        focus_area: str = "vo2max",
    ) -> Tuple[TrainingPlan, Dict[str, Any]]:
```

- Creates `TrainingPlan` with `plan_type='fitness'`
- Stores `vdot` on the plan (for tracking improvement)
- Stores `focus_area` in plan metadata
- Generates nutrition plan via `NutritionEngine`
- Saves weekly/daily records (same pattern as `PerformanceService`)

### 4. `app/templates/fitness_plan.html` — Plan display template

- Reuses shared CSS (`plan-core.css`)
- Shows VDOT-based pace zones prominently (the "north star" metric)
- Phase breakdown with VO2max focus highlighted
- Weekly view with quality workout emphasis
- Includes a "Your VO2Max Progress" section showing current VDOT and projected improvement
- Reuses `performance_plan.html` as a starting point, adapted for fitness context

---

## Existing Files to Modify

### 1. `app/routers/plan_generation.py`

Add `"fitness"` mode handling in `generate_plan()`:

```python
if plan_mode == "fitness":
    return await _generate_fitness_plan(...)
```

New helper function `_generate_fitness_plan()`:
- Requires logged-in user (like time-goal plans)
- Creates `FitnessPlanRequest` from form fields
- Calls `FitnessService.create_fitness_plan()`
- Redirects to `/plan/{plan_id}`

### 2. `app/templates/index.html`

Add third button to mode toggle:
```html
<button type="button" class="mode-btn" id="mode-fitness-btn" onclick="setPlanMode('fitness')">Fitness Goal</button>
```

Update `setPlanMode()` JS to handle `'fitness'`:
- Show fitness-specific fields:
  - `focus_distance` dropdown (5K, 10K, Half, Marathon) — used for pacing context
  - `focus_area` dropdown (VO2Max Improvement, Threshold Building, Balanced)
  - `max_heart_rate` input
  - `weeks` input (min=6, max=12)
  - `runs_per_week` (min=3, default=4)
- Hide: race goal time, goal time fields, terrain selector
- Show: recent race fields (for VDOT calculation) as prominent (not collapsible)
- Body weight: visible (used for nutrition)
- Submit button text: "Generate my fitness plan"

### 3. `app/dependencies.py`

Add dependency:
```python
def get_fitness_service(db: Session = Depends(get_db)) -> FitnessService:
    return FitnessService(db)
```

### 4. `app/main.py`

No changes needed — `plan_generation.py` router is already included. The new mode is handled within the existing `/generate-plan` endpoint.

### 5. `app/core/training/phase_calculator.py`

Add a `'Fitness'` distance category to `PHASE_DISTRIBUTIONS` for the workout distribution module:
```python
'Fitness': {'long': 0.30, 'tempo': 0.05, 'interval': 0.15, 'hill': 0.0, 'easy': 0.50},
```

And update `get_distance_category()` to handle fitness mode (map to `'Fitness'` regardless of distance).

### 6. `app/core/training/key_workout_library.py`

Add VO2max-specific key workouts for the fitness plan type:
- Progressive VO2max intervals (e.g., 6×800m at I-pace, progressing to 8×800m)
- VO2max ladder workouts (400-800-1200-800-400)
- Cruise intervals (longer VO2max efforts: 3×10min at I-pace)

---

## Data Model

No schema migration needed. The existing `TrainingPlan` model already supports:
- `plan_type` column (string) — add `'fitness'` as a value
- `vdot` column — store current VDOT for tracking
- `plan_data` JSON column — store focus_area, focus_distance, and training zones

---

## Form Field Mapping (Fitness Mode)

| Form Field | Name Attribute | Notes |
|---|---|---|
| Weekly mileage | `current_km` | Min 10km for fitness plans |
| Focus distance | `target_distance` | 5, 10, 21.1, 42.2 (pacing context) |
| Duration | `weeks` | 6–12 weeks |
| Runs per week | `max_runs_per_week` | 3–6 (default 4) |
| Body weight | `body_weight_kg` | For nutrition |
| Focus area | `fitness_focus` | vo2max, threshold, balanced |
| Recent race distance | `recent_race_distance_km` | Prominent (for VDOT) |
| Recent race time | `recent_race_time` | Prominent (for VDOT) |
| Max heart rate | `max_heart_rate` | Optional |
| Plan mode | `plan_mode` | Hidden, value="fitness" |

---

## Execution Steps

### Phase 1: Core backend
1. Create `app/schemas/fitness_schemas.py` with `FitnessPlanRequest`
2. Create `app/core/generators/fitness_plan_generator.py` with `FitnessPlanGenerator`
3. Create `app/services/fitness_service.py` with `FitnessService`
4. Add dependency in `app/dependencies.py`

### Phase 2: Router integration
5. Extend `app/routers/plan_generation.py` with `"fitness"` mode and `_generate_fitness_plan()` helper

### Phase 3: UI
6. Update `app/templates/index.html` — add third mode button, fitness fields, JS logic
7. Create `app/templates/fitness_plan.html` — plan display template

### Phase 4: Training modules
8. Update `app/core/training/phase_calculator.py` — add Fitness category
9. Update `app/core/training/key_workout_library.py` — add VO2max-specific workouts

### Phase 5: Testing
10. Create `tests/test_fitness_plan_generator.py` — generator unit tests
11. Create `tests/test_fitness_service.py` — service layer tests
12. Create `tests/test_fitness_schema.py` — schema validation tests
13. Run full test suite: `python3 -m pytest`

---

## Test Strategy

### Generator tests
- Phase distribution matches focus area (vo2max/threshold/balanced)
- Quality workout percentages per phase
- VDOT-based zone calculation
- Weekly mileage progression respects 10% rule
- Recovery weeks every 4th week in base/build
- No 3+ consecutive run days for 3x/4x schedules
- Long run always on Saturday

### Service tests
- Plan creation with VDOT from recent race
- Plan creation without VDOT (estimated)
- Plan persistence (TrainingPlan, WeeklyPlan, DailyWorkout records)
- Nutrition plan generation
- Error handling for insufficient base mileage

### Schema tests
- Valid inputs accepted
- Invalid focus_distance rejected
- current_km < 10 rejected
- weeks outside 6-12 rejected
- runs_per_week < 3 rejected
- VDOT auto-computation from race data

---

## Future Considerations (out of scope for this PR)

- VDOT tracking dashboard showing improvement over multiple fitness plans
- Adaptive fitness plans that adjust based on logged run VDOT (reuse existing recalibrator)
- Fitness plan "completion" assessment comparing start vs end VDOT
- Triathlon-specific fitness plans (swim/bike/run VO2max work)
- Export fitness plan progress as shareable card
