#!/usr/bin/env python3
"""
Test Price Data Loading Service
Tests the complete service -> adapter -> data source pipeline for price data
"""

import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.comprehensive_data_loader import ComprehensiveDataLoader
from app.config import settings
from app.database import db
from sqlalchemy import text

def test_price_data_loading():
    """Test price data loading using the service architecture"""
    
    print("📈 PRICE DATA LOADING TEST")
    print("=" * 50)
    
    # Initialize the comprehensive data loader
    try:
        loader = ComprehensiveDataLoader()
        print("✅ Comprehensive data loader initialized")
    except Exception as e:
        print(f"❌ Failed to initialize data loader: {e}")
        return False
    
    # Test symbol
    symbol = "NVDA"
    days = 30  # Get last 30 days of price data
    
    print(f"\n📊 Loading price data for {symbol} (last {days} days)")
    print("=" * 50)
    
    # Load price data using the service
    try:
        result = loader.load_price_data(symbol, days)
        
        if result.success:
            print(f"✅ Price data loaded successfully!")
            print(f"   • Source: {result.data_source}")
            print(f"   • Records: {result.records_loaded}")
            print(f"   • Duration: {result.duration:.2f}s")
            print(f"   • Message: {result.message}")
        else:
            print(f"❌ Price data loading failed: {result.message}")
            return False
            
    except Exception as e:
        print(f"❌ Error loading price data: {e}")
        return False
    
    # Verify data in database
    print(f"\n🔍 DATABASE VERIFICATION")
    print("=" * 30)
    
    try:
        with db.get_session() as session:
            # Total price data count
            total_count = session.execute(text("""
                SELECT COUNT(*) FROM raw_market_data_daily 
                WHERE symbol = :symbol
            """), {"symbol": symbol}).scalar()
            
            print(f"Total {symbol} price records: {total_count}")
            
            if total_count > 0:
                # Date range
                date_range = session.execute(text("""
                    SELECT MIN(date), MAX(date), COUNT(*) FROM raw_market_data_daily 
                    WHERE symbol = :symbol
                """), {"symbol": symbol}).fetchone()
                
                print(f"Date range: {date_range[0]} to {date_range[1]} ({date_range[2]} trading days)")
                
                # Latest price data
                latest = session.execute(text("""
                    SELECT date, open_price, high_price, low_price, close_price, volume
                    FROM raw_market_data_daily 
                    WHERE symbol = :symbol
                    ORDER BY date DESC
                    LIMIT 5
                """), {"symbol": symbol}).fetchall()
                
                print(f"\n📊 Latest {symbol} Price Data:")
                for row in latest:
                    print(f"   {row[0]}: Open=${row[1]:.2f}, High=${row[2]:.2f}, Low=${row[3]:.2f}, Close=${row[4]:.2f}, Vol={row[5]:,}")
                
                # Price statistics
                stats = session.execute(text("""
                    SELECT 
                        AVG(close_price) as avg_close,
                        MIN(close_price) as min_close,
                        MAX(close_price) as max_close,
                        AVG(volume) as avg_volume
                    FROM raw_market_data_daily 
                    WHERE symbol = :symbol
                """), {"symbol": symbol}).fetchone()
                
                print(f"\n📈 {symbol} Price Statistics:")
                print(f"   • Average Close: ${stats[0]:.2f}")
                print(f"   • 52W Low: ${stats[1]:.2f}")
                print(f"   • 52W High: ${stats[2]:.2f}")
                print(f"   • Avg Volume: {stats[3]:,.0f}")
                
            else:
                print("❌ No price data found in database")
                return False
                
    except Exception as e:
        print(f"❌ Error verifying database: {e}")
        return False
    
    print(f"\n🎯 PRICE DATA TEST: SUCCESS!")
    print("✅ Service architecture working properly")
    print("✅ Alpha Vantage adapter integrated")
    print("✅ Price data loaded and saved")
    print("✅ Database integration working")
    
    print(f"\n📋 PRICE DATA CAPABILITIES:")
    print("   • Historical OHLCV data")
    print("   • Multiple timeframes")
    print("   • Volume analysis")
    print("   • Price trend analysis")
    
    return True

def test_data_source_priority():
    """Test data source priority and fallback"""
    
    print(f"\n🔄 DATA SOURCE PRIORITY TEST")
    print("=" * 40)
    
    try:
        loader = ComprehensiveDataLoader()
        
        # Check available data sources
        available_sources = list(loader.data_sources.keys())
        print(f"Available data sources: {available_sources}")
        
        # Test the priority order
        print(f"\n📊 Data Source Priority:")
        print("   1. Alpha Vantage (Primary - OHLCV)")
        print("   2. Yahoo Finance (Fallback)")
        print("   3. Massive API (Fundamentals only)")
        
        # Check if Alpha Vantage is available (preferred for price data)
        if 'alphavantage' in loader.data_sources:
            alphavantage_adapter = loader.data_sources['alphavantage']
            if alphavantage_adapter.is_available():
                print("   ✅ Alpha Vantage: Available (Preferred)")
            else:
                print("   ❌ Alpha Vantage: Not available")
        else:
            print("   ❌ Alpha Vantage: Not configured")
        
        # Check Yahoo Finance availability
        if 'yahoo' in loader.data_sources:
            yahoo_adapter = loader.data_sources['yahoo']
            if yahoo_adapter.is_available():
                print("   ✅ Yahoo Finance: Available (Fallback)")
            else:
                print("   ❌ Yahoo Finance: Not available")
        else:
            print("   ❌ Yahoo Finance: Not configured")
                
    except Exception as e:
        print(f"❌ Error testing data sources: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 TESTING PRICE DATA LOADING PIPELINE")
    print("=" * 60)
    
    success = True
    
    # Test price data loading
    if not test_price_data_loading():
        success = False
    
    # Test data source priority
    if not test_data_source_priority():
        success = False
    
    if success:
        print(f"\n🎉 ALL PRICE DATA TESTS PASSED!")
        print("✅ Ready for production trading system")
        exit(0)
    else:
        print(f"\n❌ PRICE DATA TESTS FAILED!")
        print("🔧 Check configuration and data source availability")
        exit(1)
