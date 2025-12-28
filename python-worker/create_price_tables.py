#!/usr/bin/env python3
"""
Create Alpha Vantage Price Data Tables
Creates the proper table structure for OHLCV data
"""
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import db
from sqlalchemy import text

def create_price_tables():
    """Create price data tables for Alpha Vantage"""
    print("🗄️ CREATING ALPHA VANTAGE PRICE TABLES")
    print("=" * 45)
    
    try:
        db.initialize()
        print("✅ Database connection initialized")
        
        with db.get_session() as session:
            # Drop existing tables if they exist (clean start)
            print("🗑️  Cleaning up existing tables...")
            session.execute(text("DROP TABLE IF EXISTS raw_market_data_daily CASCADE"))
            session.execute(text("DROP TABLE IF EXISTS raw_market_data_weekly CASCADE"))
            session.execute(text("DROP TABLE IF EXISTS raw_market_data_monthly CASCADE"))
            session.commit()
            print("✅ Existing tables dropped")
            
            # Create raw_market_data_daily table
            print("📊 Creating raw_market_data_daily table...")
            session.execute(text("""
                CREATE TABLE raw_market_data_daily (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    date DATE NOT NULL,
                    open NUMERIC(12, 4),
                    high NUMERIC(12, 4),
                    low NUMERIC(12, 4),
                    close NUMERIC(12, 4),
                    volume BIGINT,
                    adjusted_close NUMERIC(12, 4),
                    data_source VARCHAR(50) DEFAULT 'alphavantage',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date, data_source)
                )
            """))
            
            # Create indexes
            session.execute(text("CREATE INDEX idx_raw_market_daily_symbol ON raw_market_data_daily(symbol)"))
            session.execute(text("CREATE INDEX idx_raw_market_daily_date ON raw_market_data_daily(date)"))
            session.execute(text("CREATE INDEX idx_raw_market_daily_symbol_date ON raw_market_data_daily(symbol, date)"))
            
            # Create raw_market_data_weekly table
            print("📊 Creating raw_market_data_weekly table...")
            session.execute(text("""
                CREATE TABLE raw_market_data_weekly (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    date DATE NOT NULL,
                    open NUMERIC(12, 4),
                    high NUMERIC(12, 4),
                    low NUMERIC(12, 4),
                    close NUMERIC(12, 4),
                    volume BIGINT,
                    adjusted_close NUMERIC(12, 4),
                    data_source VARCHAR(50) DEFAULT 'alphavantage',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date, data_source)
                )
            """))
            
            # Create indexes for weekly
            session.execute(text("CREATE INDEX idx_raw_market_weekly_symbol ON raw_market_data_weekly(symbol)"))
            session.execute(text("CREATE INDEX idx_raw_market_weekly_date ON raw_market_data_weekly(date)"))
            session.execute(text("CREATE INDEX idx_raw_market_weekly_symbol_date ON raw_market_data_weekly(symbol, date)"))
            
            # Create raw_market_data_monthly table
            print("📊 Creating raw_market_data_monthly table...")
            session.execute(text("""
                CREATE TABLE raw_market_data_monthly (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    date DATE NOT NULL,
                    open NUMERIC(12, 4),
                    high NUMERIC(12, 4),
                    low NUMERIC(12, 4),
                    close NUMERIC(12, 4),
                    volume BIGINT,
                    adjusted_close NUMERIC(12, 4),
                    data_source VARCHAR(50) DEFAULT 'alphavantage',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date, data_source)
                )
            """))
            
            # Create indexes for monthly
            session.execute(text("CREATE INDEX idx_raw_market_monthly_symbol ON raw_market_data_monthly(symbol)"))
            session.execute(text("CREATE INDEX idx_raw_market_monthly_date ON raw_market_data_monthly(date)"))
            session.execute(text("CREATE INDEX idx_raw_market_monthly_symbol_date ON raw_market_data_monthly(symbol, date)"))
            
            session.commit()
            print("✅ All price tables created successfully")
            
            # Add comments
            session.execute(text("COMMENT ON TABLE raw_market_data_daily IS 'Daily OHLCV price data from Alpha Vantage'"))
            session.execute(text("COMMENT ON TABLE raw_market_data_weekly IS 'Weekly OHLCV price data from Alpha Vantage'"))
            session.execute(text("COMMENT ON TABLE raw_market_data_monthly IS 'Monthly OHLCV price data from Alpha Vantage'"))
            session.commit()
            
            # Verify tables were created
            print(f"\n🔍 VERIFYING TABLES:")
            tables_to_check = [
                'raw_market_data_daily',
                'raw_market_data_weekly',
                'raw_market_data_monthly'
            ]
            
            for table in tables_to_check:
                try:
                    result = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                    print(f"✅ {table}: {result} records (empty as expected)")
                except Exception as e:
                    print(f"❌ {table}: ERROR - {e}")
            
            # Show table structure
            print(f"\n📋 TABLE STRUCTURE:")
            result = session.execute(text("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'raw_market_data_daily' 
                ORDER BY ordinal_position
            """)).fetchall()
            
            print(f"raw_market_data_daily columns:")
            for row in result:
                print(f"   • {row[0]}: {row[1]} (nullable: {row[2]})")
        
        print(f"\n🎉 PRICE TABLES CREATION COMPLETED!")
        print(f"✅ All Alpha Vantage price tables ready")
        print(f"✅ Indexes created for performance")
        print(f"✅ Ready for OHLCV data loading")
        
        return True
        
    except Exception as e:
        print(f"❌ Table creation failed: {e}")
        return False

def main():
    """Main function"""
    print("🚀 ALPHA VANTAGE PRICE TABLES SETUP")
    print("=" * 40)
    
    success = create_price_tables()
    
    if success:
        print(f"\n🎯 SETUP RESULT: SUCCESS!")
        print(f"✅ Database tables ready for Alpha Vantage price data")
        print(f"✅ Can now test the price data loader")
        
        print(f"\n📋 NEXT STEPS:")
        print(f"   1. Run the Alpha Vantage price data loader test")
        print(f"   2. Load OHLCV data for your desired symbols")
        print(f"   3. Verify price data in the database")
        
    else:
        print(f"\n❌ SETUP FAILED")
        print(f"   Check database connection and permissions")
    
    return success

if __name__ == "__main__":
    main()
