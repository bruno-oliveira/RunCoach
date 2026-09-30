# Remaining hardening work

State as of `main` after the follow-up pass on the `chore/robustness-sweep` work.

**Everything this document used to list as remaining is now done.** It is kept as
the record of what changed, how it was verified, the two rules that decided the
non-mechanical cases, and the few things that are *still* deliberately open — so
the next person does not have to re-derive any of it.

## Verifying the current state

```bash
env -u DATABASE_URL python3 -m pytest tests/     # 12,746 passed, 205 skipped, 88.8% cov
env -u DATABASE_URL ruff check app/ tests/
env -u DATABASE_URL ruff format --check app/ tests/
env -u DATABASE_URL pyright                      # all of app/, 0 errors
uv lock --check                                  # the lock agrees with the pins
```

`env -u DATABASE_URL` is not superstition: `tests/conftest.py` pins
`DATABASE_URL` with `setdefault` so an explicit environment still wins (which is
what CI needs). If you happen to have it exported — e.g. from a manual
`python -m app.migrations` run — the suite will point at *your* database path,
and the three `/health` tests fail with a confusing "unable to open database
file". That cost me twenty minutes; it will cost you five.

## 1. The pyright ratchet — closed

`app/contexts` was the last package (79 errors). It is now at zero, **and so is
everything else under `app/`**: the loose modules the per-package list never
named (`app/utils.py`, `app/exceptions.py`, `app/migrations/vdot_backfill.py`)
carried 7 more, so those were fixed too and `include` collapsed to a single
entry:

```json
{ "include": ["app"], "pythonVersion": "3.12", ... }
```

The per-package allow-list was a ratchet — a package joined it only once it was
clean — and it has closed. A new module cannot now be added without being
checked. `tests/` and `scripts/` are deliberately outside it.

### Note first: "fix the type" usually means "fix the signature"

`compute_current_week` in `app/core/training/periodization/plan_calendar.py`
already carries `@overload`s, because its return type is conditional: pass a
concrete `pre_start` and every path yields `int`; leave it out and a
not-yet-started plan yields the `None` sentinel. That change removed the largest
cluster of `app/contexts` errors, and it retired the `assert x is not None`
narrowing a previous pass had scattered through callers.

Same lesson this time round, twice more.
`PerformancePlanGenerator.calculate_training_zones` took a `goal_pace: float` it
could not justify — the plan column is nullable, and the zone table can be built
from `vdot_zones` alone — so the parameter was widened to `Optional[float]`. And
`app/utils.to_date` was doing a `hasattr(value, "date")` duck-check that let a
plain `date` through to `value.date()`, which `date` does not have; it is now an
`isinstance(value, datetime)` narrowing, which is what its own annotation already
promised.

If you find yourself writing an `assert` for a type, check whether the callee's
signature should be overloaded or widened instead.

### The two decision rules

Every one of these is "what should a `NULL` do here?", so it is product logic,
not a mechanical fix. Two rules covered all 86:

- **Coerce** when absence has an obvious neutral equivalent. A NULL
  `distance_km` is `0 km` in a weekly sum; a NULL `pace_zone` key is `""`; a NULL
  counter is `0`. Coercion was the right answer in about twenty places.
- **Widen the contract, or guard and skip**, when it does not. A plan we cannot
  measure against a `weeks_duration` it does not have is *not* claimed to be
  finished; a run with no distance is *not* eligible for a VDOT; a workout with
  no `day_of_week` is *not* rebuilt into a day-carrying card.

**Never fabricate a plausible value.** The one deliberate exception is still
`PlanExportDTO.from_orm`, which coerces four structurally-required fields with
`or ""` / `or 0` so a malformed row cannot crash a PDF export — visibly wrong
rather than plausibly wrong.

### The shapes the fixes took

