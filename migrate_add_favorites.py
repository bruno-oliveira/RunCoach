"""Add favorite_recipes table for storing user's favorite recipes."""

import sys
from sqlalchemy import text

from app.dependencies import engine


def migrate():
    """Create the favorite_recipes table if it doesn't exist."""
    try:
        with engine.connect() as conn:
            # Check if table already exists
            result = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='favorite_recipes'"
                )
            ).fetchone()
            
            if result:
                print("Table 'favorite_recipes' already exists. Skipping migration.")
                return
            
            # Create the favorite_recipes table
            conn.execute(
                text(
                    """
                    CREATE TABLE favorite_recipes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id VARCHAR NOT NULL,
                        recipe_name VARCHAR NOT NULL,
                        meal_type VARCHAR NOT NULL,
                        recipe_data VARCHAR NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                    """
                )
            )
            
            # Create indexes
            conn.execute(
                text(
                    "CREATE INDEX ix_favorite_recipes_user_id ON favorite_recipes (user_id)"
                )
            )
            
            conn.execute(
                text(
                    "CREATE INDEX ix_favorite_recipes_user_recipe ON favorite_recipes (user_id, recipe_name)"
                )
            )
            
            conn.commit()
            print("Successfully created favorite_recipes table")
            
    except Exception as e:
        print(f"Error during migration: {e}")
        sys.exit(1)


if __name__ == "__main__":
    migrate()
