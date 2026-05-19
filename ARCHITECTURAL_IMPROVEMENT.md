# RunCoach Architectural Improvement Plan

## Domain-Driven Restructuring with Balanced Dependencies

A structural roadmap to reorganize RunCoach into **domain-driven bounded contexts**, enforce **clean dependency direction**, and eliminate **cross-cutting coupling**. This document is orthogonal to `CORE_IMPROVEMENTS.md` (training behavior) and `IMPROVEMENTS.md` (code quality) — it addresses *component boundaries*, *dependency flow*, and *architectural layers*.

---

## 1. Current Architecture Assessment

### 1.1 Layer Map (as-is)

```
app/
├── main.py                  # Application factory (mixed: config + wiring + startup)
├── config.py                # Pydantic settings (includes training constraints + messages)
├── dependencies.py          # DI container (DB, services, generators — all in one file)
├── schemas/                 # Pydantic request/response models (by domain)
├── models/                  # SQLAlchemy ORM models
├── routers/                 # HTTP handlers (20 files, mixed API + page routes)
├── services/                # Business logic (nested subdirs, inconsistent boundaries)
│   ├── auth/                # Authentication
│   ├── adaptation/          # Plan adaptation (20 files)
│   ├── fitness/             # Fitness analysis (18 files)
│   ├── integrations/        # External services (Strava, GPX, FIT)
│   ├── plans/               # Plan operations (13 files)
│   └── runs/                # Run operations (5 files)
├── core/                    # "Pure" domain logic (violated boundary)
│   ├── generators/          # Plan generators (3 types + orchestrator)
│   ├── training/            # Calculations (25 files)
│   ├── nutrition/           # Meal planning
│   ├── coaching/            # Feedback & notes
│   ├── race/                # Race protocols
│   ├── export/              # PDF generation
│   └── runner_profile.py    # ⚠️ imports services + ORM — boundary violation
└── templates/ static/       # Web layer
```

### 1.2 Identified Architectural Problems

| # | Problem | Severity | Impact |
|---|---------|----------|--------|
| A1 | `core/runner_profile.py` imports `Session`, `RunLog`, `RacePredictorService`, `TrainingLoadService` | High | Core layer is not pure; untestable without DB |
| A2 | No bounded context boundaries — services are organized by *technical concern* not *domain* | High | Adding features requires touching multiple unrelated modules |
| A3 | Dependency direction violated: `core/` → `services/` (should be services → core) | High | Circular import risk; core not reusable outside web app |
| A4 | `dependencies.py` is a 218-line God file instantiating everything | Medium | No lazy loading, no per-context DI, hard to test |
| A5 | Routers contain business logic (plan_view.py:98-159, runs.py ad-hoc queries) | Medium | HTTP layer mixed with domain logic |
| A6 | `config.py` owns training constraints, user-facing messages, AND app settings | Medium | Settings class has 3+ unrelated responsibilities |
| A7 | No domain events — adaptation, fitness, runs communicate via direct calls | Medium | Tight coupling; hard to add async processing |
| A8 | `plan_type` stringly-typed dispatch across 6+ files | Medium | Shotgun surgery for new plan types |
| A9 | PDF generator (`core/export/`) depends on ORM `TrainingPlan` directly | Medium | Cannot export without DB; not testable from fixtures |
| A10 | No clear separation between *read* and *write* models | Low | Same ORM objects used for commands and queries |

---

## 2. Target Architecture: Domain-Driven Layers

