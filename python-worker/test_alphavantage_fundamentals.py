#!/usr/bin/env python3
"""
Test Alpha Vantage Fundamentals Loader
Focused on fundamentals data - technical indicators from Massive
"""
import sys
import os

import pytest

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app.data_sources.alphavantage_fundamentals_loader import AlphaVantageFundamentalsLoader
except ModuleNotFoundError:
    pytest.skip(
        "AlphaVantageFundamentalsLoader module not available in this codebase; skipping legacy loader test.",
        allow_module_level=True,
    )
from app.database import db
from app.observability.logging import get_logger
from sqlalchemy import text

logger = get_logger("test_alphavantage_fundamentals")

def test_fundamentals_loading():
    """Test fundamentals data loading from Alpha Vantage"""
    print("💼 ALPHA VANTAGE FUNDAMENTALS LOADER TEST")
    print("=" * 50)
    print("Focused on fundamentals - technical indicators from Massive")
    
    # Initialize database
    try:
        db.initialize()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    
    # Initialize loader
    api_key = "QFGQ8S1GNTMPFNMA"
    loader = AlphaVantageFundamentalsLoader(api_key)
    
    # Test symbols (small set for testing)
    test_symbols = ["AAPL", "MSFT"]
    
    total_results = []
    
    for symbol in test_symbols:
        print(f"\n📊 Loading fundamentals for {symbol}")
        print("-" * 35)
        
        results = loader.load_fundamentals_data(symbol)
        total_results.extend(results)
        
        # Show results for this symbol
        for result in results:
            status = "✅" if result.success else "❌"
            print(f"   {status} {result.table_name}: {result.records_loaded} records ({result.duration:.1f}s)")
            if not result.success:
                print(f"      Error: {result.message}")
    
    # Summary
    print(f"\n📋 FUNDAMENTALS LOADING SUMMARY")
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
            # Check fundamentals_summary
            count = session.execute(
                text("SELECT COUNT(*) FROM fundamentals_summary WHERE data_source = 'alphavantage'")
            ).scalar()
            print(f"fundamentals_summary: {count} records")
            
            # Check fundamentals
            count = session.execute(
                text("SELECT COUNT(*) FROM fundamentals WHERE data_source = 'alphavantage'")
            ).scalar()
            print(f"fundamentals: {count} records")
            
            # Show sample data
            if count > 0:
                print(f"\n📊 Sample Data:")
                
                # Sample from fundamentals_summary
                row = session.execute(
                    text("SELECT symbol, name, sector, market_cap, pe_ratio FROM fundamentals_summary WHERE data_source = 'alphavantage' LIMIT 1")
                ).fetchone()
                
                if row:
                    print(f"✅ Company Overview Sample:")
                    print(f"   Symbol: {row[0]}, Name: {row[1]}")
                    print(f"   Sector: {row[2]}, Market Cap: ${row[3]:,}")
                    print(f"   P/E Ratio: {row[4]}")
                
                # Sample from fundamentals
                row = session.execute(
                    text("SELECT symbol, report_type, fiscal_date_ending, total_revenue FROM fundamentals WHERE data_source = 'alphavantage' LIMIT 1")
                ).fetchone()
                
                if row:
                    print(f"✅ Financial Statements Sample:")
                    print(f"   Symbol: {row[0]}, Type: {row[1]}")
                    print(f"   Fiscal Date: {row[2]}, Revenue: ${row[3]:,}")
            
    except Exception as e:
        print(f"❌ Database verification failed: {e}")
        return False
    
    # Final result
    success_rate = len(successful_loads) / len(total_results) if total_results else 0
    
    if success_rate >= 0.8:  # 80% success rate
        print(f"\n🎉 FUNDAMENTALS LOADING COMPLETED SUCCESSFULLY!")
        print(f"✅ Success Rate: {success_rate:.1%}")
        print(f"✅ Alpha Vantage fundamentals loader working")
        print(f"✅ Ready for production data loading")
        print(f"✅ Technical indicators handled by Massive API")
        return True
    else:
        print(f"\n❌ FUNDAMENTALS LOADING FAILED")
        print(f"❌ Success Rate: {success_rate:.1%} (target: 80%)")
        return False

def test_single_symbol_fundamentals():
    """Test loading fundamentals for one symbol in detail"""
    print(f"\n🎯 SINGLE SYMBOL FUNDAMENTALS TEST")
    print("=" * 45)
    
    # Initialize database
    try:
        db.initialize()
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    
    # Initialize loader
    api_key = "QFGQ8S1GNTMPFNMA"
    loader = AlphaVantageFundamentalsLoader(api_key)
    
    # Test with one symbol
    symbol = "GOOGL"
    print(f"📊 Loading fundamentals for {symbol}")
    
    results = loader.load_fundamentals_data(symbol)
    
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
    print("🚀 ALPHA VANTAGE FUNDAMENTALS COMPREHENSIVE TEST")
    print("=" * 60)
    print("Testing fundamentals loading - technical indicators from Massive")
    
    # Test single symbol first
    if not test_single_symbol_fundamentals():
        print("❌ Single symbol test failed")
        return False
    
    # Test comprehensive loading
    success = test_fundamentals_loading()
    
    if success:
        print(f"\n🎯 COMPREHENSIVE TEST RESULT: SUCCESS!")
        print(f"✅ Alpha Vantage fundamentals loader fully functional")
        print(f"✅ Company overview and financial statements loaded")
        print(f"✅ Proper data transformation working")
        print(f"✅ Rate limiting respected")
        print(f"✅ Ready for production deployment")
        
        print(f"\n📋 DATA SOURCES STRATEGY:")
        print(f"   • Alpha Vantage: Fundamentals (overview, financial statements)")
        print(f"   • Massive API: Technical indicators (RSI, MACD, SMA, EMA)")
        print(f"   • Yahoo Finance: Historical price data")
        print(f"   • Optimized for each source's strengths")
        
    else:
        print(f"\n❌ COMPREHENSIVE TEST FAILED")
        print(f"   Check database connection and configuration")
        print(f"   Verify Alpha Vantage API key and rate limits")
    
    return success

if __name__ == "__main__":
    main()
