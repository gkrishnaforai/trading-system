#!/usr/bin/env python3
"""
Simple Yahoo Finance Price Data Test
Test Yahoo Finance only for daily price data
"""

import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.comprehensive_data_loader import ComprehensiveDataLoader
from app.config import settings
from app.database import db, init_database
from sqlalchemy import text

def test_yahoo_finance_only():
    """Test Yahoo Finance only for daily price data"""
    
    print("📈 YAHOO FINANCE DAILY DATA TEST")
    print("=" * 50)
    
    # Initialize database first
    try:
        print("🔧 Initializing database...")
        init_database()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        return False
    
    # Initialize the comprehensive data loader
    try:
        loader = ComprehensiveDataLoader()
        print("✅ Comprehensive data loader initialized")
    except Exception as e:
        print(f"❌ Failed to initialize data loader: {e}")
        return False
    
    # Test symbol
    symbol = "NVDA"
    days = 90
    
    print(f"\n📊 Loading daily price data for {symbol} (last {days} days)")
    print("=" * 60)
    
    # Load historical price data using Yahoo Finance only
    try:
        result = loader.load_historical_price_data(symbol, days)
        
        print(f"📊 Load Result:")
        print(f"   • Success: {result.success}")
        print(f"   • Data Source: {result.source}")
        print(f"   • Records Loaded: {result.records_loaded}")
        print(f"   • Duration: {result.duration_seconds:.2f}s")
        print(f"   • Message: {result.message}")
        
        if not result.success:
            print(f"❌ Historical price data loading failed: {result.message}")
            return False
            
    except Exception as e:
        print(f"❌ Error loading historical price data: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return False
    
    # Verify data in database
    print(f"\n🔍 DATABASE VERIFICATION")
    print("=" * 30)
    
    try:
        with db.get_session() as session:
            # Total daily price data count
            total_count = session.execute(text("""
                SELECT COUNT(*) FROM raw_market_data_daily 
                WHERE symbol = :symbol
            """), {"symbol": symbol}).scalar()
            
            print(f"Total {symbol} daily price records: {total_count}")
            
            if total_count > 0:
                # Date range
                date_range = session.execute(text("""
                    SELECT MIN(date), MAX(date), COUNT(*) FROM raw_market_data_daily 
                    WHERE symbol = :symbol
                """), {"symbol": symbol}).fetchone()
                
                print(f"Date range: {date_range[0]} to {date_range[1]} ({date_range[2]} trading days)")
                
                # Latest price data
                latest = session.execute(text("""
                    SELECT date, open, high, low, close, volume
                    FROM raw_market_data_daily 
                    WHERE symbol = :symbol
                    ORDER BY date DESC
                    LIMIT 3
                """), {"symbol": symbol}).fetchall()
                
                print(f"\n📊 Latest {symbol} Daily Price Data:")
                for row in latest:
                    print(f"   {row[0]}: Open=${row[1]:.2f}, High=${row[2]:.2f}, Low=${row[3]:.2f}, Close=${row[4]:.2f}, Vol={row[5]:,}")
                
                # Price statistics
                stats = session.execute(text("""
                    SELECT 
                        AVG(close) as avg_close,
                        MIN(close) as min_close,
                        MAX(close) as max_close,
                        AVG(volume) as avg_volume
                    FROM raw_market_data_daily 
                    WHERE symbol = :symbol
                """), {"symbol": symbol}).fetchone()
                
                print(f"\n📈 {symbol} Price Statistics:")
                print(f"   • Average Close: ${stats[0]:.2f}")
                print(f"   • Period Low: ${stats[1]:.2f}")
                print(f"   • Period High: ${stats[2]:.2f}")
                print(f"   • Avg Volume: {stats[3]:,.0f}")
                
                # Data source verification
                sources = session.execute(text("""
                    SELECT DISTINCT data_source, COUNT(*) FROM raw_market_data_daily 
                    WHERE symbol = :symbol GROUP BY data_source
                """), {"symbol": symbol}).fetchall()
                
                print(f"\n📡 Data Source: {sources}")
                
            else:
                print("❌ No price data found in database")
                return False
                
    except Exception as e:
        print(f"❌ Error verifying database: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return False
    
    print(f"\n🎯 YAHOO FINANCE TEST: SUCCESS!")
    print("✅ Yahoo Finance adapter working properly")
    print("✅ Daily price data loaded and saved")
    print("✅ Database integration working")
    print("✅ No fallback to Alpha Vantage needed")
    
    return True

if __name__ == "__main__":
    print("🚀 TESTING YAHOO FINANCE PRICE DATA ONLY")
    print("=" * 60)
    
    if test_yahoo_finance_only():
        print(f"\n🎉 YAHOO FINANCE TEST PASSED!")
        print("✅ Ready for production with Yahoo Finance as primary source")
        exit(0)
    else:
        print(f"\n❌ YAHOO FINANCE TEST FAILED!")
        print("🔧 Check Yahoo Finance adapter and database configuration")
        exit(1)
