# From Ephemeral to Persistent: Fixing SQLite on Fly.io

*A war story about a bug that took three debugging sessions to pin down — and a five-minute fix that solved it for good.*

> **Currency.** The bug, the volume and the fix are all still accurate. Two things
> have moved on since: the sync provider is now Intervals.icu (Strava was retired),
> and `start.sh` no longer seeds the volume from an image snapshot — a first boot
> builds the schema with Alembic instead. Both are called out where they appear.

---

## The Setup

RunCoach is a FastAPI app that generates personalised running training plans. Users connect their Intervals.icu account, and the app syncs their run history to power an analytics dashboard.

The stack is deliberately simple:

- **FastAPI** — Python web framework
- **SQLite** — single-file database
- **SQLAlchemy** — ORM
- **Fly.io** — hosting, with scale-to-zero machines

The Dockerfile was straightforward. Copy code in, copy the database in, run the app:

```dockerfile
COPY app/ ./app/
COPY runcoach.db ./runcoach.db
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

And `fly.toml`:

```toml
[env]
  DATABASE_URL = 'sqlite:///./runcoach.db'
```

This worked fine for a long time — until it very much didn't.

---

## The Bug That Wasn't

A user reported that after a morning run (Garmin → Strava auto-sync), the analytics dashboard still showed 18 total runs instead of 19. Clicking "Sync new runs" showed "Already up to date."

We dug in. The Strava sync code looked correct. We added timeouts, pagination caps, fixed a `sport_type` vs `type` field mismatch (Strava's newer API returns `sport_type="Run"` while the older `type` field may be null for Garmin-synced activities). We fixed a JavaScript scoping bug where `const AnalyticsDashboard` at the top level of a `<script>` tag doesn't attach to `window`, so `window.AnalyticsDashboard.reloadRuns()` was silently failing. We deployed.

Still 18 runs.

We SSH'd into the production machine and inserted a test run directly into the database. Checked the API — it returned it. Told the user to refresh. They couldn't see it.

We checked the database again. Zero rows.

---

## What Was Actually Happening

Fly.io machines with `auto_stop_machines = 'stop'` (the default for scale-to-zero) **stop the process and reset the container's root filesystem to the image state** when idle. Any writes to `/app/runcoach.db` — which lived inside the container — were lost every time the machine went idle and was woken up by the next request.

The sequence every single time:

1. Machine wakes from idle → starts from the image-baked `runcoach.db`
2. User loads analytics page → Strava sync fires, writes 31 runs to the DB
3. User sees 31 runs, everything looks fine
4. Machine goes idle after a few minutes of inactivity
5. Next request wakes the machine → **DB resets to 0 runs from the image**
6. Strava sync fires again on page load → re-fetches 31 runs, re-writes them
7. Go to step 3

It appeared to work. The data was there during an active session. But it was completely ephemeral — gone the moment the machine idled.

This explained everything:
- Test runs we inserted via SSH would disappear
- The Strava sync was working perfectly, just writing to a filesystem that wouldn't survive the next sleep cycle
- Every page load with Strava connected triggered a full re-sync (expensive, wasteful) because the DB was always empty on startup

---

## The Fix

Fly.io supports **persistent volumes** — block storage that survives machine restarts, stops, and even new deployments (as long as you keep the volume). The fix was three files.

### 1. Create the volume

```bash
fly volumes create runcoach_data --region sjc --size 1
```

1 GB, encrypted by default, snapshotted daily. Falls within Fly.io's free tier.

### 2. Mount it in `fly.toml`

```toml
[env]
  DATABASE_URL = 'sqlite:////data/runcoach.db'

[mounts]
  source = "runcoach_data"
  destination = "/data"
```

Four slashes in the SQLite URL: three for the `sqlite://` scheme, one for the absolute path.

### 3. A first boot that builds its own schema

The tricky part: on the very first deployment with a volume, the volume is empty. Nothing creates the schema unless something explicitly does.

The original fix baked the *current database* into the image as a seed snapshot and copied it onto the volume whenever the volume was empty:

