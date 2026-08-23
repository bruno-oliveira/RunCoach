# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RunCoach is a FastAPI web application that generates personalized running training
plans with nutrition guidance, then **adapts them to what the runner actually
does**. Users give their current weekly mileage, target race distance (5K, 10K,
Half, Marathon, Trail, or a Backyard Ultra stated in *hourly loops*) and training
duration; activities imported from
Intervals.icu feed an adaptation engine that re-paces future weeks, and the plan
is mirrored onto the runner's watch calendar. Google OAuth for sign-in.

## Development Commands

```bash
# Start development server with hot reload
python3 -m uvicorn app.main:app --reload --port 8000

# Install dependencies
python3 -m pip install -r requirements.txt

# Run the full suite (coverage gate: --cov-fail-under=74 — a passing suite
# below that still exits non-zero)
python3 -m pytest tests/

# Run one layer / file / test
python3 -m pytest tests/test_core/ -v          # pure-logic tests
python3 -m pytest tests/test_services/ -v      # context-service tests
python3 -m pytest tests/test_routers/ -v       # API endpoint tests
python3 -m pytest tests/test_security/ -v      # CSRF, headers, ownership
python3 -m pytest tests/test_architecture/ -v  # dependency-direction guardrails
python3 -m pytest tests/test_core/test_vdot_calculator.py::test_name -v

# Skip the coverage gate when iterating on a single test
python3 -m pytest tests/test_core/test_foo.py -v --no-cov

# Lint, format, and type-check (all three gate CI)
ruff check app/ tests/
ruff format --check app/ tests/
pyright                       # only app/domain + app/core — see pyrightconfig.json

# Smoke-test plan generation
python3 -c "from app.contexts.plan.generators.plan_generator import TrainingPlanGenerator; TrainingPlanGenerator().generate_plan(20, 10, 8)"

# Browser-verify a UI change (signed-in user + live plan, on a DISPOSABLE db copy)
python3 scripts/verify_ui.py          # copies runcoach.db, migrates it, prints a session cookie
python3 scripts/dev_verify.py         # serves :8011 against the copy
python3 scripts/verify_ui.py --check  # hash of the real db, to prove it never changed
```

### Never write to `runcoach.db`

`runcoach.db` holds real dev data, and there is **no seed file and no WAL backup
beside it** — an `UPDATE` without a preceding `SELECT` is unrecoverable. It has
already cost a developer their local Intervals connection.

Use `scripts/verify_ui.py` to get a signed-in user and a live plan on a throwaway
copy. If you must touch a real row, `SELECT` and record the current values first.

Two related traps worth knowing:

- **`last_activity`** — `_resolve_user` rejects a session whose user has a stale
  `last_activity`, so a hand-minted JWT 403s every page for no visible reason.
  `verify_ui.py` sets it.
- **`alembic.ini` leaves `sqlalchemy.url` empty on purpose** so the `alembic` CLI
  honours `DATABASE_URL`. Do not hardcode a value back into it: a literal there
  silently wins over the environment, so `DATABASE_URL=... alembic upgrade head`
  would migrate `./runcoach.db` instead of your scratch database.

## CI and deployment

`.github/workflows/ci.yml` runs three parallel jobs — `lint` (ruff check +
`ruff format --check`, pinned to ruff 0.15.14), `typecheck` (pyright), `test`
(pytest with the coverage gate) — and then, **only on a push to `main`**,
deploys to Fly.io with `flyctl deploy --remote-only`. Merging to `main` ships to
production; there is no manual promotion step.

CI installs the pinned `requirements.txt` and then `pip install -e . --no-deps`,
so it exercises the exact versions that ship. If you add a dependency, add it to
**both** `requirements.txt` (pinned) and `pyproject.toml`.

Manual deploy: `fly deploy` (region `sjc`). Docker build: `docker build -t runcoach .`

## Architecture

Domain-driven bounded contexts with a strict dependency direction:
**web → application → contexts → core / domain**, with `infrastructure`
implementing protocols declared in `domain`.

