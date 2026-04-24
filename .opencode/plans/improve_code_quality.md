# Code Quality Improvement Plan

> **Goal**: Improve maintainability, extensibility, and adherence to Single Responsibility Principle across the RunCoach codebase.

---

## Executive Summary

The codebase is functionally well-organized into `routers/`, `services/`, `core/`, and `models/` layers, but several files have grown beyond reasonable size and accumulated multiple responsibilities. The most critical issues are:

| Category | Count | Severity |
|---|---|---|
| God classes/services (>500 lines, multiple responsibilities) | 5 | **P0** |
| Router files with embedded business logic | 4 | **P1** |
| Duplicated code across files | 6 instances | **P1** |
| Hardcoded data that should be externalized | 7 files | **P2** |
| Missing shared constants (magic numbers duplicated) | 4 locations | **P2** |
| Schema bloat (schemas.py at 527 lines) | 1 file | **P2** |

---

## P0: Critical Refactoring — God Classes

### 1. `app/services/adaptation/plan_adjuster.py` (763 lines)

**Problem**: 7 distinct responsibilities in one file — adjustment orchestration, event recording, phase detection, signal computation (6 sub-signals), VDOT recalibration, and week adjustment application.

**Proposed Split**:

| New File | Responsibility | Est. Lines |
|---|---|---|
| `adaptation/plan_adjuster.py` | Orchestration only (dispatch to sub-services) | ~150 |
| `adaptation/signal_computer.py` | Volume, effort, completion, trend, overreach, Bayesian shrinkage signals | ~200 |
| `adaptation/vdot_recalibrator.py` | VDOT recalibration with pace zone updates | ~150 |
| `adaptation/week_adjuster.py` | Distance scaling, note annotation, quality cap enforcement for future weeks | ~150 |

**Key Extract**:
- `_compute_adjustment_signals` (lines 254-433) → `SignalComputer`
- `_recalibrate_vdot` (lines 451-554) → `VdotRecalibrator`
- `_apply_adjustment_to_future_weeks` (lines 557-763) → `WeekAdjuster`

---

### 2. `app/services/plan_view_service.py` (602 lines)

**Problem**: 8+ responsibilities — data enrichment, nutrition formatting, run mapping, adjustment hints, feedback loading, completion stats, next-plan CTA, week pulse generation, full view assembly, and week evolution.

**Proposed Split**:

| New File | Responsibility | Est. Lines |
|---|---|---|
| `services/plan_view_service.py` | Orchestration / assembly only | ~120 |
| `services/plan_data_enricher.py` | DB ID enrichment, nutrition format conversion, run mapping | ~150 |
| `services/completion_stats.py` | Completion stats, feedback aggregation, adjustment hints | ~130 |
| `services/week_pulse_generator.py` | Week pulse messages, coaching insights per week | ~150 |

**Key Extract**:
- `get_plan_view_data` (lines 450-554) → stays as orchestrator, calls sub-services
- `nutrition_for_template` (lines 80-156) → `PlanDataEnricher`
- `get_week_pulse` (lines 325-448) → `WeekPulseGenerator`

---

### 3. `app/services/plan_service.py` (511 lines)

**Problem**: 6 responsibilities — plan limit checking, anonymous user resolution, duplicate detection, plan creation orchestration, customization dispatch, and delegation proxy to `PlanViewService`.

**Proposed Split**:

| New File | Responsibility | Est. Lines |
|---|---|---|
| `services/plan_service.py` | Plan creation orchestration only | ~180 |
| `services/plan_creation_service.py` | Persist helpers, HR zone attachment, nutrition attachment | ~180 |
| `services/plan_lifecycle_service.py` | Deletion, customization, limit checking | ~120 |
| Remove delegation methods | Thin proxy methods (lines 465-510) should be removed; inject `PlanViewService` where needed | 0 |

**Key Extract**:
- `_persist_weekly_plan`, `_persist_daily_workouts`, `_attach_nutrition_plan`, `_attach_hr_zones` → `PlanCreationService`
- `delete_plan`, `customize_plan`, `check_plan_limit` → `PlanLifecycleService`
- Lines 465-510 (delegation to `PlanViewService`) → **delete entirely**, use `PlanViewService` directly

---

### 4. `app/services/adaptation/recalibrator.py` (546 lines)

**Problem**: 5 responsibilities — strategy dispatch, weekly suggestion generation, per-week suggestion building, missed week detection, and recovery insertion.

**Proposed Split**:

