"""Add last_activity column to users table for inactivity timeout."""

import sqlite3

def migrate():
    conn = sqlite3.connect('runcoach.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            ALTER TABLE users 
            ADD COLUMN last_activity TIMESTAMP
        ''')
        print("Added last_activity column")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("last_activity column already exists")
        else:
            raise
    
    conn.commit()
    conn.close()
    print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()
