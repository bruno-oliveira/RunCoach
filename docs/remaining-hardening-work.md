# Remaining hardening work

State as of the `chore/robustness-sweep` branch (off `main` at `b134b49`).

This records what is **deliberately unfinished** after the hardening sweep, so
the next person does not have to re-derive it — and so nothing here reads as an
oversight. Everything listed under "done" was verified; everything under
"remaining" was scoped out on purpose, with the reason.

## Verifying the current state

```bash
env -u DATABASE_URL python3 -m pytest tests/     # 12,486 passed, 205 skipped, 87.8% cov
env -u DATABASE_URL ruff check app/ tests/
env -u DATABASE_URL ruff format --check app/ tests/
env -u DATABASE_URL pyright                       # 8 packages, 0 errors
```

`env -u DATABASE_URL` is not superstition: `tests/conftest.py` pins
`DATABASE_URL` with `setdefault` so an explicit environment still wins (which is
what CI needs). If you happen to have it exported — e.g. from a manual
`python -m app.migrations` run — the suite will point at *your* database path,
and the three `/health` tests fail with a confusing "unable to open database
file". That cost me twenty minutes; it will cost you five.

To see the full picture including the unfinished package:

```bash
pyright app/contexts
```

## 1. The pyright ratchet — `app/contexts` is the last package

The ratchet (documented in `CLAUDE.md`) checks 8 of 9 packages. `app/contexts`
is **not** in `pyrightconfig.json` because it still has **79 errors**, and the
rule is: get a package to zero *first*, then add the path.

What is left, by kind:

| Kind | Count | What it means |
|---|---|---|
| `reportArgumentType` | 44 | a nullable value passed where a value is required |
| `reportOptionalOperand` | 14 | an operator (`>`, `-`) applied to a nullable |
| `reportOperatorIssue` | 10 | same, where one side is a union |
| `reportOptionalMemberAccess` | 4 | attribute read off a nullable |
| `reportCallIssue` | 4 | same as the first, for a call |
| `reportAttributeAccessIssue` | 3 | wrong attribute for the type |

Hot spots: `plan/adaptation/intent_service.py` (8),
`plan/generators/plan_generator.py` (7), `plan/plan_template_context.py` (6),
`plan/adaptation/run_mapper.py` (5).

### The two decision rules

Every one of these is "what should a `NULL` do here?", so it is training logic,
not a mechanical fix. Two rules cover almost all of them:

- **Coerce** when absence has an obvious neutral equivalent. A `NULL`
  `plans_generated` is `0`; a `NULL` `current_weekly_km` is `0.0` for the
  nutrition engine, which has a floor.
- **Widen the contract, or guard and skip**, when it does not. A plan we cannot
  measure against a `weeks_duration` it does not have is *not* claimed to be
  finished; a run with no distance is *not* eligible for a VDOT.

**Never fabricate a plausible value.** Converting a missing `created_at` to
"now" would assert a join date the database never recorded, so
`UserResponse.created_at` was widened to `Optional[datetime]` instead. The one
place a degenerate value is chosen is `PlanExportDTO.from_orm`, which coerces
four structurally-required fields so a malformed row cannot crash a PDF export —
`or ""` / `or 0` on a cover is visibly wrong rather than plausibly wrong.

### Already done, and worth knowing before you start

`compute_current_week` in `app/core/training/periodization/plan_calendar.py` now
carries `@overload`s, because its return type is conditional: pass a concrete
`pre_start` and every path yields `int`; leave it out and a not-yet-started plan
yields the `None` sentinel. That single change removed the largest cluster of
`app/contexts` errors (callers no longer have to re-prove a value they had
already supplied), and it retired the `assert x is not None` narrowing that a
previous pass had scattered through callers. If you find yourself writing
`assert` for a type, check whether the callee's signature should be overloaded
instead.

`tests/test_services/test_plan_date_utils.py` pins both branches.

## 2. Deferred follow-ups

Each of these was found, considered, and consciously left. None is a blocker.

### `/health` does not distinguish liveness from readiness

