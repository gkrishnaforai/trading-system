#!/usr/bin/env python3
"""
Load NVDA Data from All Sources
Loads price data, fundamentals, and indicators for NVDA
"""
import sys
import os
from datetime import datetime

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.data_sources.alphavantage_price_loader import AlphaVantagePriceLoader
from app.data_sources.alphavantage_fundamentals_loader import AlphaVantageFundamentalsLoader
from app.database import db
from app.observability.logging import get_logger
from app.config import settings
from sqlalchemy import text

logger = get_logger("load_nvda_data")

def load_nvda_price_data():
    """Load NVDA price data from Alpha Vantage"""
    print("💹 LOADING NVDA PRICE DATA")
    print("=" * 30)
    
    try:
        api_key = settings.alphavantage_api_key
        if not api_key:
            print("❌ Alpha Vantage API key not found")
            return False
        
        loader = AlphaVantagePriceLoader(api_key)
        
        print("📊 Loading NVDA price data (last 90 days)...")
        results = loader.load_price_data("NVDA", days=90)
        
        success_count = 0
        for result in results:
            status = "✅" if result.success else "❌"
            print(f"   {status} {result.table_name}: {result.records_loaded} records ({result.duration_seconds:.1f}s)")
            if result.success:
                success_count += 1
        
        print(f"✅ Price data loading: {success_count}/{len(results)} successful")
        return success_count > 0
        
    except Exception as e:
        print(f"❌ Error loading NVDA price data: {e}")
        return False

def load_nvda_fundamentals():
    """Load NVDA fundamentals from Alpha Vantage"""
    print("\n💼 LOADING NVDA FUNDAMENTALS")
    print("=" * 35)
    
    try:
        api_key = settings.alphavantage_api_key
        if not api_key:
            print("❌ Alpha Vantage API key not found")
            return False
        
        loader = AlphaVantageFundamentalsLoader(api_key)
        
        print("📊 Loading NVDA fundamentals...")
        results = loader.load_fundamentals_data("NVDA")
        
        success_count = 0
        for result in results:
            status = "✅" if result.success else "❌"
            print(f"   {status} {result.table_name}: {result.records_loaded} records ({result.duration_seconds:.1f}s)")
            if result.success:
                success_count += 1
        
        print(f"✅ Fundamentals loading: {success_count}/{len(results)} successful")
        return success_count > 0
        
    except Exception as e:
        print(f"❌ Error loading NVDA fundamentals: {e}")
        return False

def check_nvda_earnings():
    """Check if NVDA has earnings data"""
    print("\n📅 CHECKING NVDA EARNINGS")
    print("=" * 30)
    
    try:
        db.initialize()
        
        with db.get_session() as session:
            count = session.execute(text("""
                SELECT COUNT(*) FROM earnings_calendar 
                WHERE symbol = 'NVDA' AND data_source = 'alphavantage'
            """)).scalar()
            
            if count > 0:
                print(f"✅ Found {count} NVDA earnings records")
                
                # Show upcoming earnings
                upcoming = session.execute(text("""
                    SELECT company_name, report_date, estimated_eps, currency 
                    FROM earnings_calendar 
                    WHERE symbol = 'NVDA' AND data_source = 'alphavantage'
                    AND report_date >= CURRENT_DATE
                    ORDER BY report_date ASC
                    LIMIT 3
                """)).fetchall()
                
                if upcoming:
                    print("   Upcoming earnings:")
                    for earning in upcoming:
                        print(f"      • {earning[0]} on {earning[1]} (EPS: {earning[2]} {earning[3]})")
                else:
                    print("   No upcoming earnings found")
                
                return True
            else:
                print("❌ No NVDA earnings data found")
                return False
                
    except Exception as e:
        print(f"❌ Error checking NVDA earnings: {e}")
        return False

def verify_nvda_data():
    """Verify all NVDA data is loaded"""
    print("\n🔍 VERIFYING NVDA DATA")
    print("=" * 25)
    
    try:
        db.initialize()
        
        with db.get_session() as session:
            # Price data
            daily_count = session.execute(text("""
                SELECT COUNT(*) FROM raw_market_data_daily 
                WHERE symbol = 'NVDA' AND data_source = 'alphavantage'
            """)).scalar()
            
            weekly_count = session.execute(text("""
                SELECT COUNT(*) FROM raw_market_data_weekly 
                WHERE symbol = 'NVDA' AND data_source = 'alphavantage'
            """)).scalar()
            
            monthly_count = session.execute(text("""
                SELECT COUNT(*) FROM raw_market_data_monthly 
                WHERE symbol = 'NVDA' AND data_source = 'alphavantage'
            """)).scalar()
            
            print(f"💹 Price Data:")
            print(f"   Daily: {daily_count} records")
            print(f"   Weekly: {weekly_count} records")
            print(f"   Monthly: {monthly_count} records")
            
            # Fundamentals
            overview_count = session.execute(text("""
                SELECT COUNT(*) FROM fundamentals_summary 
                WHERE symbol = 'NVDA' AND data_source = 'alphavantage'
            """)).scalar()
            
            fundamentals_count = session.execute(text("""
                SELECT COUNT(*) FROM fundamentals 
                WHERE symbol = 'NVDA' AND data_source = 'alphavantage'
            """)).scalar()
            
            print(f"\n💼 Fundamentals:")
            print(f"   Company overview: {overview_count} records")
            print(f"   Financial statements: {fundamentals_count} records")
            
            # Latest price info
            if daily_count > 0:
                latest = session.execute(text("""
                    SELECT date, close, high, low, volume FROM raw_market_data_daily 
                    WHERE symbol = 'NVDA' AND data_source = 'alphavantage'
                    ORDER BY date DESC LIMIT 1
                """)).fetchone()
                
                if latest:
                    print(f"\n📊 Latest NVDA Data:")
                    print(f"   Date: {latest[0]}")
                    print(f"   Close: ${latest[1]:.2f}")
                    print(f"   High: ${latest[2]:.2f}")
                    print(f"   Low: ${latest[3]:.2f}")
                    print(f"   Volume: {latest[4]:,}")
            
            # Company overview
            if overview_count > 0:
                overview = session.execute(text("""
                    SELECT name, sector, industry, market_cap, pe_ratio, eps, beta 
                    FROM fundamentals_summary 
                    WHERE symbol = 'NVDA' AND data_source = 'alphavantage'
                    LIMIT 1
                """)).fetchone()
                
                if overview:
                    print(f"\n🏢 NVDA Company Info:")
                    print(f"   Name: {overview[0]}")
                    print(f"   Sector: {overview[1]}")
                    print(f"   Industry: {overview[2]}")
                    if overview[3]:
                        print(f"   Market Cap: ${overview[3]:,}")
                    if overview[4]:
                        print(f"   P/E Ratio: {overview[4]}")
                    if overview[5]:
                        print(f"   EPS: ${overview[5]:.2f}")
                    if overview[6]:
                        print(f"   Beta: {overview[6]}")
            
            return True
            
    except Exception as e:
        print(f"❌ Error verifying NVDA data: {e}")
        return False

