#!/bin/sh
# Entrypoint for production (Fly.io).
#
# The SQLite database lives on a persistent Fly.io volume mounted at /data.
# On first boot Alembic migrations (run inside the FastAPI lifespan) create
# the schema automatically — no seed file needed.

python -c "from app.dependencies import engine; from app.migrations import run_alembic_migrations; run_alembic_migrations(engine)"

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 30