```sh
# REMOVED — kept here only so the history reads honestly.
DB_PATH="/data/runcoach.db"
SEED_PATH="/app/runcoach.db.seed"
if [ ! -f "$DB_PATH" ]; then
    echo "[start.sh] Volume is empty — seeding from image snapshot..."
    cp "$SEED_PATH" "$DB_PATH"
fi
```

That has since been deleted, for three reasons:

- It works exactly once. The second time you change the schema, the snapshot is a lie — the volume gets an old schema and a fresh deploy of a *new* image would too.
- It makes the image a carrier of one developer's local database. `/app/runcoach.db` was never a production artifact.
- Alembic already knows how to build the schema from nothing, on the volume, before traffic moves.

First boot with an empty volume is therefore a plain migration run, as Fly's **release command**:

```toml
# fly.toml
[deploy]
  # One throwaway machine, volume attached, before traffic moves: a failing
  # migration aborts the deploy instead of shipping a machine that can never
  # pass its health check.
  release_command = 'python -m app.migrations'
```

`start.sh` is now only the entrypoint:

```sh
#!/bin/sh
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 30
```

Migrations deliberately do *not* run there. With `auto_stop_machines = 'stop'` the
machine wakes on the next request after idling, and replaying the Alembic chain
plus the startup backfills on every wake is pure waste — so `fly.toml` sets
`RUN_STARTUP_MIGRATIONS=false`. That flag defaults to **on** for local `uvicorn`
runs and plain `docker run`, where no release hook exists to do the work.

What the logs actually show, separated by where the work happens:

```
# the release machine, once per deploy (empty volume → full schema)
INFO  [alembic.runtime.migration] Running upgrade  -> 001_initial_schema, Initial migration - capture current schema state.

# the app machine, first boot and every wake after it
INFO  Mounting /dev/vdc at /data w/ uid: 1000, gid: 1000
INFO:  Application startup complete.
Health check 'servicecheck-00-http-8000' is now passing.
```

---

## What Changed

| | Before | After |
|---|---|---|
| DB location | `/app/runcoach.db` (container root fs) | `/data/runcoach.db` (persistent volume) |
| Survives machine idle | ❌ No | ✅ Yes |
| Survives redeploy | ❌ No | ✅ Yes |
| Provider sync on every page load | ✅ Re-syncs everything (wasteful) | ✅ Incremental (only new runs) |
| Cost | Free | Free (1 GB within free tier) |

---

## Lessons

**1. Fly.io root filesystems are ephemeral with `auto_stop = 'stop'`.** Data written to the container during a session is lost when the machine stops. This is not a bug, it's the expected behaviour for immutable-image deployments. If your app writes state, mount a volume.

**2. SQLite on Fly.io works great — with a volume.** The combination of scale-to-zero machines + a 1 GB volume is genuinely an excellent fit for small apps. No separate database service to manage, no connection pools, no network latency between app and DB.

**3. Let migrations own the schema — not a seed snapshot, and not `create_all()`.** The first version of this fix copied a baked-in database onto the empty volume, because "existing users need carrying over". That is a trap: it works once, and after that the snapshot is an old schema wearing a new image's tag. `create_all()` is the other dead end here — it creates *empty* tables, so the schema it builds is whatever the models happen to say today and quietly diverges from the migrations. One tool builds the schema, on the volume, before traffic moves: Alembic, via `release_command`.

**4. Test persistence explicitly, not just correctness.** The Strava sync code was correct all along. We kept fixing code that wasn't broken because we didn't yet know that persistence was the issue. A simple "insert a row, restart the machine, check if the row is still there" test would have caught this immediately.

---

## What's Next

With a persistent database, a few things become possible that weren't before:

- **Incremental sync** works as intended — the cursor is preserved across restarts, so page loads only fetch genuinely new activities (this was `strava_last_synced_at`; Intervals.icu owns the cursor now)
- **Offline-first analytics** — the dashboard can load from the local DB instantly, without waiting on a provider API call on every visit
- **Backups** — Fly.io snapshots the volume daily automatically; add `fly volumes snapshots` to your runbook

---

*RunCoach is a side project. The stack is intentionally boring — FastAPI, SQLite, a bit of Chart.js, deployed on Fly.io. The goal was always to keep it simple enough that one person can understand every part of it on a Sunday afternoon.*
