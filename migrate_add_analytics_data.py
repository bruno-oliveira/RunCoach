"""Migration to add analytics_data column to strava_analytics table."""

import sqlite3
import logging

logger = logging.getLogger(__name__)

def migrate():
    """Add analytics_data column to strava_analytics table."""
    try:
        conn = sqlite3.connect('runcoach.db')
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(strava_analytics)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'analytics_data' not in columns:
            logger.info("Adding analytics_data column to strava_analytics table...")
            cursor.execute("ALTER TABLE strava_analytics ADD COLUMN analytics_data TEXT")
            conn.commit()
            logger.info("Migration completed successfully")
        else:
            logger.info("analytics_data column already exists")

        conn.close()
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


if __name__ == "__main__":
    if migrate():
        print("Migration completed successfully!")
    else:
        print("Migration failed!")