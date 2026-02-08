#!/usr/bin/env python3
"""
Script to run the consensus table fix migration
"""

import os
import sys

# Add the app directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import db

def run_migration():
    """Run the consensus table fix migration"""
    try:
        # Read the migration file
        migration_file = "/Users/krishnag/tools/trading-system/python-worker/migrations/019_fix_consensus_table_updated_at.sql"
        
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        # Execute the migration
        with db.get_session() as session:
            session.execute(migration_sql)
            session.commit()
            
        print("✅ Successfully applied consensus table fix migration")
        return True
        
    except Exception as e:
        print(f"❌ Error running migration: {e}")
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
