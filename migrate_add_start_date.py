"""Migration script to add start_date column to training_plans table."""

import sqlite3
import sys


def migrate(db_path: str = "runcoach.db") -> None:
    """Add start_date DATETIME column and backfill from created_at.

    Args:
        db_path: Path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(training_plans)")
        columns = [row[1] for row in cursor.fetchall()]

        if "start_date" in columns:
            print("Column 'start_date' already exists. Skipping migration.")
            return

        # Add the new column
        cursor.execute(
            "ALTER TABLE training_plans ADD COLUMN start_date DATETIME"
        )
        print("Added 'start_date' column to training_plans table.")

        # Backfill from created_at
        cursor.execute(
            "UPDATE training_plans SET start_date = created_at WHERE start_date IS NULL"
        )
        updated = cursor.rowcount
        print(f"Backfilled {updated} rows with created_at values.")

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