`/health` now runs a real `SELECT 1` and answers 503 when it fails, which is what
was asked for and is a large improvement on a static `{"status": "healthy"}`.
But the textbook split is two endpoints: liveness (is the process up? no I/O)
and readiness (can it serve? dependency checks). The reason to care: Fly's
`[checks.liveness]` **restarts** a failing machine, and a database problem is not
always fixed by a restart — so the split would let a machine be taken out of the
proxy pool without being cycled.

For this deployment the failure modes are "volume missing/corrupt/locked", where
cycling is arguably the right response, which is why the single check is
defensible. If a transient dependency is ever added (a remote service), split it.

### The rate limiter is per-process, by design

`app/rate_limit.py` keeps counters in module-level dicts, so it bounds abuse
against *one* machine. True today (Fly runs a single machine) and stated in the
module docstring — but it silently stops being a limiter the moment the app
scales out, since two machines would each grant the full budget. Scaling out
needs a shared store, not a bigger dict.

### `status_label` and friends could be a typed view model

`status_label`, `target_distance_display` and `experience_level` are decorated
onto `TrainingPlan` instances per request by
`app/contexts/plan/plan_status.decorate_plan_status`. They are declared on the
model behind `TrainingPlan.__allow_unmapped__ = True`.

That flag is a deliberate trade-off, and it costs something real: with it on, a
future *column* annotation that forgets its `Mapped[]` silently becomes a plain
attribute instead of raising, and nothing else would catch it — the suite builds
its schema from Alembic migrations, so a column that exists in the database but
is not mapped would simply never be written.

`tests/test_core/test_model_annotations.py` is the tripwire: it fails if any
model grows an un-`Mapped`, undocumented annotation, and separately proves no
`Mapped[]` annotation lost its backing column. So the hole is guarded rather than
open.

The tidier long-term shape is a small typed view model (a `PlanStatus` dataclass
built by the decorator, rendered with `status.label`) so the ORM class carries no
view state at all. That touches the templates, which are not type-checked, so it
was not worth doing inside a type-safety sweep.

## 3. Repo-level drift worth a look

- **`uv.lock` and `requirements.txt` disagree.** `uv.lock` has no `anthropic`
  entry at all (it pre-dates the dependency being declared), and the local
  `.venv` is *ahead* of `requirements.txt` on ten packages — `fastapi` 0.136.0 vs
  the pinned 0.115.12, `sqlalchemy` 2.0.49 vs 2.0.41, `pydantic` 2.13.3 vs
  2.11.3, `cachetools` 7.0.6 vs 5.5.2, and others. CI installs
  `requirements.txt`, so **CI runs older versions than local development**.
  Either regenerate `uv.lock` from `requirements.txt` (or vice versa) and pick
  one as authoritative, or accept that the two are for different purposes and say
  so. Right now a green local run is not evidence about the shipped versions.
- **Python versions differ three ways**: `pyproject.toml` says `>=3.11`, the
  Dockerfile is `python:3.12.13-slim`, CI is 3.12, and the venv is 3.13. The
  `datetime.utcnow()` deprecations only surface on 3.12+, so a 3.11-only
  developer would not see them.
- **`docs/architecture-evolution-sqlite-volume.md` is stale.** It documents a
  `start.sh` that seeds the database from an image snapshot and prints
  "[start.sh] Volume is empty — seeding…". `start.sh` has not done that for a
  while, and after this sweep it does no work at all beyond `exec uvicorn`
  (migrations moved to Fly's `release_command`). The document's *rationale* is
  still the right background; its transcripts are fiction.
- **Modules with the thinnest coverage** (sweep added tests for the previously
  0% ones — `anthropic_narrator`, `secrets`, `cleanup_service`,
  `plan_validation_registry` was deleted, `fit_validation_local` moved to
  `scripts/`): the next-most-exposed are
  `runner/fitness/adherence_service.py` (16%),
  `runner/fitness/gap_analysis_service/context.py` (21%),
  `gap_analysis_service/gap_metrics.py` (25%),
  `plan/adaptation/missed_week_handler.py` (28%). All are business logic that
  alters what a runner is told.

## 4. Audit claims that turned out to be wrong

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
