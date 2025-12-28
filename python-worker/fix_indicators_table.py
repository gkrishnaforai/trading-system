#!/usr/bin/env python3
"""
Fix indicators_daily table structure
"""
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import db
from sqlalchemy import text

def fix_indicators_table():
    """Fix indicators_daily table structure"""
    print("🔧 FIXING INDICATORS_DAILY TABLE")
    print("=" * 35)
    
    try:
        db.initialize()
        print("✅ Database initialized")
        
        with db.get_session() as session:
            # Drop existing table
            print("🗑️  Dropping existing indicators_daily table...")
            session.execute(text("DROP TABLE IF EXISTS indicators_daily CASCADE"))
            session.commit()
            print("✅ Existing table dropped")
            
            # Create proper table structure
            print("📊 Creating proper indicators_daily table...")
            session.execute(text("""
                CREATE TABLE indicators_daily (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    date DATE NOT NULL,
                    indicator_name VARCHAR(50) NOT NULL,
                    indicator_value NUMERIC(12, 6),
                    time_period INTEGER,
                    data_source VARCHAR(50) DEFAULT 'alphavantage',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date, indicator_name, data_source)
                )
            """))
            
            # Create indexes
            session.execute(text("CREATE INDEX idx_indicators_daily_symbol ON indicators_daily(symbol)"))
            session.execute(text("CREATE INDEX idx_indicators_daily_date ON indicators_daily(date)"))
            session.execute(text("CREATE INDEX idx_indicators_daily_name ON indicators_daily(indicator_name)"))
            session.execute(text("CREATE INDEX idx_indicators_daily_symbol_date_name ON indicators_daily(symbol, date, indicator_name)"))
            
            # Add comment
            session.execute(text("COMMENT ON TABLE indicators_daily IS 'Technical indicators (RSI, MACD, SMA, EMA, etc.)'"))
            
            session.commit()
            print("✅ indicators_daily table created with proper structure")
            
            # Verify table structure
            result = session.execute(text("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'indicators_daily' 
                ORDER BY ordinal_position
            """)).fetchall()
            
            print(f"\n📋 Table structure:")
            for row in result:
                print(f"   • {row[0]}: {row[1]} (nullable: {row[2]})")
        
        print(f"\n🎉 INDICATORS TABLE FIXED!")
        print(f"✅ Ready for technical indicators data")
        
        return True
        
    except Exception as e:
        print(f"❌ Error fixing indicators table: {e}")
        return False

def main():
    """Main function"""
    print("🚀 INDICATORS TABLE FIX")
    print("=" * 25)
    
    success = fix_indicators_table()
    
    if success:
        print(f"\n🎯 FIX COMPLETED!")
        print(f"✅ indicators_daily table structure corrected")
        print(f"✅ Ready to load technical indicators")
        
    else:
        print(f"\n❌ FIX FAILED")
        print(f"   Check database permissions")
    
    return success

if __name__ == "__main__":
    main()
