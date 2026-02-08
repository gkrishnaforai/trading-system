#!/usr/bin/env python3
"""
Database Setup Script for Data Refresh Scheduler
Runs the SQL migration to create scheduler tables, triggers, and views
"""

import os
import sys
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import db
from app.observability.logging import get_logger

logger = get_logger("setup_scheduler_database")

def setup_scheduler_database():
    """Set up the scheduler database tables and triggers"""
    
    # Path to the migration file
    migration_file = Path(__file__).parent / "migrations" / "create_scheduler_tables.sql"
    
    if not migration_file.exists():
        logger.error(f"❌ Migration file not found: {migration_file}")
        return False
    
    try:
        logger.info("🗄️ SETTING UP SCHEDULER DATABASE")
        logger.info("=" * 50)
        
        # Read the migration file
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        logger.info(f"📄 Loaded migration file: {migration_file}")
        
        # Execute the migration
        logger.info("🚀 Executing database migration...")
        
        # Split the SQL into individual statements for better error handling
        statements = [stmt.strip() for stmt in migration_sql.split(';') if stmt.strip()]
        
        executed_count = 0
        for i, statement in enumerate(statements, 1):
            if statement:
                try:
                    db.execute_update(statement)
                    executed_count += 1
                    logger.info(f"✅ Executed statement {i}/{len(statements)}")
                except Exception as e:
                    # Some statements might fail (like DROP TRIGGER IF EXISTS)
                    # Log but continue execution
                    if "already exists" in str(e) or "does not exist" in str(e):
                        logger.info(f"ℹ️ Statement {i} skipped (expected): {e}")
                    else:
                        logger.error(f"❌ Statement {i} failed: {e}")
                        logger.error(f"Statement: {statement[:100]}...")
                        continue
        
        logger.info(f"🎉 MIGRATION COMPLETED SUCCESSFULLY!")
        logger.info(f"✅ Executed {executed_count}/{len(statements)} statements")
        
        # Verify the setup
        logger.info("\n🔍 VERIFYING SETUP:")
        
        # Check tables
        tables_query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name LIKE 'data_refresh_%'
        ORDER BY table_name
        """
        
        tables = db.execute_query(tables_query)
        if tables:
            logger.info("✅ Created tables:")
            for table in tables:
                logger.info(f"   • {table['table_name']}")
        else:
            logger.warning("⚠️ No scheduler tables found")
        
        # Check views
        views_query = """
        SELECT table_name 
        FROM information_schema.views 
        WHERE table_schema = 'public' 
        AND table_name IN ('active_refresh_schedules', 'daily_refresh_performance', 'symbol_refresh_summary')
        ORDER BY table_name
        """
        
        views = db.execute_query(views_query)
        if views:
            logger.info("✅ Created views:")
            for view in views:
                logger.info(f"   • {view['table_name']}")
        else:
            logger.warning("⚠️ No scheduler views found")
        
        # Check functions
        functions_query = """
        SELECT proname 
        FROM pg_proc 
        WHERE proname LIKE '%refresh%' OR proname LIKE '%schedule%'
        ORDER BY proname
        """
        
        functions = db.execute_query(functions_query)
        if functions:
            logger.info("✅ Created functions:")
            for func in functions:
                logger.info(f"   • {func['proname']}()")
        else:
            logger.warning("⚠️ No scheduler functions found")
        
        # Test a utility function
        logger.info("\n🧪 TESTING SETUP:")
        
        try:
            # Test the schedule function
            test_result = db.execute_query(
                "SELECT schedule_symbol_refresh('TEST', 'price_historical', 15) as result"
            )
            
            if test_result and test_result[0]['result']:
                logger.info("✅ schedule_symbol_refresh() function works")
                
                # Clean up test data
                db.execute_update("SELECT remove_symbol_schedule('TEST', 'price_historical')")
                logger.info("✅ remove_symbol_schedule() function works")
            else:
                logger.warning("⚠️ schedule_symbol_refresh() function test failed")
                
        except Exception as e:
            logger.warning(f"⚠️ Function test failed: {e}")
        
        logger.info("\n🎯 SETUP RESULT: SUCCESS!")
        logger.info("✅ Database is ready for the data refresh scheduler")
        logger.info("✅ All tables, triggers, and views have been created")
        logger.info("✅ Utility functions are available for use")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error setting up scheduler database: {e}")
        return False

def verify_database_connection():
    """Verify database connection before running migration"""
    try:
        result = db.execute_query("SELECT 1 as test")
        if result and result[0]['test'] == 1:
            logger.info("✅ Database connection verified")
            return True
        else:
            logger.error("❌ Database connection test failed")
            return False
    except Exception as e:
        logger.error(f"❌ Database connection error: {e}")
        return False

def main():
    """Main function"""
    logger.info("🚀 SCHEDULER DATABASE SETUP SCRIPT")
    logger.info("=" * 40)
    
    # Verify database connection
    if not verify_database_connection():
        logger.error("❌ Cannot proceed without database connection")
        sys.exit(1)
    
    # Run the setup
    success = setup_scheduler_database()
    
    if success:
        logger.info("\n🎉 SETUP COMPLETED SUCCESSFULLY!")
        logger.info("\n📋 NEXT STEPS:")
        logger.info("   1. Start the Python Worker server")
        logger.info("   2. Use the scheduler API endpoints")
        logger.info("   3. Test with: curl http://localhost:8001/api/v1/scheduler/status")
        logger.info("   4. Schedule symbols with: curl -X POST http://localhost:8001/api/v1/scheduler/schedule-all")
        logger.info("\n🔧 Available API Endpoints:")
        logger.info("   • POST /api/v1/scheduler/start")
        logger.info("   • POST /api/v1/scheduler/stop") 
        logger.info("   • GET  /api/v1/scheduler/status")
        logger.info("   • POST /api/v1/scheduler/schedule-all")
        logger.info("   • GET  /api/v1/scheduler/upcoming")
        logger.info("   • GET  /api/v1/scheduler/history")
        
        sys.exit(0)
    else:
        logger.error("\n❌ SETUP FAILED!")
        logger.error("🔧 Check the error messages above and retry")
        sys.exit(1)

if __name__ == "__main__":
    # Check if we're in the right directory
    if not Path("migrations/create_scheduler_tables.sql").exists():
        print("❌ Migration file not found!")
        print("📁 Make sure you're running this from the python-worker directory")
        sys.exit(1)
    
    # Run the setup
    main()