| Shape | Where | What it does |
|---|---|---|
| Coerce to a neutral value | `adherence_service`, `coaching_data`, `gap_metrics`, `run_creation_service`, `run_mapper`, `plan_data_enricher` | a NULL distance/volume/zone key is `0` / `0.0` / `""` |
| Filter the iterable | `performance_service` (`sorted(… if … is not None)`), `plan_template_context` (`sum`), `coaching_data` | the SQL already excluded NULLs; the Python filter makes that visible |
| Guard and skip | `run_mapper`, `adherence_service`, `feedback_service`, `week_adjustment_service`, `gap_analysis_service/context` | a run with no date cannot be placed in a week |
| Guard and skip | `intent_service`, `type_swapper`, `plan_adjuster`, `plan_generator` | a workout with no `day_of_week` cannot be rebuilt or matched to a card |
| Guard and skip | `plan_lifecycle_service`, `plan_template_context`, `run_mapper`, `skipped_detector`, `week_adjustment_service` | a plan with no `weeks_duration`/start date has no week grid — and is not therefore "completed" |
| Widen the contract | `RunLogResponse` (`distance_km`, `duration_minutes`, `date`, `created_at` → `Optional`), `calculate_training_zones(goal_pace: Optional[float])` | the row genuinely may not have the value, so the response mirrors the database |
| Refuse rather than invent | `AuthService.get_or_create_user` (missing `sub`), `FavoritesService.add_favorite` (missing `name`) | both are structurally required, so a missing one raises `ValidationException` (→ 400) instead of writing a nameless row or an unidentifiable account |
| Delete the dead branch | `runner/enrichment/__init__.py` | it lazily re-exported three classes that no longer exist in their modules, and nothing imported them |
| Read the honest value | `vdot_recalibrator._apply_recalibration` | `old_vdot` read the nullable `training_plan.vdot`; the caller's already-proven `plan_vdot` *is* the value being replaced |

Three behaviours worth knowing about, all in the "refuse rather than invent" row.
`add_favorite` and `get_or_create_user` used to reach the database with a NULL and
produce either a 500 or a nameless row; they now answer 400.

The third is the run's required fields, which needed a follow-up decision.
Widening `RunLogResponse` was the right shape for *reading* — but
`PUT /api/runs/{id}` could still *clear* a field, so the widening alone would
have meant "the API stops 500ing and instead reports a run with no distance".
Both creation paths were already strict (`RunLogCreate` requires a positive
`distance_km` and `duration_minutes`; the Intervals importer raises on an activity
missing distance, duration or start time), and `RunLogUpdate`'s use of
`exclude_unset=True` was the only remaining way in: an explicitly-sent `null`
counts as set, so it wrote NULL. That is now a 400 —
`tests/test_routers/test_runs_update.py` pins it, including that the refusal
happens before any write. The columns stay nullable, deliberately: a row written
before the guard (or straight to the database) still renders instead of 500ing,
and a future platform that reports an activity with no distance does not have to
be dropped outright.

One UI fix fell out of the same work: a runner whose plan has no recorded
duration is no longer shown the literal `"Week 3 of None"`. See §2c.

## 2. Follow-ups that were deferred

Each of these was found, considered, and consciously deferred. All three are now
done.

### 2a. `/health` now distinguishes liveness from readiness

The single check ran a real `SELECT 1` and answered 503 — defensible, because the
failure modes here ("volume missing/corrupt/locked") are ones a restart *does*
tend to fix. But Fly's two remedies differ, and that is what the split buys:

- `GET /health/live` — **no I/O**. Asserts only that the process is up. This is
  what `[checks.liveness]` reads: a failing liveness check *restarts* the
  machine, which is the right answer to a wedged process and the wrong one to a
  missing volume (cycling the fleet does not mount storage).
- `GET /health/ready` — runs the dependency probe and answers 503 when it fails.
  This is what `[[http_service.checks]]` reads, so a machine that cannot reach
  its database is **drained from the proxy pool** rather than restarted.
- `GET /health` — kept as the readiness check under its old name, so existing
  monitors and the Dockerfile `HEALTHCHECK` keep working unchanged.