```
app/
├── main.py              # create_app() factory: logging, middleware, routers, /health
├── dependencies/        # DI package: database / services / auth / cron
├── domain/              # Pure: repository + CoachNarrator + Mailer Protocols, value objects
├── core/                # Pure calculation libraries — no I/O, no ORM, no SQLAlchemy
│   ├── training/        # VDOT, phases, mileage progression, workout building, watch_mirror
│   ├── coaching/        # Coaching notes, recognition, nudges, training tips
│   └── race/
├── contexts/            # Bounded contexts: business logic + per-context repositories
│   ├── plan/            # Generation, adaptation, view, lifecycle, adjustments
│   │   ├── generators/  # road / beginner / performance plan generators
│   │   └── adaptation/  # signals, evaluators, adjusters, backtest harness
│   ├── runner/          # profile/ fitness/ enrichment/ wellness/ (+ queries.py)
│   ├── nutrition/
│   └── auth/
├── application/         # Cross-context orchestration (the only legal path between contexts)
├── infrastructure/      # config, database/, export/ (ReportLab), integrations/ (Intervals, FIT, GPX, Anthropic)
├── web/                 # routers/, middleware.py, templates/, static/
├── models/              # SQLAlchemy ORM (centralized so relationships resolve)
├── schemas/             # Pydantic request/response models
└── migrations/          # Startup data backfills (distinct from alembic/)
```

### The dependency rule is enforced by tests

`tests/test_architecture/test_context_boundaries.py` parses the AST of every
file under `app/contexts/` and **fails the build** if one context imports a
sibling context at module scope. Cross-context collaboration goes through
`app/application/`, or through a deferred import (inside a function, or under
`if TYPE_CHECKING:`) — only eager, module-level edges are rejected, because
those are the ones that couple the import graphs.

The rest of the rule, by convention:

- `web/routers/` → `application/`, `contexts/`, `schemas/`
- `application/` → `contexts/`, `core/`, `domain/`
- `core/` imports nothing from `contexts/`, `infrastructure/`, or SQLAlchemy
- `infrastructure/` implements the Protocols in `domain/`

`pyrightconfig.json` type-checks **only `app/domain` and `app/core`** — the pure
layers. Keeping logic pure is what makes it checkable; pushing calculation down
into `core/` is the established direction of travel.

### Persistence boundary (CQRS-lite)

Writes go through repositories (`SQLAlchemy{Plan,Run,User,Readiness,FavoriteRecipe}Repository`,
implementing the Protocols in `app/domain/repositories.py`). Read-heavy paths use
query modules (`app/contexts/runner/queries.py`, `app/contexts/plan/plan_lookup.py`).
Routers should carry no raw `db.query` — there is one remaining exception in
`notifications.py`; don't add more.

### Subsystems that span many files

- **Plan generation** — `contexts/plan/generators/` orchestrates; the actual
  math lives in `core/training/` (`phase_calculator`, `mileage_progression`,
  `long_run_calculator`, `vdot_calculator`, `workout_distribution`,
  `workout_builders`). `plan_structure_guard.py` and `plan_validator.py` are
  the post-generation sanity checks.

- **Adaptation** — `contexts/plan/adaptation/__init__.py` is a thin
  `AdaptationService` facade preserving one public API over focused modules:
  `run_mapper` (match logged runs to planned days), `performance_analyzer`,
  `skipped_detector`, `plan_adjuster` / `week_adjuster`, `type_swapper`,
  `vdot_recalibrator`, `safety.py` + `clamps.py` (guardrails), `proactive_nudge`.
  `backtest.py` replays history against the engine — use it when tuning.

- **Backyard Ultra** — a goal stated in *hourly loops*, not in kilometres.
  (The sport calls a completed loop a "yard"; the UI says **loops** everywhere
  because "yard" collides with the imperial unit on an otherwise metric page,
  and glosses the term once in the goal form. Keep new copy on "loops".)
  `core/training/backyard_profile.py` turns a loop count into the numbers
  everything reads: the per-hour rest budget, the loop pace that budget
  implies, tier-aware plan constraints, and — via `as_trail_profile()` — the
  **clamped** ultra projection the engine actually periodises against. That
  clamp is why `target_distance` on a backyard row never round-trips to a loop
  count, and why every display surface must read `backyard_target_loops`
  instead (plan header, `PlanTypeHandler`, PDF cover).
  `core/training/backyard_simulation.py` builds the progressive ladder of loop
  simulations; `generators/weekly_plan_builder/backyard_week.py` installs them
  (modelled on the trail ITW post-pass) and swaps the midweek tempo for
  loop-pace repeats or a turnaround drill. Sessions carry
  **`fixed_structure`**, which is load-bearing: a simulation is a whole number
  of hourly loops, so `enforce_long_run_ratio_cap`, `reclamp_quality_to_long_run`,
  `rebuild_key_workout` and the adaptation adjuster all skip it rather than
  producing five and a half loops. Catalog entries live in
  `key_workout_data_long/backyard.py` and are gated out of rotation via
  `_BACKYARD_ONLY_IDS` (they resolve by id only). Race day gets its own
  protocol in `core/race/backyard_protocol.py` — a timed **corral routine**
  and an hourly **fuelling schedule** that steps down band by band, in place
  of the split table and aid-station planning that mean nothing here.

