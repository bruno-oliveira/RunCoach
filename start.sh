#!/bin/sh
# Entrypoint for production (Fly.io).
#
# The SQLite database lives on a persistent Fly.io volume mounted at /data.
# On the very first boot (empty volume) we seed it from the snapshot that was
# baked into the image at build time, so existing users and training plans are
# carried over automatically.

DB_PATH="/data/runcoach.db"
SEED_PATH="/app/runcoach.db.seed"

if [ ! -f "$DB_PATH" ]; then
    echo "[start.sh] Volume is empty — seeding database from image snapshot..."
    cp "$SEED_PATH" "$DB_PATH"
    echo "[start.sh] Database seeded at $DB_PATH"
else
    echo "[start.sh] Existing database found at $DB_PATH — skipping seed."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