### 2.1 Layer Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        WEB LAYER                                │
│  routers/  ·  templates/  ·  static/  ·  middleware/            │
├─────────────────────────────────────────────────────────────────┤
│                      APPLICATION LAYER                          │
│  use_cases/  ·  commands/  ·  queries/  ·  event_handlers/     │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│   PLAN       │  TRAINING    │   RUNNER     │   NUTRITION        │
│   CONTEXT    │  CONTEXT     │   CONTEXT    │   CONTEXT          │
│              │              │              │                    │
│ plan gen     │ calculations │ profile      │ meal planning      │
│ adaptation   │ workout bldg │ fitness hist │ macros             │
│ scheduling   │ vdot/zones   │ load/ACWR    │ recipes            │
│ customization│ phases       │ readiness    │                    │
├──────────────┴──────────────┴──────────────┴────────────────────┤
│                      DOMAIN LAYER                               │
│  entities/  ·  value_objects/  ·  domain_events/  ·  repos/    │
├─────────────────────────────────────────────────────────────────┤
│                   INFRASTRUCTURE LAYER                          │
│  db/  ·  external_apis/  ·  pdf/  ·  auth/  ·  config/         │
└─────────────────────────────────────────────────────────────────┘
```

**Dependency rule**: Inner layers never know about outer layers. Domain → Application → Web. Infrastructure implements domain interfaces.

### 2.2 Bounded Context Definitions

#### Plan Context
- **Responsibility**: Training plan generation, customization, adaptation, scheduling
- **Owns**: `TrainingPlan`, `WeeklyPlan`, `DailyWorkout`, `PlanCustomization` entities
- **Services**: Plan generation orchestration, week adjustment, adaptation engine
- **Events emitted**: `PlanGenerated`, `PlanAdapted`, `PlanCustomized`, `PlanDeleted`

#### Training Context
- **Responsibility**: Pure training calculations — VDOT, pace zones, phase distribution, mileage progression, workout construction
- **Owns**: Value objects only (`PaceZone`, `PhaseDistribution`, `WorkoutStep`, `TrainingLoad`)
- **No dependencies** on other contexts or infrastructure
- **Events emitted**: `VDOTUpdated`, `ZoneRecalculated`

#### Runner Context
- **Responsibility**: Runner profile, fitness history, race prediction, readiness, performance analysis
- **Owns**: `RunnerProfile`, `RunLog`, `RunFeedback`, `ReadinessLog` entities
- **Services**: Fitness analysis, race prediction, HR zones, training load
- **Events emitted**: `RunLogged`, `FitnessUpdated`, `ReadinessRecorded`

#### Nutrition Context
- **Responsibility**: Meal planning, macro calculation, recipe management
- **Owns**: Nutrition plan value objects, meal database
- **No dependencies** on other contexts (receives mileage/distance as input)
- **Events emitted**: `NutritionPlanGenerated`

---

## 3. Migration Plan

### Phase 1: Fix Boundary Violations (Foundation)

#### 3.1 Move `runner_profile.py` to services layer

**Current**: `app/core/runner_profile.py` imports `Session`, `RunLog`, `RacePredictorService`, `TrainingLoadService`

**Target**:
```
app/core/training/runner_profile.py       →  dataclass only (pure)
app/services/runner/profile_builder.py    →  assembles from DB + services
```

**Effort**: Small. The `RunnerProfile` dataclass stays in core as a pure value object. The `build_profile()` function moves to a service.

#### 3.2 Extract domain events module

**New**: `app/domain/events.py`

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class DomainEvent:
    occurred_at: datetime
    aggregate_id: str

@dataclass
class PlanGenerated(DomainEvent):
    plan_type: str
    target_distance: float
    weeks: int

@dataclass
class RunLogged(DomainEvent):
    distance_km: float
    duration_min: float
    workout_type: Optional[str]

@dataclass
class PlanAdapted(DomainEvent):
    adjustment_reason: str
    weeks_affected: int

@dataclass
class VDOTUpdated(DomainEvent):
    old_vdot: float
    new_vdot: float
```

**Effort**: Small. Define events first; wire them incrementally in later phases.

#### 3.3 Define repository interfaces

**New**: `app/domain/repositories.py`

```python
from abc import ABC, abstractmethod
from typing import List, Optional

class IPlanRepository(ABC):
    @abstractmethod
    def get_by_id(self, plan_id: str) -> Optional[TrainingPlan]: ...
    @abstractmethod
    def save(self, plan: TrainingPlan) -> None: ...
    @abstractmethod
    def find_by_user(self, user_id: str) -> List[TrainingPlan]: ...

class IRunRepository(ABC):
    @abstractmethod
    def get_recent(self, user_id: str, weeks: int) -> List[RunLog]: ...
    @abstractmethod
    def save(self, run: RunLog) -> None: ...
```

**Effort**: Medium. Define interfaces; implement via SQLAlchemy in infrastructure layer.

### Phase 2: Reorganize by Bounded Context

#### 3.4 New directory structure