| New File | Responsibility | Est. Lines |
|---|---|---|
| `adaptation/recalibrator.py` | Strategy dispatch only | ~100 |
| `adaptation/suggestion_generator.py` | Weekly suggestion cards, performance analysis, run bucketing | ~200 |
| `adaptation/missed_week_handler.py` | Missed week detection, ease-in scaling, week shifting, taper shrinking | ~150 |
| `adaptation/recovery_inserter.py` | Recovery week insertion logic | ~100 |

---

### 5. `app/core/generators/plan_generator.py` (625 lines)

**Problem**: Acts as a facade with ~30 delegating methods plus a 112-line God method `_generate_weekly_plan` that does phase calculation, distance budgeting, scaling, fill-up, ceiling enforcement, and validation.

**Proposed Split**:

| New File | Responsibility | Est. Lines |
|---|---|---|
| `generators/plan_generator.py` | Orchestration / delegation only | ~150 |
| `generators/weekly_plan_builder.py` | Distance budgeting, scaling, fill-up, ceiling enforcement | ~200 |
| `generators/plan_validator.py` | Week plan validation, distance reconciliation | ~100 |

**Key Extract**:
- `_generate_weekly_plan` (lines 421-533) → `WeeklyPlanBuilder`
- `_validate_week_plan` (lines 378-419) → `PlanValidator`
- `_inject_pace_into_steps` (lines 36-48) → move to `core/training/workout_steps.py`

---

## P1: High Priority — Router SRP Violations & Duplicated Code

### 6. `app/routers/plans.py` (511 lines) — Split into 3 routers

**Problem**: 6 responsibilities — plan generation, time-goal dispatch, customization, viewing (with inline enrichment), listing (with status computation), and sub-router mounting.

**Proposed Split**:

| New File | Responsibility | Est. Lines |
|---|---|---|
| `routers/plan_generation.py` | Plan generation (distance + time-goal) | ~180 |
| `routers/plan_view.py` | Plan viewing with enrichment | ~180 |
| `routers/plan_list.py` | Plan listing with status labels | ~120 |

**Business Logic to Extract**:
- `_parse_time_to_pace` (lines 195-208) → `app/utils.py`
- Plan view enrichment (nutrition, HR zones, performance) → `services/PlanViewEnricher`
- Status label computation (lines 455-480) → `services/PlanStatusService`

---

### 7. `app/routers/plan_adjustments.py` (450 lines) — Extract domain logic

**Problem**: 80+ lines of `_action_*` functions implementing workout distance manipulation — this is domain logic, not routing.

**Actions**:
- Extract all `_action_*` functions + `_apply_week_action` → `services/week_adjustment_service.py`
- Extract `_get_week_workouts` and `_sync_plan_data_distances` → `services/plan_data_sync.py`
- Move inline Pydantic models to `schemas.py` or `schemas/plan_adjustment_schemas.py`

---

### 8. **CRITICAL**: Delete `app/routers/strava_pages.py` — 70% code duplication

**Problem**: `_auto_map_and_adjust` (lines 34-85) is identical to `strava.py` lines 27-78. `strava_callback` (lines 88-156) is nearly identical to `strava.py` lines 100-170.

**Action**: Delete `strava_pages.py` entirely. The callback in `strava.py` already returns `RedirectResponse`. If a page redirect is needed, the existing callback handles it.

---

### 9. `app/routers/strava.py` (286 lines) — Extract post-sync logic

**Problem**: `_auto_map_and_adjust` (52 lines) is a full orchestration function. `_initial_sync` is a nested background task with its own DB session.

**Actions**:
- Extract `_auto_map_and_adjust` → `services/strava_post_sync_service.py`
- Extract `_initial_sync` → reuse `StravaSyncOrchestrator`
- Move `INITIAL_SYNC_DAYS = 365` → `config.py`

---

### 10. `app/routers/analytics.py` (319 lines) — Split API and pages

**Problem**: Two routers defined in one file (`analytics_router` + `analytics_page_router`). 60-line heatmap builder inline.

**Actions**:
- Split into `routers/analytics.py` (API endpoints) and `routers/analytics_pages.py` (HTML pages)
- Extract heatmap grid building → `services/adherence_service.py`

---

### 11. `app/routers/runs.py` (470 lines) — Extract enrichment and validation

**Actions**:
- Move IDOR validation → `Depends(validate_plan_ownership)` dependency
- Extract `_enrich_vdot_and_prediction` → `services/run_enrichment_service.py`
- Move gap analysis from `/predictions` endpoint → `RacePredictorService`

---

