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

### The Coach's Note: the model gets a voice, never a fact

The Coach's Note is the two-to-four sentences at the top of the Today tab, and
it is written by an LLM. It has never stated a pace, a distance, or a VDOT
value — because the architecture doesn't let it.

**Why that constraint came first.** A training app earns trust on its numbers.
If the coach says your easy pace has been drifting when it hasn't, or
congratulates a nine-week streak you never had, the damage isn't one bad
sentence — it's that every other number on the page becomes suspect.
Hallucination here doesn't degrade the feature, it discredits the app. And a
rule in a system prompt is a *request*, not a guarantee: if the only thing
between a user and a fabricated VDOT is a strongly-worded sentence in the
prompt, that's a strong preference, not a property.

So the model is treated like a newsreader. Very good at delivery; not the one
deciding what the news is.

```
contexts/       read-only assemblers        →  deterministic
core/           fact pack + focus selection →  pure, unit-tested
domain/         CoachNarrator (Protocol)    →  the seam
infrastructure/ AnthropicCoachNarrator      →  the only LLM in the path
web/            prose + recognition chips   →  chips computed in Python
```

**1 — The fact pack.** Every number is computed in Python from the runner's own
logged data: training age, the VDOT journey, per-workout-type pace patterns, the
adaptation stance, today's prescribed session, this morning's readiness
check-in. It's a plain JSON-serialisable dict, which makes it loggable and
diffable when something looks off. A detail that matters more than it looks:
`vdot_start` and `vdot_now` are pulled over *the same 12-week window* the
profile uses, because two different horizons produce a "journey" that subtly
contradicts the rest of the page — the kind of bug you can't catch by reading
the prose.

**2 — The narrator is a Protocol, not a client.** This is the entire interface
between the application and any LLM anywhere in the app:

```python
@runtime_checkable
class CoachNarrator(Protocol):
    """Turns a structured fact pack into a short, warm coach's note.

    Implementations must return ``None`` (never raise) when generation is
    unavailable or fails, so the caller can fall back to a deterministic note.
    """

    def generate_note(self, context: dict[str, Any]) -> Optional[str]: ...
```

It lives in `app/domain/coaching.py` and imports nothing but `typing`. The
application layer never imports an SDK, never sees an API key, and never knows
which vendor it's talking to. Testing the real assembly logic needs no network,
no key, no recorded cassettes, and no mocking library — it needs a two-line
class. The contract in that docstring does real work too: *return `None`, never
raise* is what lets every caller downstream be written without a `try/except`,
because failure has a value rather than an exception.

**3 — The adapter converts every failure into `None`.**

```python
def generate_note(self, context: dict[str, Any]) -> Optional[str]:
    try:
        return self._call(context)
    except Exception:  # never let a coach note break the page
        logger.warning("Coach note generation failed", exc_info=True)
        return None
```

The bare `except Exception` is usually a smell; here it is the design. Rate
limit, timeout, malformed response, expired key, SDK not installed — all become
one `None`, logged with a stack trace. No failure of the Anthropic API can
produce a 500 on the Today tab. The `import anthropic` is lazy inside
`__init__`, so the app boots and the suite runs on a machine without the SDK.

**4 — The prompt, and the rule that took longest.** The system prompt asks for
three beats as one flowing note: a short recognition clause, today's purpose and
how to run it, and — *only when there is one* — a single focus adjustment. The
recognition beat is deliberately brief because the chips beside the note already
carry the streak and week count; asking the model to recite stats is both
redundant and exactly where a hallucination would land.

The hard-won rule is this one:

> If "focus" is null, DO NOT invent a warning, caveat, or adjustment — simply
> end after today's purpose.

Hand a model a coach persona and a pile of training telemetry, and on a day when
every signal is green it will *still* find something to caution you about. Not
because it's broken — because that's what coaches sound like. The result is a
runner told to watch their fatigue in a week when nothing was wrong, which is
corrosive precisely because the sentence is plausible.

The fix wasn't a longer prompt. *Whether there is anything to say* is now owned
by a pure function, `select_today_focus()`, which applies an explicit priority
order — readiness, then safety, then execution drift, then effort trend, then
push — against real thresholds, and returns `None` on most days. Judgment in
Python, phrasing in the model.

**5 — Degrading instead of failing.** No API key is a fully supported state:

```python
@lru_cache
def get_coach_narrator() -> CoachNarrator:
    if settings.is_coach_ai_enabled:
        from app.infrastructure.integrations.anthropic_narrator import (
            AnthropicCoachNarrator,
        )
        return AnthropicCoachNarrator(
            api_key=settings.anthropic_api_key, model=settings.coach_ai_model
        )
    return _NullCoachNarrator()
```

Clone the repo, run it with no secrets, and the Today tab renders a perfectly
reasonable note built by `build_fallback_note()` from the identical fact pack,
following the identical three beats. The calling code doesn't branch on
configuration at all — it calls the narrator, and on `None` uses the rules note,
flipping a `source` field from `"ai"` to `"rules"` so the front end (and the
logs) always know which path ran. The recognition chips are computed
unconditionally, *before* the model, and are identical either way.

**6 — Bounding cost with a signature, not a TTL.** A TTL is wrong in both
directions here: it expires while nothing has changed, and serves stale output
straight through the run that should have refreshed it. The cache key is instead
a signature of exactly the inputs the note is built from:

```python
return f"{plan.id}:{count}:{last_str}:{readiness_str}"
```

`count` catches a new run; `max(date)` catches a *back-dated* run the count
alone would miss; the readiness component means logging how you feel this
morning refreshes the note rather than serving yesterday's stance. A second
brake sits on top — once an AI note has been generated in the user's *local*
calendar day it's reused for the rest of that day, which is partly cost and
mostly product, since a daily note that rewrites itself four times an afternoon
is jumpier, not better. Together: **at most one model call per plan per day**,
whatever the sync volume. The cache write is wrapped and rolls back on failure,
because a cache that can't persist must never take down the page it was meant to
make cheap.

**What's missing.** There is no eval harness for the prose. The fact pack, the
focus selection and the fallback are unit-tested; the model's output is verified
by reading it. The deterministic side of the app *does* have a replay harness —
`contexts/plan/adaptation/backtest.py` runs real training history back through
the engine, and tuning against it surfaced three genuine bugs — so the pattern
exists and applying it here is the obvious next step. The protocol also makes
swapping vendors a one-line change, but no second implementation exists, so that
seam is designed rather than exercised.

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