```
app/
├── domain/                          # Pure domain layer
│   ├── __init__.py
│   ├── events.py                    # Domain events
│   ├── repositories.py              # Repository interfaces
│   ├── entities.py                  # Shared entity base
│   └── value_objects.py             # Shared value objects
│
├── core/                            # Pure calculation libraries (no I/O)
│   ├── training/                    # Training calculations
│   │   ├── vdot_calculator.py
│   │   ├── hr_zone_calculator.py
│   │   ├── phase_calculator.py
│   │   ├── mileage_progression.py
│   │   ├── workout_builders.py
│   │   ├── workout_distribution.py
│   │   ├── long_run_calculator.py
│   │   ├── key_workout_library.py
│   │   ├── key_workout_data.py
│   │   ├── key_workout_data_long.py
│   │   ├── key_workout_parser.py
│   │   ├── workout_steps.py
│   │   ├── workout_registry.py
│   │   ├── quality_scorer.py
│   │   ├── quality_caps.py
│   │   ├── strength_plan.py
│   │   ├── trail_profile.py
│   │   ├── vertical_simulation.py
│   │   ├── week_scheduler.py
│   │   ├── zone_calculator.py
│   │   ├── distribution_validator.py
│   │   ├── training_constants.py
│   │   └── runner_profile.py        # Pure dataclass (moved from root)
│   │
│   ├── nutrition/                   # Nutrition calculations
│   │   ├── nutrition_engine.py
│   │   ├── meal_database.py
│   │   ├── meal_selector.py
│   │   └── nutrition_content.py
│   │
│   ├── coaching/                    # Coaching logic (pure)
│   │   ├── coaching_feedback_engine.py
│   │   ├── coaching_notes_generator.py
│   │   ├── training_tips.py
│   │   ├── hr_feedback.py
│   │   ├── pace_feedback.py
│   │   ├── pattern_analyzer.py
│   │   ├── sentiment_classifier.py
│   │   └── volume_tracker.py
│   │
│   └── race/                        # Race logic (pure)
│       ├── race_protocol_generator.py
│       └── race_profiles.py
│
├── contexts/                        # Bounded contexts (application + domain)
│   ├── plan/                        # Plan bounded context
│   │   ├── entities.py              # TrainingPlan, WeeklyPlan, DailyWorkout
│   │   ├── repositories.py          # Plan repository interface + SQLAlchemy impl
│   │   ├── services.py              # PlanService, PlanViewService
│   │   ├── generators/              # Plan generators
│   │   │   ├── plan_generator.py
│   │   │   ├── weekly_plan_builder.py
│   │   │   ├── workout_scaler.py
│   │   │   ├── plan_validator.py
│   │   │   ├── beginner_plan_generator.py
│   │   │   ├── fitness_plan_generator.py
│   │   │   ├── fitness_workout_builders.py
│   │   │   ├── performance_plan_generator.py
│   │   │   └── performance_workout_builders.py
│   │   ├── adaptation/              # Adaptation engine
│   │   │   ├── plan_adjuster.py
│   │   │   ├── signal_computer.py
│   │   │   ├── recommendation_evaluator.py
│   │   │   ├── recalibrator.py
│   │   │   ├── vdot_recalibrator.py
│   │   │   ├── week_adjuster.py
│   │   │   ├── type_swapper.py
│   │   │   ├── alert_checker.py
│   │   │   ├── change_plan_builder.py
│   │   │   ├── change_reasons.py
│   │   │   ├── recovery_inserter.py
│   │   │   ├── missed_week_handler.py
│   │   │   ├── run_mapper.py
│   │   │   ├── safety.py
│   │   │   ├── skipped_detector.py
│   │   │   ├── _helpers.py
│   │   │   └── hr_zone_analyzer.py
│   │   ├── adjustments/             # Plan customization
│   │   │   ├── plan_adjustments.py
│   │   │   ├── week_adjustment_service.py
│   │   │   ├── merge_service.py
│   │   │   └── plan_lifecycle_service.py
│   │   └── view/                    # Plan view/presentation
│   │       ├── plan_view_service.py
│   │       ├── plan_template_context.py
│   │       ├── plan_data_enricher.py
│   │       ├── plan_date_utils.py
│   │       └── completion_stats.py
│   │
│   ├── runner/                      # Runner bounded context
│   │   ├── entities.py              # RunLog, RunFeedback, ReadinessLog
│   │   ├── repositories.py          # Run repository interface + impl
│   │   ├── services.py              # RunService, EnrichmentService
│   │   ├── fitness/                 # Fitness analysis
│   │   │   ├── fitness_service.py
│   │   │   ├── performance_service.py
│   │   │   ├── race_predictor_service.py
│   │   │   ├── race_pacing_service.py
│   │   │   ├── gap_analysis_service.py
│   │   │   ├── training_load_service.py
│   │   │   ├── hr_zone_service.py
│   │   │   ├── readiness_service.py
│   │   │   ├── readiness_scoring.py
│   │   │   ├── personal_records_service.py
│   │   │   ├── adherence_service.py
│   │   │   ├── effort_classifier.py
│   │   │   ├── feedback_service.py
│   │   │   ├── insights_service.py
│   │   │   ├── insight_generators.py
│   │   │   └── performance_progress/
│   │   ├── profile/                 # Runner profile
│   │   │   ├── runner_profile.py    # Pure dataclass
│   │   │   └── profile_builder.py   # Assembles from DB
│   │   └── enrichment/              # Run enrichment
│   │       ├── run_enrichment_service.py
│   │       └── week_pulse_generator.py
│   │
│   ├── nutrition/                   # Nutrition bounded context
│   │   ├── services.py              # NutritionService
│   │   └── recipes/                 # Recipe management
│   │
│   └── auth/                        # Auth bounded context
│       ├── services.py              # AuthService
│       └── repositories.py          # User repository
│
├── infrastructure/                  # Infrastructure implementations
│   ├── database/                    # DB setup, migrations
│   │   ├── engine.py                # SQLAlchemy engine + session
│   │   └── migrations/              # Alembic migrations
│   ├── export/                      # Export implementations
│   │   ├── pdf_generator.py
│   │   ├── pdf_base.py
│   │   ├── pdf_plan_pages.py
│   │   ├── pdf_nutrition_pages.py
│   │   └── pdf_supplementary_pages.py
│   ├── integrations/                # External service clients
│   │   ├── strava_service.py
│   │   ├── strava_post_sync_service.py
│   │   ├── gpx_service.py
│   │   ├── fit_service.py
│   │   └── fit_validation_local.py
│   └── config.py                    # Settings (moved from app/config.py)
│
├── application/                     # Application layer (use cases)
│   ├── commands/                    # Command handlers
│   │   ├── generate_plan.py
│   │   ├── log_run.py
│   │   ├── adapt_plan.py
│   │   └── customize_plan.py
│   ├── queries/                     # Query handlers
│   │   ├── get_plan.py
│   │   ├── get_runner_profile.py
│   │   └── get_analytics.py
│   └── event_handlers/              # Domain event handlers
│       ├── on_run_logged.py
│       └── on_plan_generated.py
│
├── web/                             # Web layer (moved from routers/)
│   ├── routers/                     # HTTP handlers (thin)
│   │   ├── plans.py
│   │   ├── runs.py
│   │   ├── auth.py
│   │   ├── nutrition.py
│   │   ├── performance.py
│   │   ├── analytics.py
│   │   ├── strava.py
│   │   ├── readiness.py
│   │   ├── race_prep.py
│   │   └── recipes.py
│   ├── templates/
│   ├── static/
│   └── middleware/
│
├── schemas/                         # Pydantic models (unchanged, reorganized)
│   ├── plan_schemas.py
│   ├── run_schemas.py
│   ├── auth_schemas.py
│   ├── strava_schemas.py
│   └── race_prep_schemas.py
│
├── dependencies.py                  # DI container (simplified)
├── exceptions.py                    # Custom exceptions (unchanged)
├── main.py                          # App factory (simplified)
├── rate_limit.py
├── template_helpers.py
└── utils.py
```

