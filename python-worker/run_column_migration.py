#!/usr/bin/env python3
"""
Run Column Naming Consistency Migration
Fixes column names from stock_symbol/trade_date to symbol/date
"""

import os
import sys
import psycopg2
from psycopg2 import OperationalError
from dotenv import load_dotenv

def run_column_naming_migration():
    """Run the column naming consistency migration"""
    
    # Load environment variables
    load_dotenv()
    
    # Get database connection string
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        return False
    
    print("🔧 Running Column Naming Consistency Migration...")
    print("=" * 60)
    
    try:
        # Connect to PostgreSQL database
        print("📡 Connecting to database...")
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Get the migration file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        migration_file = os.path.join(current_dir, 'migrations', '029_fix_column_naming_consistency.sql')
        
        if not os.path.exists(migration_file):
            print(f"❌ Migration file not found: {migration_file}")
            return False
        
        print(f"📄 Running migration: {migration_file}")
        
        # Read and execute the migration
        with open(migration_file, 'r') as file:
            migration_sql = file.read()
        
        print("🔨 Executing migration...")
        cursor.execute(migration_sql)
        
        print("✅ Migration completed successfully!")
        
        # Verify the fixes
        print("\n🔍 Verifying column fixes...")
        
        # Check raw_market_data_daily
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'raw_market_data_daily' 
            AND column_name IN ('symbol', 'date', 'stock_symbol', 'trade_date')
            ORDER BY column_name
        """)
        columns = [row[0] for row in cursor.fetchall()]
        print(f"📊 raw_market_data_daily columns: {columns}")
        
        # Check indicators_daily
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'indicators_daily' 
            AND column_name IN ('symbol', 'date', 'stock_symbol', 'trade_date')
            ORDER BY column_name
        """)
        columns = [row[0] for row in cursor.fetchall()]
        print(f"📊 indicators_daily columns: {columns}")
        
        # Check data_ingestion_state
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'data_ingestion_state' 
            AND column_name IN ('symbol', 'stock_symbol')
            ORDER BY column_name
        """)
        columns = [row[0] for row in cursor.fetchall()]
        print(f"📊 data_ingestion_state columns: {columns}")
        
        # Check industry_peers
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'industry_peers' 
            AND column_name IN ('symbol', 'stock_symbol')
            ORDER BY column_name
        """)
        columns = [row[0] for row in cursor.fetchall()]
        print(f"📊 industry_peers columns: {columns}")
        
        # Close connection
        cursor.close()
        conn.close()
        
        print("\n🎉 Column naming migration completed!")
        print("🔄 You can now restart the python-worker service")
        
        return True
        
    except OperationalError as e:
        print(f"❌ Database connection error: {e}")
        print("🔧 Please check your DATABASE_URL configuration")
        return False
        
    except Exception as e:
        print(f"❌ Error running migration: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function"""
    success = run_column_naming_migration()
    
    if success:
        print("\n📋 Next Steps:")
        print("1. Restart the python-worker service:")
        print("   docker-compose restart python-worker")
        print("2. Test bulk stock loading:")
        print("   curl -X POST http://localhost:8001/api/v1/bulk/stocks/load/popular")
        print("3. Test market data refresh:")
        print("   curl -X POST http://localhost:8001/refresh")
        print("4. Check table status:")
        print("   python check_tables.py")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
