#!/usr/bin/env python3
"""
Create Missing Market Data Tables
Creates the raw_market_data_intraday table and any other missing tables
"""

import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import db
from sqlalchemy import text

def create_intraday_table():
    """Create the raw_market_data_intraday table"""
    print("🗄️ CREATING MISSING MARKET DATA TABLES")
    print("=" * 50)
    
    try:
        db.initialize()
        print("✅ Database connection initialized")
        
        with db.get_session() as session:
            # Create raw_market_data_intraday table
            print("📊 Creating raw_market_data_intraday table...")
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS raw_market_data_intraday (
                    id SERIAL PRIMARY KEY,
                    stock_symbol VARCHAR(10) NOT NULL,
                    ts TIMESTAMP WITH TIME ZONE NOT NULL,
                    interval VARCHAR(10) NOT NULL,
                    open NUMERIC(12, 4),
                    high NUMERIC(12, 4),
                    low NUMERIC(12, 4),
                    close NUMERIC(12, 4),
                    volume BIGINT,
                    source VARCHAR(50) DEFAULT 'fmp',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_symbol, ts, interval, source)
                )
            """))
            
            # Create indexes for performance
            print("🔍 Creating indexes...")
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_intraday_symbol_ts 
                ON raw_market_data_intraday(stock_symbol, ts DESC)
            """))
            
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_intraday_symbol_interval 
                ON raw_market_data_intraday(stock_symbol, interval)
            """))
            
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_intraday_ts 
                ON raw_market_data_intraday(ts DESC)
            """))
            
            session.commit()
            print("✅ raw_market_data_intraday table created successfully")
            
            # Verify table exists
            print("🔍 Verifying table creation...")
            result = session.execute(text("""
                SELECT COUNT(*) as count FROM raw_market_data_intraday
            """))
            count = result.fetchone()[0]
            print(f"✅ Table verified (current rows: {count})")
            
            return True
            
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        return False

def check_existing_tables():
    """Check what market data tables exist"""
    print("\n📋 CHECKING EXISTING TABLES")
    print("=" * 30)
    
    try:
        db.initialize()
        
        with db.get_session() as session:
            # Check for market data tables
            tables_to_check = [
                'raw_market_data_daily',
                'raw_market_data_weekly', 
                'raw_market_data_monthly',
                'raw_market_data_intraday',
                'indicators_daily',
                'fundamentals_snapshots'
            ]
            
            for table in tables_to_check:
                try:
                    result = session.execute(text(f"""
                        SELECT COUNT(*) as count FROM {table}
                    """))
                    count = result.fetchone()[0]
                    print(f"✅ {table}: {count} rows")
                except Exception as e:
                    if "does not exist" in str(e):
                        print(f"❌ {table}: Table does not exist")
                    else:
                        print(f"⚠️  {table}: Error - {str(e)[:50]}...")
            
    except Exception as e:
        print(f"❌ Error checking tables: {e}")

def main():
    """Main function to create missing tables"""
    
    # Check existing tables first
    check_existing_tables()
    
    # Create missing intraday table
    success = create_intraday_table()
    
    if success:
        print("\n🎉 SUCCESS!")
        print("✅ Missing market data tables created successfully")
        print("✅ Data loading should now work properly")
        print("\n📋 Next Steps:")
        print("1. Restart the data loading process")
        print("2. Try loading TQQQ, QQQ, and VIX data")
        print("3. Run the backtesting system")
    else:
        print("\n❌ FAILED!")
        print("❌ Could not create missing tables")
        print("🔧 Check the error messages above")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