### Phase 3: Dependency Inversion

#### 3.5 Introduce dependency injection container

**Current**: `dependencies.py` instantiates everything eagerly with 218 lines of `get_*` functions.

**Target**: Per-context DI with lazy resolution.

```python
# app/dependencies.py — simplified
from functools import lru_cache
from app.contexts.plan.services import PlanService
from app.contexts.runner.services import RunService
from app.contexts.runner.fitness.fitness_service import FitnessService
from app.contexts.auth.services import AuthService
from app.infrastructure.database.engine import get_db

@lru_cache
def get_plan_service() -> PlanService:
    return PlanService()

# Services that need DB get it via Depends(get_db)
def get_run_service(db = Depends(get_db)) -> RunService:
    return RunService(db)
```

**Effort**: Medium. Refactor service constructors to accept dependencies explicitly.

#### 3.6 Repository pattern for data access

**Current**: Services and routers run ad-hoc `db.query(Model).filter(...)` everywhere.

**Target**: Repository interfaces in domain layer, SQLAlchemy implementations in infrastructure.

```python
# app/domain/repositories.py
class IPlanRepository(Protocol):
    def get_by_id(self, plan_id: str, *, include_weeks: bool = False) -> TrainingPlan | None: ...
    def find_duplicates(self, user_id: str, criteria: PlanCriteria) -> TrainingPlan | None: ...
    def save(self, plan: TrainingPlan) -> None: ...
    def delete(self, plan: TrainingPlan) -> None: ...
    def list_by_user(self, user_id: str, *, active_only: bool = True) -> list[TrainingPlan]: ...

# app/contexts/plan/repositories.py
class SQLAlchemyPlanRepository(IPlanRepository):
    def __init__(self, session: Session):
        self.session = session
    # ... implementations
```

