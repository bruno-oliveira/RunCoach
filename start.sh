#!/bin/sh
# Entrypoint for production (Fly.io).
#
# The SQLite database lives on a persistent Fly.io volume mounted at /data.
# On first boot Alembic migrations (run inside the FastAPI lifespan) create
# the schema automatically — no seed file needed.

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 30
