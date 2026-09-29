#!/bin/sh
# Entrypoint for production (Fly.io).
#
# The SQLite database lives on a persistent Fly.io volume mounted at /data.
#
# Migrations are NOT applied here. They run as Fly's release command
# (`python -m app.migrations`, see the [deploy] block in fly.toml), which
# executes on a temporary machine with the volume attached *before* traffic
# moves — so a failing migration aborts the deploy instead of producing a
# machine that never passes its health check. For the same reason fly.toml sets
# RUN_STARTUP_MIGRATIONS=false, so the FastAPI lifespan does not repeat the work
# on every wake from scale-to-zero.

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 30