`tests/test_routers/test_health_endpoint.py` pins all three, including that
liveness never calls the probe.

### 2b. The rate limiter has a store seam

`app/rate_limit.py` kept its counters in module-level dicts, so it bounded abuse
against one machine and silently stopped being a limiter the moment the app
scaled out. That is still the *default* — but it is now a swap, not a rewrite:

- `RateLimitStore` is the protocol: `hit(key, max_requests, window_seconds)` —
  decide-and-record in one atomic step — plus `clear()`.
- `InMemoryRateLimitStore` is the default, and still does the abandoned-bucket
  sweep, unchanged.
- `RateLimiter(..., scope=..., store=...)` namespaces each limiter's keys, so one
  shared store can hold every limiter's counters without mixing their budgets.
- `use_shared_store(store)` points every module-level limiter at a shared backend
  in one line at startup.

A store backed by this app's own SQLite database would **not** qualify, and the
module docstring says why: Fly attaches a volume to a single machine, so two
machines do not share one file. Such a store would look shared while granting
each machine the full budget — worse than an honest in-memory dict. Scaling out
needs a genuinely shared backend (Redis, or any store both machines can reach).

`tests/test_security/test_rate_limit.py` pins the seam: distinct scopes in one
store do not spend each other's budget, and `use_shared_store` really installs
the store on every limiter.

### 2c. `status_label` is a `PlanStatus` view model, and `__allow_unmapped__` is gone

`TrainingPlan` carried `status_label` / `target_distance_display` /
`experience_level` as plain attributes written per request by a decorator, which
forced `TrainingPlan.__allow_unmapped__ = True`. That flag cost something real:
with it on, a future *column* annotation that forgets its `Mapped[]` silently
becomes a plain attribute instead of raising, and nothing else would catch it —
the suite builds its schema from Alembic migrations, so a column that exists in
the database but is not mapped would simply never be written.

Now:

- `app/contexts/plan/plan_status.py` is a frozen `PlanStatus` dataclass
  (`label`, `distance_display`, `experience_level`, `.completed`) with
  `plan_status(plan, today)`, `plan_statuses(plans, today) -> dict[id, PlanStatus]`
  and `current_active_plan(plans, statuses)`.
- The ORM class carries no view state at all, so `__allow_unmapped__` is gone.
- Call sites hand the templates a `plan_statuses` mapping and read status fields
  off it (`{% set status = plan_statuses[plan.id] %}`); the `/my-plans` router
  computes the active/completed split instead of the template running
  `selectattr` against a model attribute.
- `tests/test_core/test_model_annotations.py` — the tripwire — now asserts the
  allow-list is *empty* and that `TrainingPlan` has none of the three attributes,
  so putting view state back on the model fails the build.
- `tests/test_core/test_plan_status.py` pins the labels, the completion rule and
  the nullable-column cases.
- `tests/test_routers/test_router_smoke.py::TestMyPlansPage` renders the page with
  an active and a completed plan, since templates are not type-checked.

## 3. Repo-level drift — resolved

### `uv.lock` agrees with `requirements.txt`

They had drifted badly: `uv.lock` had no `anthropic` entry at all, and its
`fastapi` was 0.136.0 against a pinned 0.115.12 (likewise `sqlalchemy`,
`pydantic`, `cachetools`, `pytest`…). CI installs `requirements.txt`, so it ran
versions nobody was developing against.

`uv lock` resolves from `pyproject.toml`, so a `>=` range there is exactly how
the two files diverged. `pyproject.toml`'s dependencies are now pinned to the
same versions as `requirements.txt` — which stays authoritative, since pip, the
Docker image and CI all install it — and the lock was regenerated: `anthropic`
1.9.0 is present, and `fastapi`/`sqlalchemy`/`pydantic`/`cachetools`/`alembic`
all match the pins. `uv lock --check` now passes.