### 12. `app/routers/triathlon_pages.py` (208 lines) — Deduplicate ownership checks

**Problem**: Ownership check logic duplicated 3 times verbatim (lines 30-39, 134-139, 186-192).

**Action**: Extract → `Depends(verify_triathlon_plan_ownership)` dependency.

---

## P1: Cross-Cutting Code Duplication

### 13. Duplicated Magic Numbers — Create `training_constants.py`

The following constants are duplicated across 4+ files:

| Constant | Locations |
|---|---|
| `_HARD_CEILINGS` (distance caps by VDOT) | `plan_generator.py:485`, `long_run_calculator.py:136`, `mileage_progression.py:278`, `performance_workout_builders.py:249` |
| `week_in_phase` calculation | `plan_generator.py:434`, `performance_plan_generator.py:416`, `long_run_calculator.py:92` |
| Quality cap values | `quality_caps.py`, `plan_generator.py`, `mileage_progression.py` |

**Action**: Create `app/core/training/training_constants.py` with all shared constants.

---

### 14. PDF Generator Duplication — Create `pdf_base.py`

**Problem**: `pdf_generator.py` and `triathlon_pdf_generator.py` share caching, styling, and footer logic with zero reuse.

**Action**: Create `app/core/export/pdf_base.py` with:
- Shared PDF caching logic
- Shared style definitions
- Shared footer rendering
- Both generators compose or inherit from it

---

### 15. Dict/ORM Dual-Format Adapters

**Problem**: `quality_caps.py` (lines 99-120) handles both dict and ORM objects with `_get_type`, `_get_distance`, `_set_distance` adapters. This coupling breaks when either format changes.

**Action**: Split into:
- `quality_caps.py` — pure cap logic (works on one format)
- `workout_distance_adapter.py` — dict ↔ ORM conversion utilities

---

## P2: Moderate Priority — Hardcoded Data Externalization

### 16. Externalize Static Data to JSON/YAML

The following files contain hundreds of lines of hardcoded data that should be loaded from external files:

| File | Lines | Data Type | Recommended Format |
|---|---|---|---|
| `core/generators/triathlon_plan_data.py` | 388 | Sprint/Olympic triathlon plans | JSON |
| `core/generators/triathlon_plan_data_70_3.py` | 321 | 70.3 triathlon plan | JSON |
| `core/training/key_workout_data_long.py` | 722 | Long workout definitions | JSON + Pydantic validation |
| `core/training/key_workout_data.py` | 322 | Short workout definitions | JSON + Pydantic validation |
| `core/training/strength_plan.py` | ~320 | Exercise database | JSON |
| `core/coaching/training_tips.py` | ~336 | Training tip strings | JSON |
| `core/race/race_protocol_generator.py` | ~180 | Race protocol checklists | JSON |

**Benefits**:
- Data changes without code redeployment
- Schema validation with Pydantic models
- Easier to review and update
- Potential for admin UI to manage data

---

### 17. `app/schemas.py` (527 lines) — Split by domain

**Problem**: All Pydantic schemas in one file — plan requests, auth, runs, performance, Strava.

**Proposed Split**:

| New File | Schemas |
|---|---|
| `schemas/plan_schemas.py` | PlanRequest, PlanRequestBase, RaceInfoMixin, PerformancePlanRequest |
| `schemas/auth_schemas.py` | UserBase, UserCreate, UserResponse, AuthResponse, Token, GoogleAuthRequest |
| `schemas/run_schemas.py` | RunLogBase, RunLogCreate, RunLogUpdate, RunLogResponse, RunLogListResponse |
| `schemas/strava_schemas.py` | StravaSyncResponse, StravaStatusResponse |
| `schemas/__init__.py` | Re-export all for backward compatibility |

---

### 18. `app/core/training/vdot_calculator.py` (359 lines) — Separate concerns

**Problem**: VDOT math, pace zone generation, description injection, and race prediction all in one file.

**Proposed Split**:

| New File | Responsibility |
|---|---|
| `training/vdot_calculator.py` | Core VDOT math (VO2 calculation, pace zones) |
| `training/race_predictor.py` | Binary search prediction, confidence ranges, multi-distance |
| Move to templating module | `inject_paces_into_description` |

---

### 19. `app/core/training/workout_steps.py` (655 lines) — Extract parser

**Problem**: Key-workout string parser with 4 regex patterns (lines 444-616) is a text-parsing concern mixed with step builders.

**Action**: Extract parser → `core/training/key_workout_parser.py`

---

### 20. `app/core/training/workout_distribution.py` (375 lines) — Split concerns

