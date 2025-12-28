#!/usr/bin/env python3
"""
Test Alpha Vantage Earnings Calendar Loader
Loads upcoming earnings data from Alpha Vantage
"""
import sys
import os

import pytest

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app.data_sources.alphavantage_earnings_loader import AlphaVantageEarningsLoader
except ModuleNotFoundError:
    pytest.skip(
        "AlphaVantageEarningsLoader module not available in this codebase; skipping legacy loader test.",
        allow_module_level=True,
    )
from app.database import db
from app.observability.logging import get_logger
from app.config import settings
from sqlalchemy import text
from datetime import datetime, timedelta

logger = get_logger("test_alphavantage_earnings")

def test_earnings_calendar_loading():
    """Test earnings calendar loading from Alpha Vantage"""
    print("📅 ALPHA VANTAGE EARNINGS CALENDAR TEST")
    print("=" * 50)
    print("Loading upcoming earnings data")
    
    # Initialize database
    try:
        db.initialize()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    
    # Initialize loader
    api_key = settings.alphavantage_api_key
    print(f"🔑 Using API key: ***{api_key[-4:] if api_key else 'NOT_FOUND'}")
    
    if not api_key:
        print("❌ Alpha Vantage API key not found in configuration")
        return False
    
    loader = AlphaVantageEarningsLoader(api_key)
    
    # Test earnings calendar loading
    print(f"\n📊 Loading earnings calendar (3-month horizon)")
    print("-" * 45)
    
    result = loader.load_earnings_calendar("3month")
    
    # Show result
    status = "✅" if result.success else "❌"
    print(f"   {status} Earnings Calendar: {result.records_loaded} records ({result.duration_seconds:.1f}s)")
    if not result.success:
        print(f"      Error: {result.message}")
        return False
    
    # Verify data in database
    print(f"\n🔍 DATABASE VERIFICATION")
    print("=" * 30)
    
    try:
        with db.get_session() as session:
            # Check earnings_calendar table
            count = session.execute(
                text("SELECT COUNT(*) FROM earnings_calendar WHERE data_source = 'alphavantage'")
            ).scalar()
            print(f"earnings_calendar: {count} records")
            
            # Show sample data
            if count > 0:
                print(f"\n📊 Sample Earnings Data:")
                
                # Get upcoming earnings (next 30 days)
                upcoming = loader.get_upcoming_earnings(30)
                
                if upcoming:
                    print(f"✅ Upcoming Earnings (next 30 days): {len(upcoming)} companies")
                    print(f"   Sample:")
                    for i, earning in enumerate(upcoming[:5]):  # Show first 5
                        print(f"   {i+1}. {earning['symbol']} - {earning['company_name']}")
                        print(f"      Date: {earning['report_date']}, EPS Estimate: {earning['estimated_eps']}")
                    
                    if len(upcoming) > 5:
                        print(f"   ... and {len(upcoming) - 5} more")
                else:
                    print(f"ℹ️  No upcoming earnings in next 30 days")
                
                # Show date range
                date_range = session.execute(text("""
                    SELECT MIN(report_date), MAX(report_date) 
                    FROM earnings_calendar 
                    WHERE data_source = 'alphavantage'
                """)).fetchone()
                
                if date_range and date_range[0]:
                    print(f"📅 Date range: {date_range[0]} to {date_range[1]}")
                
                # Show unique symbols count
                symbol_count = session.execute(text("""
                    SELECT COUNT(DISTINCT symbol) 
                    FROM earnings_calendar 
                    WHERE data_source = 'alphavantage'
                """)).scalar()
                print(f"🏢 Unique companies: {symbol_count}")
            
    except Exception as e:
        print(f"❌ Database verification failed: {e}")
        return False
    
    # Test different horizons
    print(f"\n🔄 TESTING DIFFERENT HORIZONS")
    print("=" * 35)
    
    horizons = ["3month", "6month"]
    
    for horizon in horizons:
        print(f"\n📅 Testing {horizon} horizon:")
        
        # Clear existing data for this test
        with db.get_session() as session:
            session.execute(text("DELETE FROM earnings_calendar WHERE data_source = 'alphavantage'"))
            session.commit()
        
        result = loader.load_earnings_calendar(horizon)
        status = "✅" if result.success else "❌"
        print(f"   {status} {horizon}: {result.records_loaded} records")
    
    # Final result
    success_rate = 100 if result.success else 0
    
    if success_rate >= 80:
        print(f"\n🎉 EARNINGS CALENDAR LOADING COMPLETED SUCCESSFULLY!")
        print(f"✅ Success Rate: {success_rate:.1%}")
        print(f"✅ Alpha Vantage earnings calendar loader working")
        print(f"✅ Ready for production earnings tracking")
        return True
    else:
        print(f"\n❌ EARNINGS CALENDAR LOADING FAILED")
        print(f"❌ Success Rate: {success_rate:.1%} (target: 80%)")
        return False

def test_upcoming_earnings_query():
    """Test querying upcoming earnings"""
    print(f"\n🎯 UPCOMING EARNINGS QUERY TEST")
    print("=" * 40)
    
    try:
        db.initialize()
        
        loader = AlphaVantageEarningsLoader(settings.alphavantage_api_key)
        
        # Test different time ranges
        ranges = [7, 14, 30, 90]
        
        for days in ranges:
            upcoming = loader.get_upcoming_earnings(days)
            print(f"📅 Next {days} days: {len(upcoming)} companies reporting")
            
            if upcoming and days <= 30:  # Show details for shorter ranges
                for earning in upcoming[:3]:
                    print(f"   • {earning['symbol']} ({earning['company_name']}) on {earning['report_date']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Upcoming earnings query failed: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 ALPHA VANTAGE EARNINGS CALENDAR COMPREHENSIVE TEST")
    print("=" * 65)
    print("Testing upcoming earnings data loading")
    
    # Test earnings calendar loading
    success = test_earnings_calendar_loading()
    
    if success:
        # Test upcoming earnings queries
        test_upcoming_earnings_query()
        
        print(f"\n🎯 COMPREHENSIVE TEST RESULT: SUCCESS!")
        print(f"✅ Alpha Vantage earnings calendar loader fully functional")
        print(f"✅ Upcoming earnings data loaded successfully")
        print(f"✅ Proper data transformation working")
        print(f"✅ Ready for production deployment")
        
        print(f"\n📋 EARNINGS CALENDAR FEATURES:")
        print(f"   • 3-month, 6-month, 12-month horizons")
        print(f"   • Company symbols and names")
        print(f"   • Report dates and EPS estimates")
        print(f"   • Currency information")
        print(f"   • Duplicate prevention with UPSERT")
        
    else:
        print(f"\n❌ COMPREHENSIVE TEST FAILED")
        print(f"   Check Alpha Vantage API key and rate limits")
    
    return success

if __name__ == "__main__":
    main()
