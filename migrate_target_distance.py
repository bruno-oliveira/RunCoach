#!/usr/bin/env python3
"""
Database migration script to update target_distance column from Float to String.
Run this script to update existing databases to support trail running.
"""

import sqlite3
import os
from pathlib import Path

def migrate_database():
    """Migrate the database to support trail running target distances."""
    
    # Find the database file
    db_paths = [
        'app.db',
        'runcoach.db',
        'database.db',
        'data.db'
    ]
    
    db_path = None
    for path in db_paths:
        if os.path.exists(path):
            db_path = path
            break
    
    if not db_path:
        # Look in common directories
        for base_dir in ['.', 'data', 'app']:
            for path in db_paths:
                full_path = os.path.join(base_dir, path)
                if os.path.exists(full_path):
                    db_path = full_path
                    break
            if db_path:
                break
    
    if not db_path:
        print("❌ No database file found. Please specify the database path.")
        return False
    
    print(f"📁 Found database: {db_path}")
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if target_distance column exists and its type
        cursor.execute("PRAGMA table_info(training_plans)")
        columns = cursor.fetchall()
        
        target_distance_col = None
        max_runs_col = None
        
        for col in columns:
            if col[1] == 'target_distance':
                target_distance_col = col
            elif col[1] == 'max_runs_per_week':
                max_runs_col = col
        
        if not target_distance_col:
            print("❌ target_distance column not found in training_plans table")
            return False
        
        print(f"📋 Current target_distance column: {target_distance_col[2]}")
        
        if target_distance_col[2].upper() == 'TEXT':
            print("✅ target_distance column is already TEXT - no migration needed")
            return True
        
        # Create backup
        backup_path = f"{db_path}.backup"
        print(f"💾 Creating backup: {backup_path}")
        
        # Backup entire database
        with sqlite3.connect(backup_path) as backup_conn:
            conn.backup(backup_conn)
        
        # Begin transaction
        conn.execute("BEGIN TRANSACTION")
        
        try:
            # Build the CREATE TABLE statement based on existing columns
            create_cols = []
            select_cols = []
            insert_cols = []
            
            for col in columns:
                col_name = col[1]
                col_type = col[2]
                
                # Map column types
                if col_name == 'target_distance':
                    create_cols.append(f"{col_name} TEXT")
                elif col_name == 'id':
                    create_cols.append(f"{col_name} TEXT PRIMARY KEY")
                else:
                    create_cols.append(f"{col_name} {col_type}")
                
                select_cols.append(col_name)
                insert_cols.append(col_name)
            
            # Add max_runs_per_week if it doesn't exist
            if not max_runs_col:
                create_cols.append("max_runs_per_week INTEGER DEFAULT 4")
                # Don't add to select_cols since it doesn't exist in old table
            else:
                insert_cols.append("max_runs_per_week")
            
            # 1. Create new table with TEXT column
            create_sql = f"CREATE TABLE training_plans_new ({', '.join(create_cols)})"
            cursor.execute(create_sql)
            
            # 2. Copy data from old table to new table
            select_sql = f"SELECT {', '.join(select_cols)} FROM training_plans"
            insert_sql = f"INSERT INTO training_plans_new ({', '.join(insert_cols)}) {select_sql}"
            cursor.execute(insert_sql)
            
            # 3. Drop old table
            cursor.execute("DROP TABLE training_plans")
            
            # 4. Rename new table
            cursor.execute("ALTER TABLE training_plans_new RENAME TO training_plans")
            
            # 5. Recreate indexes if needed
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_training_plans_user_id ON training_plans(user_id)")
            
            conn.commit()
            print("✅ Migration completed successfully")
            
            # Verify the change
            cursor.execute("PRAGMA table_info(training_plans)")
            new_columns = cursor.fetchall()
            
            for col in new_columns:
                if col[1] == 'target_distance':
                    print(f"📋 New target_distance column: {col[2]}")
                    break
            
            return True
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Migration failed: {e}")
            print("🔄 Restoring from backup...")
            
            # Restore from backup
            with sqlite3.connect(backup_path) as backup_conn:
                backup_conn.backup(conn)
            
            return False
            
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False
        
    finally:
        conn.close()

if __name__ == "__main__":
    print("🔄 RunCoach Database Migration")
    print("=" * 40)
    
    success = migrate_database()
    
    if success:
        print("\n🎉 Migration completed successfully!")
        print("📝 The database now supports trail running target distances.")
    else:
        print("\n❌ Migration failed. Please check the error messages above.")
        print("💡 You may need to manually update the database or start with a fresh database.")