**Effort**: Large. Migrate incrementally — start with Plan context.

### Phase 4: Clean Up Cross-Cutting Concerns

#### 3.7 Separate config responsibilities

**Current**: `config.py` has app settings, training constraints, user-facing messages, and OAuth config.

**Target**: Split by responsibility.

```
app/infrastructure/config.py             # App settings (name, version, DB, secrets)
app/core/training/training_config.py     # Training constraints (min/max weeks, mileage)
app/core/training/training_messages.py   # User-facing messages per distance
```

**Effort**: Small. Training constraints as a `DistanceConstraints` registry:

```python
@dataclass(frozen=True)
class DistanceConstraints:
    min_weeks: int
    max_weeks: int
    min_mileage: float
    max_mileage: float
    perf_min_mileage: float
    low_mileage_msg: str
    high_mileage_msg: str

DISTANCE_CONSTRAINTS: dict[float, DistanceConstraints] = {
    5.0: DistanceConstraints(...),
    10.0: DistanceConstraints(...),
    21.0975: DistanceConstraints(...),
    42.195: DistanceConstraints(...),
}
```

#### 3.8 Plan type registry (eliminate stringly-typed dispatch)

**Current**: `plan_type` string branched in 6+ files with `if/elif`.

**Target**: Registry pattern.

```python
# app/contexts/plan/plan_types.py
from abc import ABC, abstractmethod

class PlanTypeHandler(ABC):
    @abstractmethod
    def get_view_context(self, plan) -> dict: ...
    @abstractmethod
    def get_zones(self, plan) -> dict: ...
    @abstractmethod
    def get_pdf_section(self, plan) -> Flowable: ...
    @abstractmethod
    def matches(self, plan) -> bool: ...

class RoadPlanHandler(PlanTypeHandler): ...
class PerformancePlanHandler(PlanTypeHandler): ...
class FitnessPlanHandler(PlanTypeHandler): ...

PLAN_TYPE_REGISTRY: list[PlanTypeHandler] = [
    RoadPlanHandler(),
    PerformancePlanHandler(),
    FitnessPlanHandler(),
]

def get_handler_for_plan(plan) -> PlanTypeHandler:
    for handler in PLAN_TYPE_REGISTRY:
        if handler.matches(plan):
            return handler
    raise ValueError(f"No handler for plan_type: {plan.plan_type}")
```

**Effort**: Medium. One handler class per plan type; routers delegate to registry.

#### 3.9 DTO for export (decouple PDF from ORM)

**Current**: `PDFGenerator` accepts `TrainingPlan` ORM object directly.

**Target**: Data transfer object.

```python
# app/contexts/plan/export_dto.py
@dataclass
class PlanExportDTO:
    id: str
    user_id: str
    target_distance: float
    weeks_duration: int
    max_runs_per_week: int
    plan_data: list[dict]
    nutrition_plan_data: dict | None
    hr_zones: dict | None
    plan_type: str
    created_at: datetime

# Router converts once:
dto = PlanExportDTO.from_orm(training_plan)
pdf = PDFGenerator().generate(dto)
```

**Effort**: Small. Define DTO; update PDF mixins to accept it.

---

## 4. Dependency Flow Rules

### 4.1 Allowed Dependencies

```
Web Layer → Application Layer → Domain/Core → (nothing)
     ↓              ↓                ↓
Infrastructure ← (implements interfaces)
```

**Specifically**:
- `web/routers/` may import from `application/`, `contexts/`, `schemas/`
- `application/` may import from `contexts/`, `core/`, `domain/`
- `contexts/*/` may import from `core/`, `domain/`
- `core/` imports **nothing** from `contexts/`, `services/`, `models/`, `infrastructure/`
- `infrastructure/` implements interfaces defined in `domain/`

### 4.2 Forbidden Dependencies

