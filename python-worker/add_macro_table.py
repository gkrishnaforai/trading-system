#!/usr/bin/env python3
"""
Add missing macro_market_data table
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv

def add_macro_market_data_table():
    """Add the missing macro_market_data table"""
    
    load_dotenv()
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ DATABASE_URL not found")
        return False
    
    print("🔧 Adding macro_market_data table...")
    
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Create the table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS macro_market_data (
            id SERIAL PRIMARY KEY,
            data_date DATE NOT NULL UNIQUE,
            vix_close NUMERIC(8, 2),
            nasdaq_symbol VARCHAR(10),
            nasdaq_close NUMERIC(12, 4),
            nasdaq_sma50 NUMERIC(12, 4),
            nasdaq_sma200 NUMERIC(12, 4),
            tnx_yield NUMERIC(6, 4),
            irx_yield NUMERIC(6, 4),
            yield_curve_spread NUMERIC(6, 4),
            sp500_above_50d_pct NUMERIC(5, 4),
            source VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        cursor.execute(create_table_sql)
        print("   ✅ Created macro_market_data table")
        
        # Create index
        create_index_sql = """
        CREATE INDEX IF NOT EXISTS idx_macro_date 
        ON macro_market_data(data_date DESC)
        """
        
        cursor.execute(create_index_sql)
        print("   ✅ Created idx_macro_date index")
        
        # Verify table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'macro_market_data'
            )
        """)
        
        table_exists = cursor.fetchone()[0]
        print(f"📊 Table exists: {table_exists}")
        
        cursor.close()
        conn.close()
        
        print("✅ macro_market_data table added successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = add_macro_market_data_table()
    
    if success:
        print("\n📋 Next Steps:")
        print("1. Restart python-worker:")
        print("   docker-compose restart python-worker")
        print("2. Test macro data endpoint:")
        print("   curl http://localhost:8001/admin/data-summary/macro_market_data")
        print("3. Trigger macro refresh:")
        print("   curl -X POST http://localhost:8001/refresh")
    else:
        print("❌ Failed to add table")
        sys.exit(1)