**Problem**: Quality count calculation, profile-to-builder mapping, distribution building, polarized ratio validation, and day scheduling all in one file.

**Proposed Split**:

| New File | Responsibility |
|---|---|
| `training/workout_count_calculator.py` | Quality workout count calculation |
| `training/quality_type_selector.py` | Profile-to-builder mapping, quality distribution |
| `training/week_scheduler.py` | Day scheduling |
| `training/distribution_validator.py` | Polarized ratio validation |

---

### 21. `app/core/nutrition/nutrition_engine.py` (380 lines) — Separate meal selection

**Actions**:
- Extract `_select_varied_meal` → `core/nutrition/meal_selector.py`
- Extract `_generate_general_nutrition_tips` and `_generate_hydration_guide` → `core/nutrition/nutrition_content.py`

---

### 22. `app/core/coaching/coaching_feedback_engine.py` (404 lines) — Split feedback types

**Actions**:
- Extract `_pace_feedback` → `coaching/pace_feedback.py`
- Extract `_hr_zone_feedback` → `coaching/hr_feedback.py`
- Extract `_volume_feedback` → `coaching/volume_tracker.py`
- Extract `_pattern_feedback` → `coaching/pattern_analyzer.py`
- Extract `_determine_sentiment` → `coaching/sentiment_classifier.py`

---

### 23. `app/core/training/mileage_progression.py` (330 lines) — Extract taper logic

**Actions**:
- Extract `_get_taper_curve` and `_progress_taper_phase` → `training/taper_calculator.py`
- Move magic ceiling/cap dicts → `training_constants.py`

---

### 24. `app/core/training/hr_zone_calculator.py` (170 lines) — Separate DB concerns

**Problem**: Pure calculator coupled to DB sessions and user models (lines 117-170).

**Action**: Split into:
- `hr_zone_calculator.py` — pure math (zone calculation, classification)
- DB integration stays in existing `services/hr_zone_service.py`

---

### 25. `app/core/training/key_workout_library.py` (282 lines) — Extract description templating

**Actions**:
- Extract `_DISTANCE_REWRITES` and `_rewrite_key_workout_description` → `training/workout_description_templater.py`
- Move `_resolve_long_steps_builder` → `training/workout_steps.py`

---

### 26. `app/services/race_predictor_service.py` (433 lines) — Extract weighting strategy

**Actions**:
- Extract confidence weighting logic → `services/vdot_weighting_strategy.py`
- Extract race history enrichment → `services/race_history_enricher.py`

---

### 27. `app/services/strava_service.py` (356 lines) — Extract mapper and orchestrator

**Actions**:
- Extract `map_activity_to_run_log` → `services/strava_activity_mapper.py`
- Extract `sync_activities` pagination/dedup loop → `services/strava_sync_orchestrator.py`

---

### 28. `app/services/performance_service.py` (380 lines) — Extract Max HR calculator

**Actions**:
- Extract `_calculate_max_hr` (3-tier fallback) → `services/max_hr_calculator.py` with strategy pattern
- Extract `_save_weekly_plans` → use bulk insert patterns

---

### 29. `app/services/readiness_scoring.py` (326 lines) — Extract VDOT scorer

**Actions**:
- Extract `score_vdot` (lines 150-258) → `services/vdot_scorer.py`
- Extract scenario building (lines 261-300) → `services/scenario_builder.py`

---

### 30. `app/services/auth_service.py` (158 lines) — Separate token and user concerns

**Actions**:
- Extract JWT token creation/verification + Google cert caching → `services/google_token_verifier.py`
- Extract `get_or_create_user` → `services/user_provisioner.py`

---

### 31. `app/services/plan_helpers.py` (214 lines) — Split by concern

**Problem**: Mixes HTTP helpers, date utilities, and template context building.

**Proposed Split**:

| New File | Responsibility |
|---|---|
| `services/plan_auth_helpers.py` | Plan fetching with ownership validation |
| `services/plan_date_utils.py` | Week date building, current week computation, next Monday |
| `services/plan_template_context.py` | Template context building (`plan_view_context`) |

---

### 32. `app/core/training/long_run_calculator.py` (247 lines) — Remove indirection

**Actions**:
- Move `calculate_quality_distances` → `training/quality_budget.py` (not a long run concern)
- Remove `get_phase_distribution` — unnecessary indirection over `phase_calculator.PHASE_DISTRIBUTIONS`
- Move `hard_ceilings` → `training_constants.py`

---

### 33. `app/core/export/pdf_plan_pages.py` (474 lines) — Extract steps rendering