def assess_signal_generation_capability():
    """Assess NVDA signal generation capabilities"""
    print("\n🎯 NVDA SIGNAL GENERATION CAPABILITY")
    print("=" * 40)
    
    try:
        db.initialize()
        
        with db.get_session() as session:
            daily_count = session.execute(text("""
                SELECT COUNT(*) FROM raw_market_data_daily 
                WHERE symbol = 'NVDA' AND data_source = 'alphavantage'
            """)).scalar()
            
            overview_count = session.execute(text("""
                SELECT COUNT(*) FROM fundamentals_summary 
                WHERE symbol = 'NVDA' AND data_source = 'alphavantage'
            """)).scalar()
            
            fundamentals_count = session.execute(text("""
                SELECT COUNT(*) FROM fundamentals 
                WHERE symbol = 'NVDA' AND data_source = 'alphavantage'
            """)).scalar()
            
            earnings_count = session.execute(text("""
                SELECT COUNT(*) FROM earnings_calendar 
                WHERE symbol = 'NVDA' AND data_source = 'alphavantage'
            """)).scalar()
            
            capabilities = []
            
            if daily_count >= 50:
                capabilities.append("✅ Technical Analysis (MA, RSI, MACD)")
            if daily_count >= 200:
                capabilities.append("✅ Advanced Technical Patterns")
            
            if overview_count > 0:
                capabilities.append("✅ Fundamental Analysis (P/E, EPS, Beta)")
            
            if fundamentals_count >= 4:
                capabilities.append("✅ Financial Trend Analysis")
            
            if earnings_count > 0:
                capabilities.append("✅ Earnings-Based Strategies")
            
            print(f"Available capabilities for NVDA:")
            for capability in capabilities:
                print(f"   {capability}")
            
            if len(capabilities) >= 3:
                print(f"\n🔥 NVDA is ready for comprehensive signal generation!")
                print(f"   • Technical + Fundamental Analysis")
                print(f"   • Momentum Trading Strategies") 
                print(f"   • Value Investing Analysis")
                print(f"   • Earnings Surprise Strategies")
            elif len(capabilities) >= 2:
                print(f"\n⚡ NVDA is ready for basic signal generation!")
            else:
                print(f"\n❌ NVDA needs more data for signal generation")
            
            return True
            
    except Exception as e:
        print(f"❌ Error assessing capabilities: {e}")
        return False

def main():
    """Main function"""
    print("🚀 NVDA COMPREHENSIVE DATA LOADER")
    print("=" * 40)
    print("Loading NVDA data from all sources")
    
    # Load price data
    price_success = load_nvda_price_data()
    
    # Add delay for rate limiting
    if price_success:
        print("\n⏳ Rate limit delay: waiting 15 seconds...")
        import time
        time.sleep(15)
    
    # Load fundamentals
    fundamentals_success = load_nvda_fundamentals()
    
    # Check earnings
    earnings_success = check_nvda_earnings()
    
    # Verify all data
    verify_nvda_data()
    
    # Assess capabilities
    assess_signal_generation_capability()
    
    # Final result
    success_count = sum([price_success, fundamentals_success, earnings_success])
    
    print(f"\n🎯 LOADING SUMMARY")
    print("=" * 20)
    print(f"Price Data: {'✅' if price_success else '❌'}")
    print(f"Fundamentals: {'✅' if fundamentals_success else '❌'}")
    print(f"Earnings: {'✅' if earnings_success else '❌'}")
    print(f"Overall: {success_count}/3 data sources loaded")
    
    if success_count >= 2:
        print(f"\n🎉 NVDA DATA LOADING COMPLETED!")
        print(f"✅ Ready for signal generation and screening")
    else:
        print(f"\n❌ NVDA DATA LOADING INCOMPLETE")
        print(f"   Some data sources failed to load")
    
    return success_count >= 2

if __name__ == "__main__":
    main()