`tests/test_architecture/test_dependency_pins.py` grew a test that fails if any
pinned version in `requirements.txt` differs from `pyproject.toml`, so the two
files cannot silently drift apart again.

### Python is 3.12 everywhere

`pyproject.toml` said `>=3.11` while the Dockerfile was `python:3.12.13-slim` and
CI was 3.12 — and the `datetime.utcnow()` deprecations only surface on 3.12+, so
a 3.11-only developer would not have seen them. `requires-python`, ruff's
`target-version` (`py312`), pyright's `pythonVersion` and the dependency-pin test
are all 3.12 now; the Dockerfile and CI already were.

### `docs/architecture-evolution-sqlite-volume.md` is no longer fiction

It documented a `start.sh` that seeded the volume from an image snapshot and
printed "[start.sh] Volume is empty — seeding…". `start.sh` had not done that for
a while, and today it does nothing but `exec uvicorn` (migrations moved to Fly's
`release_command`). Its rationale is still the right background, so the document
was corrected rather than deleted: a currency note at the top, the seed script
replaced with the release-command story, the invented log transcripts replaced
with what actually happens, and lesson 3 rewritten ("let migrations own the
schema — not a seed snapshot, and not `create_all()`"). The Dockerfile's stale
"runs Alembic migrations" comment on the `start.sh` copy went with it.

### The thinnest-coverage modules now have tests

The sweep added tests for the previously-0% modules. The next-most-exposed were
all business logic that alters what a runner is told; they are covered now:

| Module | Before | After |
|---|---|---|
| `plan/adaptation/missed_week_handler.py` | 28% | 100% |
| `runner/fitness/adherence_service.py` | 16% | 98% |
| `runner/fitness/gap_analysis_service/context.py` | 21% | 95% |
| `runner/fitness/gap_analysis_service/gap_metrics.py` | 25% | 67% |

New files: `tests/test_services/test_missed_week_handler.py`,
`test_adherence_heatmap.py`, `test_gap_analysis_service.py`. Each pins the
preconditions (no plan, another runner's plan, no start date, no duration) as
`[]`/`None` rather than an exception, plus the nullable columns the computation
reads — which doubles as a regression test for the §1 fixes in those files.

## 4. Still deliberately open

Short, and none of it is a blocker.

- **`scripts/` and `tests/` are not type-checked.** `app` is; those two are not.
  `tests/` would be a large, low-value sweep; `scripts/` are one-shot utilities.
- **`coverage` still omits `app/migrations/*`** from the gate (see
  `pyproject.toml`). Those run as a release command and are exercised through
  Alembic, not through unit tests.
- **`gap_metrics.py` sits at 67%.** What is left is the fitness-trajectory and
  elevation branches, which need a prediction fixture rather than a plan fixture
  to reach. Worth doing; not done.
- **A shared rate-limit store is not implemented** — only the seam for it. See
  §2b: the honest implementation needs a store every machine can reach, and this
  deployment has none.

## 5. Audit claims that turned out to be wrong

Recorded so nobody re-investigates them.

- **"Concurrent duplicate run import is possible."** Refuted. The import path is
  guarded three deep: a cheap exact lookup on `intervals_activity_id` (which
  carries a **unique index**), then the fuzzy `find_duplicate_run` for the
  cross-provider Strava-era history, then `_persist` wrapping the insert in
  `db.begin_nested()` and swallowing `IntegrityError`. The losing side of a race
  is already treated as "already imported".
- **"Fourteen deprecated `datetime.utcnow()` calls."** Wrong count. There were
  **3** in `app/` and **4** in `tests/`; the scan had conflated those with 11
  references to local `_utcnow()` helpers. All are now `utcnow_naive()`.
- **"A pre-Alembic database needs `HEAD_REVISION`."** The constant was stale
  (`011` while head was `033`), but the fix was not to update the number — it was
  to derive the head from the script directory, because a hardcoded revision can
  always drift again. Stamping head is also the only choice that cannot replay
  DDL over a schema that already has it.
