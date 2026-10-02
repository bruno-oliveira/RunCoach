#!/bin/sh
# Entrypoint for production (Fly.io).
#
# The SQLite database lives on a persistent Fly.io volume mounted at /data.
#
# Migrations are applied HERE, on the app machine, because it is the only
# machine that has the volume. They used to run as Fly's release command, on
# the belief that a release machine mounts the volume. It does not: it got an
# empty /data, built a brand-new database from revision 001 to head, exited 0,
# and was thrown away — so every deploy "migrated successfully" while the real
# database stayed where it was, and the first schema change shipped that way
# took the site down with `no such column`.
#
# A failed migration stops the machine from serving (non-zero exit, no uvicorn)
# rather than letting it answer every request with a 500 on a stale schema.
# fly.toml keeps RUN_STARTUP_MIGRATIONS=false so the FastAPI lifespan does not
# run the same work a second time.

set -e

python -m app.migrations

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 30