- **Watch mirroring** — `application/watch_sync_service.py` keeps the
  Intervals.icu calendar a *mirror* of the plan, not a log of what was once
  exported. Decisions are pure (`core/training/watch_mirror.py`); the service is
  the I/O. Load-bearing detail: a changed day must be **deleted and re-created**,
  because Intervals only re-triggers the watch export on create, never on update.

- **Coach's Note** — `application/coach_narrative_service.py` assembles a
  deterministic fact pack, then asks an injected `CoachNarrator`
  (`domain/coaching.py`; Anthropic implementation in
  `infrastructure/integrations/anthropic_narrator.py`) to voice it. Hard numbers
  are computed in Python and never taken from model prose. Falls back to a
  deterministic note when no API key is configured — the feature degrades, it
  does not fail.

- **Run import** — Intervals.icu is the only source since the Strava
  integration was retired. `run_logs.source` carries provenance, read via the
  `was_imported` property. `infrastructure/integrations/activity_dedup.py`
  matches on *start time + distance* rather than provider id, because the large
  Strava-era backfill has no Intervals id and would otherwise be re-inserted,
  double-counting every distance total.

- **Workout typing** — the user-entered/imported `workout_type` is kept separate
  from `inferred_workout_type` (+ `inferred_type_confidence`), filled in from
  pace/HR/distance/splits by `contexts/runner/fitness/workout_type_classifier.py`.
  Always read via `RunLog.effective_workout_type`, which prefers the explicit
  label and falls back to inference for untagged imported runs.

### Timezone: never call `date.today()`

The app runs on a UTC clock (Fly.io, single region) while users live elsewhere,
so a server-side `date.today()` drifts by up to a day around midnight — the
wrong workout highlighted, readiness logged against the wrong date, "current
week" flipping late. The web layer captures the browser's IANA zone
(`X-Timezone` header for API calls, `rc_tz` cookie for page navigations) into a
`ContextVar`. All "what day is it for this user?" logic must go through
`app.core.time_utils.local_today()` / `local_now()`.

### Data flow

1. Google OAuth → `/api/auth/google`; JWT set as an HTTP-only cookie.
2. Form submit → `/generate-plan`; `PlanRequest` validates (min weeks per
   distance, base mileage) and raises domain exceptions.
3. `TrainingPlanGenerator.generate_plan()` builds the weekly schedule;
   `NutritionEngine` builds the meal blueprint.
4. Persisted as a normalized tree — `training_plans` → `weekly_plans` →
   `daily_workouts` — plus a denormalized `plan_data` JSON snapshot for rendering.
5. Activities arrive from Intervals.icu (manual sync or the scheduled sweep) →
   `auto_map_and_adjust` (`infrastructure/integrations/post_sync_service.py`,
   the single entry point both paths share) re-paces future weeks → the watch
   mirror re-syncs.

## Testing

pytest with fixtures in `tests/conftest.py`. Config (`DEBUG`, `SECRET_KEY`,
`GOOGLE_CLIENT_ID`) is set **hermetically at the top of conftest**, before any
app module imports the settings singleton — local and CI runs are identical.

- `test_db` — a temp-file SQLite session **migrated with Alembic to head**
  (not `create_all`), so migrations are exercised on every run
- `client` — `TestClient` over `create_app(skip_migrations=True)` with `get_db` overridden
- `plan_generator`, `nutrition_engine`, `nutrition_engine_seeded` (seed 42, for reproducibility)
- `sample_5k_params`, `sample_marathon_params`, `sample_trail_params`
- An autouse fixture resets the module-scope rate limiters between tests —
  without it, tightly-capped limiters (plan generation is 5/min) cascade failures

## Configuration