| From | Must Not Import | Why |
|------|-----------------|-----|
| `core/` | `app.models.*`, `app.services.*`, `sqlalchemy` | Core must be pure, importable anywhere |
| `core/` | `app.config` | Core should receive configuration as parameters |
| `domain/` | `app.infrastructure.*` | Domain defines interfaces; infrastructure implements |
| `web/routers/` | Direct `db.query()` | Routers delegate to application services |
| Any | Circular imports between contexts | Contexts communicate via events or application layer |

### 4.3 Cross-Context Communication

Contexts communicate through the **application layer**, never directly:

```
Runner Context  →  emits RunLogged event  →  Application event handler
                                                    ↓
                                              Plan Context adapts
```

For synchronous queries, the application layer coordinates:

```python
# app/application/commands/generate_plan.py
class GeneratePlanCommand:
    def __init__(self, plan_service, runner_profile_builder, nutrition_service):
        self.plan_service = plan_service
        self.runner_profile_builder = runner_profile_builder
        self.nutrition_service = nutrition_service

    def execute(self, request: PlanRequest, user: User) -> TrainingPlan:
        profile = self.runner_profile_builder.build(user.id)
        plan = self.plan_service.generate(request, profile)
        nutrition = self.nutrition_service.generate(request, plan)
        return plan
```

---

## 5. Migration Strategy

### 5.1 Phased Approach

| Phase | Focus | Duration | Risk |
|-------|-------|----------|------|
| **1. Foundation** | Fix boundary violations, define events/repos | 1 week | Low |
| **2. Context extraction** | Move files to new structure, update imports | 2 weeks | Medium |
| **3. Dependency inversion** | Repository pattern, DI container | 2 weeks | Medium |
| **4. Cleanup** | Config split, plan type registry, export DTO | 1 week | Low |

### 5.2 Incremental Migration Tactics

1. **Strangler pattern**: New code goes into new structure; old code stays until migrated
2. **Import aliases**: During transition, `from app.services.plans import PlanService` can alias to `from app.contexts.plan.services import PlanService`
3. **Test coverage first**: Ensure existing tests pass before each migration step
4. **Feature flags**: Gate new structure behind flags if needed for gradual rollout

### 5.3 What NOT to Change

- **Training calculation logic**: VDOT math, phase distributions, 10% cap, 80/20 polarization all work correctly
- **Database models**: SQLAlchemy models stay as-is; repository pattern wraps them
- **Templates and static files**: Web layer structure can migrate last
- **External integrations**: Strava, GPX, FIT services work; just relocate

---

## 6. Expected Outcomes

### 6.1 After Migration

| Metric | Before | After |
|--------|--------|-------|
| Core layer purity | 1 violation (`runner_profile.py`) | 0 violations |
| Cross-context direct imports | ~15 files | 0 (via application layer) |
| Router files with business logic | 6+ files | 0 |
| Stringly-typed dispatches | `plan_type` in 6+ files | Registry pattern |
| ORM coupling in export | PDF depends on `TrainingPlan` | PDF depends on DTO |
| `dependencies.py` size | 218 lines | ~40 lines |
| Config responsibilities | 4 concerns in 1 file | 3 focused files |
| Testability of core | Requires DB | Pure functions, no imports |

### 6.2 Developer Experience

- **Adding a new plan type**: Register one handler class (no router edits)
- **Adding a new distance**: One row in `DISTANCE_CONSTRAINTS` registry
- **Adding a new integration**: Implement `ActivityProvider` protocol
- **Testing core logic**: Import from `core/` — no app, no DB, no config
- **Understanding the system**: Four bounded contexts map to four domain concepts

---

## 7. Relationship to Other Documents

| Document | Focus | Overlap |
|----------|-------|---------|
| `CORE_IMPROVEMENTS.md` | Training behavior, signals, adaptation | None — this doc is structural |
| `IMPROVEMENTS.md` | Code quality (SRP, DRY, security) | Complementary — this doc provides the structural framework for those fixes |
| `P1_P2_PLAN.md` | Execution roadmap for domain work | Complementary — migration phases here can run in parallel |

Items from `IMPROVEMENTS.md` that this architecture enables:
- **E3** (`runner_profile.py` boundary violation): Resolved by Phase 1
- **E2** (`plan_type` stringly-typed): Resolved by Phase 4, section 3.8
- **E4** (PDF depends on ORM): Resolved by Phase 4, section 3.9
- **E1** (per-distance settings): Resolved by Phase 4, section 3.7
- **E6** (routers with ad-hoc queries): Resolved by Phase 2 + repository pattern
- **M2** (plan_view router with business logic): Resolved by Phase 2 (context extraction)
