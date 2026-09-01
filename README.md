# RunCoach

A running training plan that **adapts to the runs you actually do**.

Most plans are a static PDF: they assume you hit every session at the prescribed
pace, and they don't notice when you don't. RunCoach generates a periodised plan
for your goal race, imports your completed activities from Intervals.icu, and
re-paces the remaining weeks based on what actually happened — then mirrors the
result onto your watch calendar so the session shows up on your wrist.

Built with FastAPI, SQLAlchemy and SQLite, deployed on Fly.io.

```
56,471 lines  ·  274 modules  ·  1,805 tests  ·  74% coverage gate
```

> Personal project, running in production for its author. Not accepting
> contributions, but the architecture notes below are the interesting part.

---

## What it does

- **Plan generation** — 5K, 10K, half, marathon, trail, and backyard ultra
  (stated in hourly loops, not kilometres). Periodised into base / build / peak /
  taper with VDOT-derived paces, progressive overload, and deload weeks.
- **Adaptation** — matches each logged run to its planned day, detects skipped
  sessions and execution drift, recalibrates VDOT, and re-paces future weeks
  through explicit safety clamps.
- **Morning check-in** — a daily readiness score that feeds the same engine, so
  the plan responds to how you feel and not only to what you ran.
- **Watch mirroring** — keeps the Intervals.icu calendar a *mirror* of the plan
  rather than a log of what was once exported.
- **Coach's Note** — a short daily note, LLM-voiced but grounded (see below).
- **Nutrition** — a meal blueprint scaled to training load, with a recipe library.
- **Export** — PDF plan, `.fit` and `.gpx` workout files.

## Engineering notes

The parts worth reading if you landed here from a CV.

### The dependency rule is a test, not a convention

```
web → application → contexts → core / domain
                                      ↑
                    infrastructure implements protocols declared in domain
```

`tests/test_architecture/test_context_boundaries.py` parses the AST of every file
under `app/contexts/` and **fails the build** if one bounded context imports a
sibling at module scope. Cross-context collaboration goes through
`app/application/`, or through a deferred import — only eager, module-level edges
are rejected, because those are the ones that couple the import graphs.

`core/` imports nothing from `contexts/`, `infrastructure/`, or SQLAlchemy. It is
pure calculation: VDOT, phases, mileage progression, workout building. Pyright
type-checks `app/domain` and `app/core` only — keeping those layers free of I/O
is exactly what makes them checkable, which is the argument for pushing more
logic down into them.

### The LLM gets a voice, never a fact

The Coach's Note is written by Claude Haiku, but the model has never stated a
pace, a distance, or a VDOT value — the architecture doesn't let it.

Every number is computed in Python into a structured fact pack. The model
receives that pack as JSON and compresses it into prose. The hard numbers the
user actually reads are rendered separately from the same pack, never parsed back
out of the completion. The model is isolated behind a `CoachNarrator` protocol
declared in `app/domain/coaching.py`, whose contract is *return `None`, never
raise* — so a missing API key, a rate limit, or a malformed response all fall
back to a deterministic rules note, and the feature degrades instead of failing.

Cost is bounded at **one model call per plan per day** by a cache keyed on a
signature of the inputs the note is built from, rather than a TTL.

Full write-up: [Grounding an LLM feature: giving the model a voice, never a fact](https://dev.to/brunooliveira)

### Constraints that shaped the code

A few decisions that look odd until you know why:

- **Never call `date.today()`.** The app runs on a UTC clock while users live
  elsewhere, so a server-side "today" drifts by up to a day around midnight —
  wrong workout highlighted, readiness logged against the wrong date. The web
  layer captures the browser's IANA zone into a `ContextVar`; all day logic goes
  through `app.core.time_utils.local_today()`.
- **A changed watch day is deleted and re-created**, never updated. Intervals.icu
  only re-triggers the device export on create.
- **Activity dedup matches on start time + distance**, not provider id. A large
  historical backfill carries no Intervals id and would otherwise be re-inserted,
  double-counting every distance total.
- **Backyard ultra sessions carry `fixed_structure`.** A loop simulation is a
  whole number of hourly loops, so the ratio caps and the adaptation adjuster
  skip those sessions rather than prescribing five and a half loops.
- **The root filesystem is ephemeral.** With scale-to-zero the container resets
  to the image on every wake, so the database lives on a mounted volume.

## Quickstart

Requires Python 3.11+.

```bash
git clone https://github.com/bruno-oliveira/RunCoach.git
cd RunCoach
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Fill in the two required values in `.env`:

```bash
# SECRET_KEY — generate one
openssl rand -hex 32

# GOOGLE_CLIENT_ID — from console.cloud.google.com, OAuth client ID (Web),
# with http://localhost:8000 as an authorized JavaScript origin
```

Then run it:

```bash
python3 -m uvicorn app.main:app --reload --port 8000
```

Migrations run automatically on startup and create the schema — there is no seed
file and no manual database step.

Every integration is optional and off by default. With no Intervals.icu
credentials you can still generate and follow plans; with no `ANTHROPIC_API_KEY`
the Coach's Note is produced by the deterministic rules engine; with no
`SMTP_HOST` the mailer refuses and says so rather than pretending to send. See
`.env.example` for the full list.

## Tests and quality gates

```bash
python3 -m pytest tests/              # full suite (coverage gate: 74%)
python3 -m pytest tests/test_core/    # pure-logic tests
ruff check app/ tests/                # lint
ruff format --check app/ tests/       # formatting
pyright                               # types (app/domain + app/core)
```

Test layers mirror the architecture: `test_core/` (pure logic), `test_services/`,
`test_routers/` (API), `test_security/` (CSRF, headers, ownership), and
`test_architecture/` (the dependency guardrails above). The `test_db` fixture is
migrated with Alembic to head rather than `create_all`, so migrations are
exercised on every run.

CI runs lint, typecheck, and tests in parallel, then deploys to Fly.io on a push
to `main`.

## Project layout

```
app/
├── main.py           create_app() factory
├── domain/           protocols and value objects — pure
├── core/             calculation libraries — no I/O, no ORM
│   ├── training/     VDOT, phases, progression, workout building, watch mirror
│   ├── coaching/     notes, recognition, nudges
│   └── race/
├── contexts/         bounded contexts (plan, runner, nutrition, auth)
├── application/      cross-context orchestration — the only legal path between contexts
├── infrastructure/   config, database, export, integrations
├── web/              routers, middleware, templates, static
├── models/           SQLAlchemy ORM
└── schemas/          Pydantic request/response models
```

`CLAUDE.md` carries the longer architectural notes, including the traps worth
knowing before changing anything.

## Security

OAuth tokens are encrypted at rest with Fernet (`MultiFernet`, supporting key
rotation via `ENCRYPTION_KEY_PREVIOUS`). Production requires `ENCRYPTION_KEY` to
be set and distinct from `SECRET_KEY`. Sessions are HTTP-only JWT cookies with
CSRF protection and ownership checks covered by `tests/test_security/`.

Found something? Open an issue rather than a PR.

## License

No license yet — all rights reserved. Ask if you want to use any of it.