**Actions**:
- Extract `_add_workout_steps_block` → `export/pdf_steps_renderer.py`
- Move `_add_training_zones_page` → performance PDF module (circular dependency risk)
- Extract `_get_day_name` → shared utility

---

## P2: Infrastructure & Testing Improvements

### 34. Dependency Injection Improvements

**Current State**: `dependencies.py` creates service instances without DB sessions for most services, but some services require DB sessions. This inconsistency leads to services creating their own sessions.

**Actions**:
- Standardize: all services that need DB access should receive it via constructor
- Remove module-level singletons (`_generator`, `_pdf_generator` in `triathlon_pages.py`)
- Inject `meal_db` via dependency instead of module-level global (`recipes.py:20`)

---

### 35. Test Coverage Gaps

**Current State**: 22 test files, but coverage is uneven. Some large services have no dedicated tests.

**Recommended New Tests**:
- `test_plan_adjuster.py` — after splitting `plan_adjuster.py`
- `test_plan_view_service.py` — after splitting `plan_view_service.py`
- `test_week_adjustment_service.py` — after extracting from `plan_adjustments.py`
- `test_strava_post_sync_service.py` — after extracting from `strava.py`
- `test_adherence_service.py` — after extracting from `analytics.py`

---

### 36. Schema Validation for Externalized Data

When hardcoded data is moved to JSON files, add Pydantic models for validation:

```python
class WorkoutDefinition(BaseModel):
    name: str
    type: str
    description: str
    steps: list[StepDefinition]
    # ... etc
```

Load and validate at startup or on first access with caching.

---

## Implementation Order

### Phase 1: Quick Wins (Low Risk, High Impact)
1. Delete `strava_pages.py` (eliminate duplication)
2. Create `training_constants.py` (consolidate magic numbers)
3. Create `pdf_base.py` (shared PDF infrastructure)
4. Deduplicate ownership checks in `triathlon_pages.py`

### Phase 2: Service Layer Refactoring (Medium Risk)
5. Split `plan_adjuster.py` → signal computer, VDOT recalibrator, week adjuster
6. Split `plan_view_service.py` → enricher, stats, pulse generator
7. Split `plan_service.py` → creation, lifecycle, remove delegation proxy
8. Split `recalibrator.py` → suggestion generator, missed week handler, recovery inserter

### Phase 3: Router Layer Refactoring (Medium Risk)
9. Split `plans.py` → generation, view, list routers
10. Extract domain logic from `plan_adjustments.py` → `WeekAdjustmentService`
11. Extract post-sync logic from `strava.py` → `StravaPostSyncService`
12. Split `analytics.py` → API + pages, extract adherence service
13. Clean up `runs.py` → extract enrichment, move IDOR to dependency

### Phase 4: Core Module Refactoring (Medium Risk)
14. Split `plan_generator.py` → orchestrator, weekly builder, validator
15. Split `vdot_calculator.py` → calculator + race predictor
16. Extract key-workout parser from `workout_steps.py`
17. Split `workout_distribution.py` → count calculator, type selector, scheduler
18. Split `hr_zone_calculator.py` → pure calculator + DB service

### Phase 5: Data Externalization (Low Risk, High Maintenance Benefit)
19. Externalize triathlon plan data to JSON
20. Externalize key workout data to JSON with Pydantic validation
21. Externalize strength exercises to JSON
22. Externalize training tips to JSON
23. Externalize race protocol data to JSON

### Phase 6: Cleanup & Polish (Low Risk)
24. Split `schemas.py` → domain-specific schema files
25. Split `nutrition_engine.py` → meal selector, content generator
26. Split `coaching_feedback_engine.py` → feedback type modules
27. Split `plan_helpers.py` → auth, date, context helpers
28. Improve dependency injection consistency
29. Add tests for refactored modules

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| Breaking changes during refactoring | Run full test suite after each file split |
| Import cycle introduction | Use dependency injection instead of direct imports between new modules |
| Regression in plan generation | Add integration test that generates a plan for each distance type before refactoring |
| Performance impact | Profile PDF generation and plan generation before/after refactoring |
| Team coordination | Merge each phase as a separate PR; communicate breaking changes |

---

## Success Metrics

- **File size**: No file exceeds 400 lines (currently 10 files exceed 500 lines)
- **SRP compliance**: Each file has ≤2 distinct responsibilities
- **Code duplication**: Zero instances of duplicated logic across files
- **Test coverage**: Maintain or improve current coverage percentage
- **Build time**: No regression in test execution time
