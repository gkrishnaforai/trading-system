#!/usr/bin/env python3
"""
Simple Stock Grades Migration Runner
Follows the same pattern as run_column_migration.py
"""

import os
import sys
import psycopg2
from psycopg2 import OperationalError
from dotenv import load_dotenv

def run_stock_grades_migrations():
    """Run all stock grades migrations using simple psycopg2 approach"""
    
    # Load environment variables
    load_dotenv()
    
    # Get database connection string
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        return False
    
    print("🚀 Running Stock Grades System Migrations...")
    print("=" * 60)
    
    migration_files = [
        "007_stock_grades_system.sql",
        "008_consensus_system.sql", 
        "009_alerts_integration.sql",
        "010_stock_grades_indexes.sql"
    ]
    
    try:
        # Connect to PostgreSQL database
        print("📡 Connecting to database...")
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        migrations_dir = os.path.dirname(os.path.abspath(__file__))
        
        for migration_file in migration_files:
            migration_path = os.path.join(migrations_dir, 'migrations', migration_file)
            
            if not os.path.exists(migration_path):
                print(f"⚠️  Migration file not found: {migration_file}")
                continue
            
            print(f"📄 Running migration: {migration_file}")
            
            try:
                # Read and execute the migration
                with open(migration_path, 'r') as file:
                    migration_sql = file.read()
                
                print(f"🔨 Executing migration...")
                cursor.execute(migration_sql)
                print(f"✅ {migration_file} completed successfully!")
                
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"⚠️  {migration_file} skipped (already exists): {e}")
                    continue
                else:
                    print(f"❌ {migration_file} failed: {e}")
                    raise
        
        # Close connection
        cursor.close()
        conn.close()
        
        print("\n🎉 All stock grades migrations completed!")
        return True
        
    except OperationalError as e:
        print(f"❌ Database connection error: {e}")
        print("🔧 Please check your DATABASE_URL configuration")
        return False
        
    except Exception as e:
        print(f"❌ Error running migrations: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function"""
    print("📋 Running Stock Grades Migrations...")
    
    # First run the trigger functions fix
    print("\n🔧 Step 1: Creating trigger functions...")
    try:
        from create_trigger_functions_simple import main as fix_triggers
        fix_triggers()
        print("✅ Trigger functions created successfully!")
    except Exception as e:
        print(f"⚠️  Trigger functions failed: {e}")
        print("🔧 Continuing with migrations...")
    
    # Then run the migrations
    print("\n🔧 Step 2: Running database migrations...")
    success = run_stock_grades_migrations()
    
    if success:
        # Finally create remaining triggers
        print("\n🔧 Step 3: Creating remaining triggers...")
        try:
            from create_remaining_triggers import main as create_triggers
            create_triggers()
            print("✅ Remaining triggers created successfully!")
        except Exception as e:
            print(f"⚠️  Remaining triggers failed: {e}")
            print("🔧 But migrations completed successfully!")
    
    if success:
        print("\n🎉 Stock grades system setup completed!")
        print("\n📋 Next Steps:")
        print("1. Test the API endpoints:")
        print("   curl http://localhost:8001/api/v2/stock-grades/coverage-stats")
        print("2. Load sample data:")
        print("   curl -X POST http://localhost:8001/api/v2/stock-grades/refresh/AAPL")
        print("3. Check the system status:")
        print("   python check_tables.py")
        sys.exit(0)
    else:
        print("\n❌ Migrations failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
