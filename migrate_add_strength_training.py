"""Create strength training tables and populate with exercise data."""

import json
import sys
from sqlalchemy import text

from app.dependencies import engine


def create_tables():
    """Create strength training tables."""
    try:
        with engine.connect() as conn:
            # Check if strength_exercises table already exists
            result = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='strength_exercises'"
                )
            ).fetchone()
            
            if result:
                print("Table 'strength_exercises' already exists. Skipping table creation.")
                return False
            
            # Create strength_exercises table
            conn.execute(
                text(
                    """
                    CREATE TABLE strength_exercises (
                        id VARCHAR PRIMARY KEY,
                        name VARCHAR NOT NULL,
                        exercise_id VARCHAR NOT NULL UNIQUE,
                        force VARCHAR,
                        level VARCHAR,
                        mechanic VARCHAR,
                        equipment VARCHAR,
                        primary_muscles TEXT,
                        secondary_muscles TEXT,
                        instructions TEXT,
                        category VARCHAR,
                        target_muscles TEXT,
                        images TEXT,
                        gif_url VARCHAR,
                        is_running_related BOOLEAN DEFAULT 0,
                        is_bodyweight BOOLEAN DEFAULT 0,
                        is_dumbbell BOOLEAN DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            
            # Create indexes
            conn.execute(
                text(
                    "CREATE INDEX ix_strength_exercises_name ON strength_exercises (name)"
                )
            )
            
            conn.execute(
                text(
                    "CREATE INDEX ix_strength_exercises_is_running_related ON strength_exercises (is_running_related)"
                )
            )
            
            conn.execute(
                text(
                    "CREATE INDEX ix_strength_exercises_is_bodyweight ON strength_exercises (is_bodyweight)"
                )
            )
            
            conn.execute(
                text(
                    "CREATE INDEX ix_strength_exercises_is_dumbbell ON strength_exercises (is_dumbbell)"
                )
            )
            
            # Create daily_strength_workouts table
            conn.execute(
                text(
                    """
                    CREATE TABLE daily_strength_workouts (
                        id VARCHAR PRIMARY KEY,
                        date VARCHAR NOT NULL,
                        title VARCHAR NOT NULL,
                        description TEXT,
                        warmup_exercises TEXT,
                        main_exercises TEXT,
                        cooldown_exercises TEXT,
                        warmup_duration INTEGER DEFAULT 5,
                        main_duration INTEGER DEFAULT 25,
                        cooldown_duration INTEGER DEFAULT 5,
                        total_duration INTEGER DEFAULT 35,
                        primary_focus VARCHAR,
                        secondary_focus VARCHAR,
                        difficulty VARCHAR DEFAULT 'beginner',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(date)
                    )
                    """
                )
            )
            
            # Create indexes for daily_strength_workouts
            conn.execute(
                text(
                    "CREATE INDEX ix_daily_strength_workouts_date ON daily_strength_workouts (date)"
                )
            )
            
            # Create user_favorite_workouts table
            conn.execute(
                text(
                    """
                    CREATE TABLE user_favorite_workouts (
                        id VARCHAR PRIMARY KEY,
                        user_id VARCHAR NOT NULL,
                        workout_id VARCHAR NOT NULL,
                        notes VARCHAR,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id),
                        FOREIGN KEY (workout_id) REFERENCES daily_strength_workouts (id),
                        UNIQUE(user_id, workout_id)
                    )
                    """
                )
            )
            
            # Create indexes for user_favorite_workouts
            conn.execute(
                text(
                    "CREATE INDEX ix_user_favorite_workouts_user_id ON user_favorite_workouts (user_id)"
                )
            )
            
            conn.execute(
                text(
                    "CREATE INDEX ix_user_favorite_workouts_workout_id ON user_favorite_workouts (workout_id)"
                )
            )
            
            conn.commit()
            print("Successfully created strength training tables")
            return True
            
    except Exception as e:
        print(f"Error during table creation: {e}")
        sys.exit(1)


def populate_exercises():
    """Populate strength_exercises table with data from JSON file."""
    try:
        # Read the JSON file
        with open("strength_exercises.json", "r") as f:
            exercises_data = json.load(f)
        
        print(f"Loading {len(exercises_data)} exercises into database...")
        
        with engine.connect() as conn:
            for exercise in exercises_data:
                conn.execute(
                    text(
                        """
                        INSERT INTO strength_exercises (
                            id, name, exercise_id, force, level, mechanic, equipment,
                            primary_muscles, secondary_muscles, instructions, category,
                            target_muscles, images, gif_url, is_running_related,
                            is_bodyweight, is_dumbbell
                        ) VALUES (
                            lower(hex(randomblob(16))), :name, :exercise_id, :force, :level,
                            :mechanic, :equipment, :primary_muscles, :secondary_muscles,
                            :instructions, :category, :target_muscles, :images, :gif_url,
                            :is_running_related, :is_bodyweight, :is_dumbbell
                        )
                        """
                    ),
                    {
                        "name": exercise["name"],
                        "exercise_id": exercise["exercise_id"],
                        "force": exercise.get("force"),
                        "level": exercise.get("level"),
                        "mechanic": exercise.get("mechanic"),
                        "equipment": exercise.get("equipment"),
                        "primary_muscles": exercise.get("primary_muscles"),
                        "secondary_muscles": exercise.get("secondary_muscles"),
                        "instructions": exercise.get("instructions"),
                        "category": exercise.get("category"),
                        "target_muscles": exercise.get("target_muscles"),
                        "images": exercise.get("images"),
                        "gif_url": exercise.get("gif_url"),
                        "is_running_related": 1 if exercise.get("is_running_related") else 0,
                        "is_bodyweight": 1 if exercise.get("is_bodyweight") else 0,
                        "is_dumbbell": 1 if exercise.get("is_dumbbell") else 0,
                    }
                )
            
            conn.commit()
            print(f"Successfully loaded {len(exercises_data)} exercises")
            
    except Exception as e:
        print(f"Error during exercise population: {e}")
        sys.exit(1)


def main():
    """Run migration."""
    print("Starting strength training migration...")
    
    # Create tables
    tables_created = create_tables()
    
    if tables_created:
        # Populate exercises
        populate_exercises()
    else:
        print("Tables already exist. Skipping data population.")
    
    print("Migration complete!")


if __name__ == "__main__":
    main()
