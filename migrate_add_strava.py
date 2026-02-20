"""Migration: Add Strava integration columns to users and run_logs tables."""

import sqlite3
import sys


def migrate(db_path: str = "runcoach.db") -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get existing columns for users table
    cursor.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in cursor.fetchall()}

    # Rename legacy strava_id -> strava_athlete_id if present
    if "strava_id" in user_columns and "strava_athlete_id" not in user_columns:
        cursor.execute("ALTER TABLE users RENAME COLUMN strava_id TO strava_athlete_id")
        user_columns.discard("strava_id")
        user_columns.add("strava_athlete_id")
        print("Renamed users.strava_id -> strava_athlete_id")

    user_additions = {
        "strava_athlete_id": "TEXT UNIQUE",
        "strava_access_token": "TEXT",
        "strava_refresh_token": "TEXT",
        "strava_token_expires_at": "INTEGER",
    }

    for col, col_type in user_additions.items():
        if col not in user_columns:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            print(f"Added users.{col}")
        else:
            print(f"users.{col} already exists, skipping")

    # Get existing columns for run_logs table
    cursor.execute("PRAGMA table_info(run_logs)")
    run_log_columns = {row[1] for row in cursor.fetchall()}

    if "strava_activity_id" not in run_log_columns:
        cursor.execute("ALTER TABLE run_logs ADD COLUMN strava_activity_id TEXT UNIQUE")
        print("Added run_logs.strava_activity_id")
    else:
        print("run_logs.strava_activity_id already exists, skipping")

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "runcoach.db"
    migrate(db_path)
