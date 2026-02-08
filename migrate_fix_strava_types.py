"""Migration to fix numeric column types in strava_activities table."""

import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    """Fix numeric column types in strava_activities table from INTEGER to REAL."""
    try:
        conn = sqlite3.connect('runcoach.db')
        cursor = conn.cursor()

        # Check if the table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='strava_activities'")
        if not cursor.fetchone():
            logger.info("strava_activities table does not exist yet, skipping migration")
            conn.close()
            return True

        # SQLite doesn't support ALTER COLUMN directly, so we need to:
        # 1. Create a new table with correct types
        # 2. Copy data from old table
        # 3. Drop old table
        # 4. Rename new table

        logger.info("Creating new strava_activities table with correct column types...")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strava_activities_new (
                id TEXT PRIMARY KEY,
                analytics_id TEXT NOT NULL,
                activity_id TEXT,
                date TIMESTAMP,
                activity_type TEXT,
                distance_km REAL,
                moving_time_seconds INTEGER,
                elapsed_time_seconds INTEGER,
                avg_speed REAL,
                max_speed REAL,
                avg_heart_rate INTEGER,
                max_heart_rate INTEGER,
                elevation_gain_meters REAL,
                elevation_loss_meters REAL,
                calories INTEGER,
                raw_data TEXT,
                FOREIGN KEY (analytics_id) REFERENCES strava_analytics(id) ON DELETE CASCADE
            )
        """)

        # Check if old table has data
        cursor.execute("SELECT COUNT(*) FROM strava_activities")
        count = cursor.fetchone()[0]
        
        if count > 0:
            logger.info(f"Copying {count} records from old table to new table...")
            cursor.execute("""
                INSERT INTO strava_activities_new 
                SELECT * FROM strava_activities
            """)
        
        logger.info("Dropping old table...")
        cursor.execute("DROP TABLE strava_activities")
        
        logger.info("Renaming new table...")
        cursor.execute("ALTER TABLE strava_activities_new RENAME TO strava_activities")
        
        conn.commit()
        logger.info("Migration completed successfully")
        
        conn.close()
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if migrate():
        print("Migration completed successfully!")
    else:
        print("Migration failed!")
