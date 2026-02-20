"""Migration: add strava_adapted_multiplier column to training_plans table."""

import sqlite3
import sys


def migrate(db_path: str = "runcoach.db") -> None:
    """Add strava_adapted_multiplier FLOAT column (nullable) to training_plans.

    This column stores the last Strava-fitness multiplier applied to the plan so
    that subsequent adaptations can reverse the previous adjustment before
    applying a new one, preventing distances from compounding on repeated calls.

    Args:
        db_path: Path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(training_plans)")
        columns = [row[1] for row in cursor.fetchall()]

        if "strava_adapted_multiplier" in columns:
            print("Column 'strava_adapted_multiplier' already exists. Skipping migration.")
            return

        cursor.execute(
            "ALTER TABLE training_plans ADD COLUMN strava_adapted_multiplier REAL"
        )
        print("Added 'strava_adapted_multiplier' column to training_plans table.")

        conn.commit()
        print("Migration completed successfully.")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "runcoach.db"
    migrate(db)
