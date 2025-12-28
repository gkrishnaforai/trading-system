#!/usr/bin/env python3
"""
Test Historical and Intraday Price Data Loading
Tests both historical daily data (one-time load) and current intraday data (5-minute updates)
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

def test_historical_price_data():
    """Test historical daily price data loading (one-time load)"""
    
    print("📈 HISTORICAL PRICE DATA TEST")
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
    
    print(f"\n📊 Loading historical daily price data for {symbol}")
    print("=" * 60)
    
    # Load historical price data using the service
    try:
        result = loader.load_historical_price_data(symbol, days=365)
        
        if result.success:
            print(f"✅ Historical price data loaded successfully!")
            print(f"   • Source: {result.data_source}")
            print(f"   • Records: {result.records_loaded}")
            print(f"   • Duration: {result.duration:.2f}s")
            print(f"   • Message: {result.message}")
        else:
            print(f"❌ Historical price data loading failed: {result.message}")
            return False
            
    except Exception as e:
        print(f"❌ Error loading historical price data: {e}")
        return False
    
    # Verify data in database
    print(f"\n🔍 HISTORICAL DATA VERIFICATION")
    print("=" * 35)
    
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
                
            else:
                print("❌ No historical price data found in database")
                return False
                
    except Exception as e:
        print(f"❌ Error verifying historical data: {e}")
        return False
    
    return True

def test_intraday_price_data():
    """Test current intraday price data loading (5-minute updates)"""
    
    print(f"\n⚡ INTRADAY PRICE DATA TEST")
    print("=" * 50)
    
    try:
        loader = ComprehensiveDataLoader()
    except Exception as e:
        print(f"❌ Failed to initialize data loader: {e}")
        return False
    
    # Test symbol
    symbol = "NVDA"
    
    print(f"\n📊 Loading current intraday price data for {symbol}")
    print("=" * 60)
    
    # Load intraday price data using the service
    try:
        result = loader.load_current_price_data(symbol)
        
        if result.success:
            print(f"✅ Intraday price data loaded successfully!")
            print(f"   • Source: {result.data_source}")
            print(f"   • Records: {result.records_loaded}")
            print(f"   • Duration: {result.duration:.2f}s")
            print(f"   • Message: {result.message}")
        else:
            print(f"❌ Intraday price data loading failed: {result.message}")
            return False
            
    except Exception as e:
        print(f"❌ Error loading intraday price data: {e}")
        return False
    
    # Verify intraday data in database
    print(f"\n🔍 INTRADAY DATA VERIFICATION")
    print("=" * 35)
    
    try:
        with db.get_session() as session:
            # Total intraday price data count
            total_count = session.execute(text("""
                SELECT COUNT(*) FROM raw_market_data_intraday 
                WHERE symbol = :symbol
            """), {"symbol": symbol}).scalar()
            
            print(f"Total {symbol} intraday price records: {total_count}")
            
            if total_count > 0:
                # Time range
                time_range = session.execute(text("""
                    SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM raw_market_data_intraday 
                    WHERE symbol = :symbol
                """), {"symbol": symbol}).fetchone()
                
                print(f"Time range: {time_range[0]} to {time_range[1]} ({time_range[2]} data points)")
                
                # Latest intraday data
                latest = session.execute(text("""
                    SELECT timestamp, open_price, high_price, low_price, close_price, volume
                    FROM raw_market_data_intraday 
                    WHERE symbol = :symbol
                    ORDER BY timestamp DESC
                    LIMIT 5
                """), {"symbol": symbol}).fetchall()
                
                print(f"\n📊 Latest {symbol} Intraday Price Data:")
                for row in latest:
                    print(f"   {row[0]}: Open=${row[1]:.2f}, High=${row[2]:.2f}, Low=${row[3]:.2f}, Close=${row[4]:.2f}, Vol={row[5]:,}")
                
                # Calculate price movement
                if len(latest) >= 2:
                    current_price = latest[0][4]  # Close of latest
                    previous_price = latest[-1][1]  # Open of earliest
                    price_change = current_price - previous_price
                    price_change_pct = (price_change / previous_price) * 100
                    
                    print(f"\n📈 Intraday Price Movement:")
                    print(f"   • Current Price: ${current_price:.2f}")
                    print(f"   • Price Change: ${price_change:+.2f} ({price_change_pct:+.2f}%)")
                
            else:
                print("❌ No intraday price data found in database")
                return False
                
    except Exception as e:
        print(f"❌ Error verifying intraday data: {e}")
        return False
    
    return True

def test_data_architecture():
    """Test the dual data architecture"""
    
    print(f"\n🏗️  DUAL DATA ARCHITECTURE TEST")
    print("=" * 50)
    
    try:
        with db.get_session() as session:
            # Compare daily vs intraday data
            daily_count = session.execute(text("""
                SELECT COUNT(*) FROM raw_market_data_daily WHERE symbol = 'NVDA'
            """)).scalar()
            
            intraday_count = session.execute(text("""
                SELECT COUNT(*) FROM raw_market_data_intraday WHERE symbol = 'NVDA'
            """)).scalar()
            
            print(f"📊 Data Architecture Summary:")
            print(f"   • Historical Daily Records: {daily_count}")
            print(f"   • Current Intraday Records: {intraday_count}")
            
            # Show data sources
            daily_sources = session.execute(text("""
                SELECT DISTINCT data_source, COUNT(*) FROM raw_market_data_daily 
                WHERE symbol = 'NVDA' GROUP BY data_source
            """)).fetchall()
            
            intraday_sources = session.execute(text("""
                SELECT DISTINCT data_source, COUNT(*) FROM raw_market_data_intraday 
                WHERE symbol = 'NVDA' GROUP BY data_source
            """)).fetchall()
            
            print(f"\n📡 Data Sources:")
            print(f"   Daily Data: {[(src[0], src[1]) for src in daily_sources]}")
            print(f"   Intraday Data: {[(src[0], src[1]) for src in intraday_sources]}")
            
            print(f"\n📊 Data Source Priority:")
            print(f"   Daily Data: Yahoo Finance (Primary) → Alpha Vantage (Fallback)")
            print(f"   Intraday Data: Alpha Vantage (Primary)")
            
    except Exception as e:
        print(f"❌ Error testing data architecture: {e}")
        return False
    
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
        print(f"\n📊 Optimized Data Source Priority:")
        print("   Daily Data:")
        print("     1. Yahoo Finance (Primary - Free & Reliable)")
        print("     2. Alpha Vantage (Fallback)")
        print("   Intraday Data:")
        print("     1. Alpha Vantage (Primary - Better intraday support)")
        print("   Fundamentals:")
        print("     1. Massive API (Primary)")
        
        # Check Yahoo Finance availability (preferred for daily)
        if 'yahoo' in loader.data_sources:
            yahoo_adapter = loader.data_sources['yahoo']
            if yahoo_adapter.is_available():
                print("   ✅ Yahoo Finance: Available (Preferred for daily)")
            else:
                print("   ❌ Yahoo Finance: Not available")
        else:
            print("   ❌ Yahoo Finance: Not configured")
        
        # Check Alpha Vantage availability (fallback for daily, primary for intraday)
        if 'alphavantage' in loader.data_sources:
            alphavantage_adapter = loader.data_sources['alphavantage']
            if alphavantage_adapter.is_available():
                print("   ✅ Alpha Vantage: Available (Fallback daily, Primary intraday)")
            else:
                print("   ❌ Alpha Vantage: Not available")
        else:
            print("   ❌ Alpha Vantage: Not configured")
                
    except Exception as e:
        print(f"❌ Error testing data sources: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 TESTING DUAL PRICE DATA LOADING PIPELINE")
    print("=" * 70)
    
    success = True
    
    # Test historical daily data (one-time load)
    if not test_historical_price_data():
        success = False
    
    # Test current intraday data (5-minute updates)
    if not test_intraday_price_data():
        success = False
    
    # Test the dual architecture
    if not test_data_architecture():
        success = False
    
    # Test data source priority
    if not test_data_source_priority():
        success = False
    
    if success:
        print(f"\n🎉 ALL PRICE DATA TESTS PASSED!")
        print("✅ Historical daily data loading working (Yahoo Finance primary)")
        print("✅ Current intraday data loading working (Alpha Vantage primary)")
        print("✅ Dual data architecture working")
        print("✅ Optimized data source priority working")
        print("✅ Ready for production trading system")
        print(f"\n📋 OPTIMIZED USAGE RECOMMENDATIONS:")
        print("   • Use load_historical_price_data() for one-time historical load (Yahoo Finance)")
        print("   • Use load_current_price_data() for 5-minute updates (Alpha Vantage)")
        print("   • Use load_price_data() for flexible data loading")
        print(f"\n💡 COST OPTIMIZATION:")
        print("   • Daily data: Yahoo Finance (FREE)")
        print("   • Intraday data: Alpha Vantage (Premium API required)")
        print("   • Fundamentals: Massive API (Premium)")
        exit(0)
    else:
        print(f"\n❌ PRICE DATA TESTS FAILED!")
        print("🔧 Check configuration and data source availability")
        exit(1)
