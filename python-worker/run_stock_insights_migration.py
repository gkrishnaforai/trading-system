#!/usr/bin/env python3
"""
Stock Insights Database Migration Script
Creates the stock_insights_snapshots table for enhanced recommendations
"""

import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def run_stock_insights_migration():
    """Run the Stock Insights table creation migration"""
    print("📊 RUNNING STOCK INSIGHTS DATABASE MIGRATION")
    print("=" * 50)
    
    try:
        # Get database URL from environment
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            print("❌ DATABASE_URL not found in environment variables")
            return False
        
        print(f"🔌 Connecting to database...")
        
        # Read the migration SQL file
        migration_file = "migrations/create_stock_insights_table.sql"
        
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        print(f"📄 Reading migration from: {migration_file}")
        
        # Connect directly with psycopg2
        conn = psycopg2.connect(db_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        with conn.cursor() as cursor:
            # Execute the migration
            statements = [stmt.strip() for stmt in migration_sql.split(';') if stmt.strip()]
            
            for i, statement in enumerate(statements, 1):
                print(f"🚀 Executing statement {i}/{len(statements)}...")
                cursor.execute(statement)
        
        conn.close()
        print("✅ Stock Insights migration completed successfully!")
        
        # Verify table was created
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT table_name, column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'stock_insights_snapshots'
                ORDER BY ordinal_position;
            """)
            
            columns = cursor.fetchall()
            if columns:
                print(f"✅ Table 'stock_insights_snapshots' verified with {len(columns)} columns:")
                for col in columns:
                    print(f"   • {col[0]}.{col[1]} ({col[2]})")
            else:
                print("❌ Table not found after migration")
                return False
        
        conn.close()
        return True
            
    except FileNotFoundError:
        print(f"❌ Migration file not found: {migration_file}")
        return False
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error running Stock Insights migration: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Stock Insights Table Migration")
    print("=" * 40)
    
    success = run_stock_insights_migration()
    
    if success:
        print("\n🎉 STOCK INSIGHTS MIGRATION COMPLETED!")
        print("\n✅ You can now:")
        print("   • Run: streamlit run streamlit_trading_dashboard.py")
        print("   • Test enhanced overall recommendations")
        print("   • View entry/exit plans with reasoning")
    else:
        print("\n❌ Migration failed. Please check the error above.")
        print("   • Ensure DATABASE_URL is set correctly")
        print("   • Ensure you have database permissions")