Environment variables or `.env` (see `.env.example`). Loaded via
pydantic-settings in `app/infrastructure/config.py`.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | sqlite:///./runcoach.db | Connection string |
| `DEBUG` | False | Debug mode; also relaxes cookie `Secure` and lets `ENCRYPTION_KEY` fall back to `SECRET_KEY` |
| `SECRET_KEY` | (required) | JWT signing key |
| `GOOGLE_CLIENT_ID` | (required) | Google OAuth client ID |
| `INTERVALS_CLIENT_ID` / `_SECRET` / `_REDIRECT_URI` | — | Intervals.icu OAuth |
| `INTERVALS_INITIAL_SYNC_DAYS` | 365 | Backfill window on first connect |
| `SMTP_HOST` | (empty) | Outbound-nudge mail host. **Empty means send nothing** — the null mailer logs and reports failure rather than pretending |
| `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` | 587 / empty | Port 465 switches to implicit TLS; otherwise STARTTLS unless `SMTP_STARTTLS=false` |
| `CRON_SECRET` | (empty) | Shared secret for both scheduled endpoints. Empty makes them 404 |
| `PUBLIC_BASE_URL` | http://localhost:8000 | Absolute origin for links inside emails. Must be set in production |
| `NUDGE_MIN_INTERVAL_DAYS` | 4 | Floor between two nudge emails to the same runner |

Training constraints live in `app/infrastructure/config.py` (min/max weeks and
min mileage per distance) and `app/core/training/training_config.py`
(`DISTANCE_CONSTRAINTS` registry).

### Scheduled jobs

Two daily jobs, driven by `.github/workflows/ambient-sync.yml`, **in this order**:

1. `POST /api/scheduled/sync` — import everyone's activities, hand new ones to
   the adaptive engine, roll every mirrored plan's watch window forward.
2. `POST /api/notifications/run` — email at most one coaching nudge per
   opted-in runner.

The order is load-bearing: the `gone_quiet` guard reads how long it has been
since a logged run, so nudging before importing can tell a runner they've gone
quiet when they came back yesterday. Step 2 inherits GitHub's default "skip if
the previous step failed" — do not add `if: always()`.

Both are off in every direction until configured (no `CRON_SECRET` → 404 and the
workflow skips itself; no `SMTP_HOST` → the mailer refuses and says so). See
`docs/scheduled-jobs-setup.md` for the guards and how to check what *would*
happen with `?dry_run=true` before anything goes out.

## Production notes

Deployed on Fly.io: shared-cpu-1x, 512MB, scale-to-zero
(`auto_stop_machines = 'stop'`).

**The root filesystem is ephemeral.** With scale-to-zero the container resets to
the image state on every machine wake, so anything written under `/app/...` is
lost when the machine idles. The database lives on the mounted volume
`runcoach_data` at `/data/runcoach.db` (`DATABASE_URL` is overridden in
`fly.toml`). Alembic migrations run in the FastAPI lifespan via `start.sh`, so a
first boot creates the schema on the volume with no seed file.

`docs/architecture-evolution-sqlite-volume.md` has the rationale;
`docs/intervals-sync-setup.md` covers the Intervals OAuth setup.

## Code style

- **Imports**: stdlib, third-party, then local. Absolute imports for app modules
  (`from app.contexts... import ...`) — the dominant convention
- **Types**: type hints on all signatures; `X | None` or `Union[...]`
- **Line length**: 88 (ruff; `E501` itself is ignored, but `ruff format` enforces it)
- **Validation**: Pydantic `@field_validator` / `@model_validator`
- **Logging**: `logging.getLogger(__name__)`
- **Docstrings**: Google style. Module docstrings in this codebase explain *why*
  a module exists and which constraint shaped it — match that register rather
  than restating the code
- **Exceptions**: the `RunCoachException` hierarchy in `app/exceptions.py` carries
  `user_message` / `suggestion` and is mapped to HTTP by the global handler
  registered in `create_app` — raise those rather than `HTTPException` from
  business logic
- **Secrets at rest**: OAuth tokens use `EncryptedString` (Fernet via
  `MultiFernet`) — see `app/models/encrypted_type.py`. Production requires
  `ENCRYPTION_KEY` to be set and **distinct from** `SECRET_KEY`; only in debug
  does it fall back to `SECRET_KEY`. `ENCRYPTION_KEY_PREVIOUS` is read on
  decryption only, so keys can be rotated without rewriting rows
