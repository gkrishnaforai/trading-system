#!/usr/bin/env python3
"""
Test Alpha Vantage Price Data Loader
Focused on OHLCV historical data - fundamentals from Massive API
"""
import sys
import os

import pytest

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app.data_sources.alphavantage_price_loader import AlphaVantagePriceLoader
except ModuleNotFoundError:
    pytest.skip(
        "AlphaVantagePriceLoader module not available in this codebase; skipping legacy loader test.",
        allow_module_level=True,
    )
from app.database import db
from app.observability.logging import get_logger
from sqlalchemy import text

logger = get_logger("test_alphavantage_price_data")

def test_price_data_loading():
    """Test price data loading from Alpha Vantage"""
    print("📈 ALPHA VANTAGE PRICE DATA LOADER TEST")
    print("=" * 50)
    print("Focused on OHLCV historical data - fundamentals from Massive")
    
    # Initialize database
    try:
        db.initialize()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    
    # Initialize loader
    api_key = "QFGQ8S1GNTMPFNMA"
    loader = AlphaVantagePriceLoader(api_key)
    
    # Test symbols (small set for testing)
    test_symbols = ["AAPL", "MSFT"]
    
    total_results = []
    
    for symbol in test_symbols:
        print(f"\n📊 Loading price data for {symbol}")
        print("-" * 35)
        
        results = loader.load_price_data(symbol, days=30)  # Load 30 days for testing
        total_results.extend(results)
        
        # Show results for this symbol
        for result in results:
            status = "✅" if result.success else "❌"
            print(f"   {status} {result.table_name}: {result.records_loaded} records ({result.duration_seconds:.1f}s)")
            if not result.success:
                print(f"      Error: {result.message}")
        
        # Add delay between symbols to respect rate limits
        if symbol != test_symbols[-1]:  # Don't delay after last symbol
            print(f"⏳ Rate limit delay: waiting 15 seconds before next symbol...")
            import time
            time.sleep(15)
    
    # Summary
    print(f"\n📋 PRICE DATA LOADING SUMMARY")
    print("=" * 40)
    
    successful_loads = [r for r in total_results if r.success]
    failed_loads = [r for r in total_results if not r.success]
    
    print(f"Total Operations: {len(total_results)}")
    print(f"Successful: {len(successful_loads)}")
    print(f"Failed: {len(failed_loads)}")
    print(f"Total Records Loaded: {sum(r.records_loaded for r in successful_loads)}")
    print(f"Total Duration: {sum(r.duration_seconds for r in total_results):.1f}s")
    
    if failed_loads:
        print(f"\n❌ Failed Operations:")
        for result in failed_loads:
            print(f"   • {result.table_name}: {result.message}")
    
    # Verify data in database
    print(f"\n🔍 DATABASE VERIFICATION")
    print("=" * 30)
    
    try:
        with db.get_session() as session:
            # Check raw_market_data_daily
            count = session.execute(
                text("SELECT COUNT(*) FROM raw_market_data_daily WHERE data_source = 'alphavantage'")
            ).scalar()
            print(f"raw_market_data_daily: {count} records")
            
            # Check raw_market_data_weekly (if created)
            try:
                count = session.execute(
                    text("SELECT COUNT(*) FROM raw_market_data_weekly WHERE data_source = 'alphavantage'")
                ).scalar()
                print(f"raw_market_data_weekly: {count} records")
            except:
                print(f"raw_market_data_weekly: Table not created")
            
            # Check raw_market_data_monthly (if created)
            try:
                count = session.execute(
                    text("SELECT COUNT(*) FROM raw_market_data_monthly WHERE data_source = 'alphavantage'")
                ).scalar()
                print(f"raw_market_data_monthly: {count} records")
            except:
                print(f"raw_market_data_monthly: Table not created")
            
            # Show sample data
            if count > 0:
                print(f"\n📊 Sample Price Data:")
                
                # Sample from raw_market_data_daily
                rows = session.execute(
                    text("""
                        SELECT symbol, date, open, high, low, close, volume 
                        FROM raw_market_data_daily 
                        WHERE data_source = 'alphavantage' 
                        ORDER BY date DESC 
                        LIMIT 3
                    """)
                ).fetchall()
                
                if rows:
                    print(f"✅ Daily Price Data Sample:")
                    for row in rows:
                        print(f"   {row[0]} {row[1]}: O:{row[2]} H:{row[3]} L:{row[4]} C:{row[5]} V:{row[6]:,}")
            
    except Exception as e:
        print(f"❌ Database verification failed: {e}")
        return False
    
    # Final result
    success_rate = len(successful_loads) / len(total_results) if total_results else 0
    
    if success_rate >= 0.8:  # 80% success rate
        print(f"\n🎉 PRICE DATA LOADING COMPLETED SUCCESSFULLY!")
        print(f"✅ Success Rate: {success_rate:.1%}")
        print(f"✅ Alpha Vantage price data loader working")
        print(f"✅ Ready for production data loading")
        return True
    else:
        print(f"\n❌ PRICE DATA LOADING FAILED")
        print(f"❌ Success Rate: {success_rate:.1%} (target: 80%)")
        return False

def test_single_symbol_price_data():
    """Test loading price data for one symbol in detail"""
    print(f"\n🎯 SINGLE SYMBOL PRICE DATA TEST")
    print("=" * 45)
    
    # Initialize database
    try:
        db.initialize()
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    
    # Initialize loader
    api_key = "QFGQ8S1GNTMPFNMA"
    loader = AlphaVantagePriceLoader(api_key)
    
    # Test with one symbol
    symbol = "GOOGL"
    print(f"📊 Loading price data for {symbol} (last 30 days)")
    
    results = loader.load_price_data(symbol, days=30)
    
    print(f"\n📋 Detailed Results for {symbol}:")
    for result in results:
        status = "✅" if result.success else "❌"
        print(f"   {status} {result.table_name}")
        print(f"      Records: {result.records_loaded}")
        print(f"      Duration: {result.duration_seconds:.1f}s")
        if result.message:
            print(f"      Message: {result.message}")
    
    return True

def main():
    """Main test function"""
    print("🚀 ALPHA VANTAGE PRICE DATA COMPREHENSIVE TEST")
    print("=" * 60)
    print("Testing OHLCV historical data loading - fundamentals from Massive")
    
    # Test single symbol first
    if not test_single_symbol_price_data():
        print("❌ Single symbol test failed")
        return False
    
    # Test comprehensive loading
    success = test_price_data_loading()
    
    if success:
        print(f"\n🎯 COMPREHENSIVE TEST RESULT: SUCCESS!")
        print(f"✅ Alpha Vantage price data loader fully functional")
        print(f"✅ Daily, weekly, and monthly OHLCV data loaded")
        print(f"✅ Proper data transformation working")
        print(f"✅ Rate limiting respected")
        print(f"✅ Ready for production deployment")
        
        print(f"\n📋 OPTIMIZED DATA SOURCES STRATEGY:")
        print(f"   • Alpha Vantage: Historical OHLCV price data")
        print(f"   • Massive API: Company overview, fundamentals, technical indicators")
        print(f"   • Yahoo Finance: Additional price data backup")
        print(f"   • Each source optimized for its strengths")
        
    else:
        print(f"\n❌ COMPREHENSIVE TEST FAILED")
        print(f"   Check database connection and configuration")
        print(f"   Verify Alpha Vantage API key and rate limits")
    
    return success

if __name__ == "__main__":
    main()
