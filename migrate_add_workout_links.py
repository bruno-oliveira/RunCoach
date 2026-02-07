"""Add training_plan_id and daily_workout_id to run_logs table."""

import sqlite3

def migrate():
    conn = sqlite3.connect('runcoach.db')
    cursor = conn.cursor()
    
    try:
        # Add training_plan_id column
        cursor.execute('''
            ALTER TABLE run_logs 
            ADD COLUMN training_plan_id TEXT
        ''')
        print("Added training_plan_id column")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("training_plan_id column already exists")
        else:
            raise
    
    try:
        # Add daily_workout_id column
        cursor.execute('''
            ALTER TABLE run_logs 
            ADD COLUMN daily_workout_id TEXT
        ''')
        print("Added daily_workout_id column")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("daily_workout_id column already exists")
        else:
            raise
    
    conn.commit()
    conn.close()
    print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()
