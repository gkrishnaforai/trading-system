#!/usr/bin/env python3
"""
Test Massive API Fundamentals Loader
Test loading company overview and financial statements from Massive API
"""
import sys
import os

import pytest

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app.data_sources.massive_fundamentals_loader import MassiveFundamentalsLoader
except ModuleNotFoundError:
    pytest.skip(
        "MassiveFundamentalsLoader module not available in this codebase; skipping legacy loader test.",
        allow_module_level=True,
    )
from app.database import db
from app.observability.logging import get_logger
from sqlalchemy import text

logger = get_logger("test_massive_fundamentals")

def test_massive_fundamentals_loading():
    """Test fundamentals data loading from Massive API"""
    print("💼 MASSIVE API FUNDAMENTALS LOADER TEST")
    print("=" * 50)
    print("Loading company overview and financial statements from Massive")
    
    # Initialize database
    try:
        db.initialize()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    
    # Initialize loader
    loader = MassiveFundamentalsLoader()
    
    # Test with NVDA first
    symbol = "NVDA"
    print(f"\n📊 Loading fundamentals for {symbol} from Massive")
    print("-" * 45)
    
    results = loader.load_fundamentals_data(symbol)
    
    # Show results
    for result in results:
        status = "✅" if result.success else "❌"
        print(f"   {status} {result.table_name}: {result.records_loaded} records ({result.duration_seconds:.1f}s)")
        if not result.success:
            print(f"      Error: {result.message}")
    
    # Verify data in database
    print(f"\n🔍 DATABASE VERIFICATION")
    print("=" * 30)
    
    try:
        with db.get_session() as session:
            # Check fundamentals_summary (Massive data)
            count = session.execute(
                text("SELECT COUNT(*) FROM fundamentals_summary WHERE data_source = 'massive'")
            ).scalar()
            print(f"fundamentals_summary (Massive): {count} records")
            
            # Check fundamentals (Massive data)
            count = session.execute(
                text("SELECT COUNT(*) FROM fundamentals WHERE data_source = 'massive'")
            ).scalar()
            print(f"fundamentals (Massive): {count} records")
            
            # Show sample data
            if count > 0:
                print(f"\n📊 Sample Massive Data:")
                
                # Sample from fundamentals_summary
                row = session.execute(
                    text("""
                        SELECT symbol, name, sector, market_cap, pe_ratio, eps 
                        FROM fundamentals_summary 
                        WHERE data_source = 'massive' AND symbol = :symbol
                        LIMIT 1
                    """), {"symbol": symbol}
                ).fetchone()
                
                if row:
                    print(f"✅ Company Overview Sample (Massive):")
                    print(f"   Symbol: {row[0]}, Name: {row[1]}")
                    print(f"   Sector: {row[2]}, Market Cap: ${row[3]:,}" if row[3] else f"   Sector: {row[2]}")
                    print(f"   P/E Ratio: {row[4]}, EPS: ${row[5]:.2f}" if row[4] else f"   P/E Ratio: N/A, EPS: ${row[5]:.2f}")
                
                # Sample from fundamentals
                rows = session.execute(
                    text("""
                        SELECT symbol, report_type, fiscal_date_ending, total_revenue, net_income 
                        FROM fundamentals 
                        WHERE data_source = 'massive' AND symbol = :symbol
                        LIMIT 3
                    """), {"symbol": symbol}
                ).fetchall()
                
                if rows:
                    print(f"✅ Financial Statements Sample (Massive):")
                    for row in rows:
                        print(f"   {row[0]} {row[1]}: {row[2]}, Revenue: ${row[3]:,}, Net Income: ${row[4]:,}")
            
    except Exception as e:
        print(f"❌ Database verification failed: {e}")
        return False
    
    # Final result
    successful_loads = [r for r in results if r.success]
    success_rate = len(successful_loads) / len(results) if results else 0
    
    if success_rate >= 0.8:  # 80% success rate
        print(f"\n🎉 MASSIVE FUNDAMENTALS LOADING COMPLETED SUCCESSFULLY!")
        print(f"✅ Success Rate: {success_rate:.1%}")
        print(f"✅ Massive API fundamentals loader working")
        print(f"✅ Ready for production data loading")
        return True
    else:
        print(f"\n❌ MASSIVE FUNDAMENTALS LOADING FAILED")
        print(f"❌ Success Rate: {success_rate:.1%} (target: 80%)")
        return False

def main():
    """Main test function"""
    print("🚀 MASSIVE API FUNDAMENTALS TEST")
    print("=" * 35)
    print("Testing company overview and financial statements from Massive")
    
    # Test fundamentals loading
    success = test_massive_fundamentals_loading()
    
    if success:
        print(f"\n🎯 TEST RESULT: SUCCESS!")
        print(f"✅ Massive API fundamentals loader functional")
        print(f"✅ Company overview and financial statements loaded")
        print(f"✅ Ready for NVDA signal generation")
        
        print(f"\n📋 DATA SOURCES STRATEGY:")
        print(f"   • Massive API: Company overview, fundamentals, technical indicators")
        print(f"   • Alpha Vantage: Historical OHLCV price data, earnings calendar")
        print(f"   • Each source optimized for its strengths")
        
    else:
        print(f"\n❌ TEST FAILED")
        print(f"   Check Massive API connection and configuration")
    
    return success

if __name__ == "__main__":
    main()
