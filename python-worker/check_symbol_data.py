#!/usr/bin/env python3
"""
Check Available Data for Symbol Analysis
Comprehensive data source check for NVDA symbol analysis
"""
import sys
import os
from datetime import datetime, timedelta

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import db
from app.observability.logging import get_logger
from sqlalchemy import text

logger = get_logger("check_symbol_data")

def check_symbol_data(symbol: str = "NVDA"):
    """Check all available data sources for a symbol"""
    print(f"🔍 COMPREHENSIVE DATA CHECK FOR {symbol}")
    print("=" * 50)
    
    try:
        db.initialize()
        print("✅ Database initialized")
        
        with db.get_session() as session:
            print(f"\n📊 DATA SOURCES CHECK")
            print("=" * 30)
            
            # 1. Price Data (Alpha Vantage)
            print(f"\n💹 PRICE DATA (OHLCV)")
            print("-" * 25)
            
            # Daily price data
            daily_count = session.execute(text("""
                SELECT COUNT(*) FROM raw_market_data_daily 
                WHERE symbol = :symbol AND data_source = 'alphavantage'
            """), {"symbol": symbol}).scalar()
            
            if daily_count > 0:
                print(f"✅ Daily price data: {daily_count} records")
                
                # Get latest price and date range
                latest = session.execute(text("""
                    SELECT date, close, volume FROM raw_market_data_daily 
                    WHERE symbol = :symbol AND data_source = 'alphavantage'
                    ORDER BY date DESC LIMIT 1
                """), {"symbol": symbol}).fetchone()
                
                date_range = session.execute(text("""
                    SELECT MIN(date), MAX(date) FROM raw_market_data_daily 
                    WHERE symbol = :symbol AND data_source = 'alphavantage'
                """), {"symbol": symbol}).fetchone()
                
                if latest:
                    print(f"   Latest price: ${latest[1]:.2f} on {latest[0]} (Volume: {latest[2]:,})")
                if date_range and date_range[0]:
                    print(f"   Date range: {date_range[0]} to {date_range[1]}")
                
                # Recent price movement
                recent = session.execute(text("""
                    SELECT date, close, volume FROM raw_market_data_daily 
                    WHERE symbol = :symbol AND data_source = 'alphavantage'
                    ORDER BY date DESC LIMIT 5
                """), {"symbol": symbol}).fetchall()
                
                if recent:
                    print(f"   Recent prices:")
                    for i, row in enumerate(reversed(recent)):
                        print(f"      {row[0]}: ${row[1]:.2f}")
            else:
                print(f"❌ No daily price data found")
            
            # Weekly price data
            weekly_count = session.execute(text("""
                SELECT COUNT(*) FROM raw_market_data_weekly 
                WHERE symbol = :symbol AND data_source = 'alphavantage'
            """), {"symbol": symbol}).scalar()
            
            if weekly_count > 0:
                print(f"✅ Weekly price data: {weekly_count} records")
            else:
                print(f"❌ No weekly price data found")
            
            # 2. Fundamentals Data (Massive API)
            print(f"\n💼 FUNDAMENTALS DATA")
            print("-" * 20)
            
            # Company overview
            overview_count = session.execute(text("""
                SELECT COUNT(*) FROM fundamentals_summary 
                WHERE symbol = :symbol AND data_source = 'alphavantage'
            """), {"symbol": symbol}).scalar()
            
            if overview_count > 0:
                print(f"✅ Company overview: {overview_count} records")
                
                overview = session.execute(text("""
                    SELECT name, sector, industry, market_cap, pe_ratio, eps, beta 
                    FROM fundamentals_summary 
                    WHERE symbol = :symbol AND data_source = 'alphavantage'
                    LIMIT 1
                """), {"symbol": symbol}).fetchone()
                
                if overview:
                    print(f"   Company: {overview[0]}")
                    print(f"   Sector: {overview[1]}, Industry: {overview[2]}")
                    print(f"   Market Cap: ${overview[3]:,}" if overview[3] else "   Market Cap: N/A")
                    print(f"   P/E Ratio: {overview[4]}" if overview[4] else "   P/E Ratio: N/A")
                    print(f"   EPS: ${overview[5]:.2f}" if overview[5] else "   EPS: N/A")
                    print(f"   Beta: {overview[6]}" if overview[6] else "   Beta: N/A")
            else:
                print(f"❌ No company overview found")
            
            # Financial statements
            fundamentals_count = session.execute(text("""
                SELECT COUNT(*) FROM fundamentals 
                WHERE symbol = :symbol AND data_source = 'alphavantage'
            """), {"symbol": symbol}).scalar()
            
            if fundamentals_count > 0:
                print(f"✅ Financial statements: {fundamentals_count} records")
                
                # Breakdown by type
                types = session.execute(text("""
                    SELECT report_type, COUNT(*) FROM fundamentals 
                    WHERE symbol = :symbol AND data_source = 'alphavantage'
                    GROUP BY report_type
                """), {"symbol": symbol}).fetchall()
                
                for report_type, count in types:
                    print(f"   {report_type}: {count} records")
            else:
                print(f"❌ No financial statements found")
            
            # 3. Technical Indicators (Massive API)
            print(f"\n📈 TECHNICAL INDICATORS")
            print("-" * 22)
            
            indicators_count = session.execute(text("""
                SELECT COUNT(*) FROM indicators_daily 
                WHERE symbol = :symbol AND data_source = 'alphavantage'
            """), {"symbol": symbol}).scalar()
            
            if indicators_count > 0:
                print(f"✅ Technical indicators: {indicators_count} records")
                
                # Available indicators
                indicators = session.execute(text("""
                    SELECT DISTINCT indicator_name FROM indicators_daily 
                    WHERE symbol = :symbol AND data_source = 'alphavantage'
                    ORDER BY indicator_name
                """), {"symbol": symbol}).fetchall()
                
                print(f"   Available indicators:")
                for indicator in indicators:
                    print(f"      • {indicator[0]}")
                
                # Latest RSI if available
                latest_rsi = session.execute(text("""
                    SELECT indicator_value, date FROM indicators_daily 
                    WHERE symbol = :symbol AND indicator_name = 'RSI' AND data_source = 'alphavantage'
                    ORDER BY date DESC LIMIT 1
                """), {"symbol": symbol}).fetchone()
                
                if latest_rsi:
                    print(f"   Latest RSI: {latest_rsi[0]:.2f} on {latest_rsi[1]}")
            else:
                print(f"❌ No technical indicators found")
            
            # 4. Earnings Calendar
            print(f"\n📅 EARNINGS DATA")
            print("-" * 16)
            
            earnings_count = session.execute(text("""
                SELECT COUNT(*) FROM earnings_calendar 
                WHERE symbol = :symbol AND data_source = 'alphavantage'
            """), {"symbol": symbol}).scalar()
            
            if earnings_count > 0:
                print(f"✅ Earnings data: {earnings_count} records")
                
                upcoming = session.execute(text("""
                    SELECT company_name, report_date, estimated_eps, currency 
                    FROM earnings_calendar 
                    WHERE symbol = :symbol AND data_source = 'alphavantage'
                    AND report_date >= CURRENT_DATE
                    ORDER BY report_date ASC
                    LIMIT 3
                """), {"symbol": symbol}).fetchall()
                
                if upcoming:
                    print(f"   Upcoming earnings:")
                    for earning in upcoming:
                        print(f"      • {earning[0]} on {earning[1]}")
                        print(f"        EPS Estimate: {earning[2]} {earning[3]}")
                else:
                    print(f"   No upcoming earnings found")
            else:
                print(f"❌ No earnings data found")
            
            # 5. Signal Generation Capability Assessment
            print(f"\n🎯 SIGNAL GENERATION CAPABILITY")
            print("=" * 35)
            
            capabilities = []
            
            if daily_count >= 50:  # Need at least 50 days for moving averages
                capabilities.append("✅ Technical Analysis (MA, RSI, MACD)")
            
            if overview_count > 0:
                capabilities.append("✅ Fundamental Analysis (P/E, EPS, Beta)")
            
            if fundamentals_count >= 4:  # Multiple quarters of data
                capabilities.append("✅ Financial Trend Analysis")
            
            if earnings_count > 0:
                capabilities.append("✅ Earnings-Based Strategies")
            
            if weekly_count >= 52:  # 1 year of weekly data
                capabilities.append("✅ Long-term Trend Analysis")
            
            if capabilities:
                print(f"Available capabilities for {symbol}:")
                for capability in capabilities:
                    print(f"   {capability}")
            else:
                print(f"❌ Insufficient data for signal generation")
            
            # 6. Recommended Strategies
            print(f"\n📋 RECOMMENDED STRATEGIES")
            print("=" * 25)
            
            if daily_count >= 200 and overview_count > 0:
                print(f"🔥 COMPREHENSIVE STRATEGIES AVAILABLE:")
                print(f"   • Technical + Fundamental Analysis")
                print(f"   • Momentum Trading (RSI, MACD)")
                print(f"   • Value Investing (P/E, EPS trends)")
                print(f"   • Earnings Surprise Strategies")
            elif daily_count >= 50:
                print(f"⚡ TECHNICAL STRATEGIES AVAILABLE:")
                print(f"   • Moving Average Crossovers")
                print(f"   • RSI Overbought/Oversold")
                print(f"   • Price Breakout Patterns")
            elif overview_count > 0:
                print(f"💰 FUNDAMENTAL STRATEGIES AVAILABLE:")
                print(f"   • Value Screening (P/E ratios)")
                print(f"   • Sector Analysis")
            else:
                print(f"❌ LIMITED STRATEGIES - Need more data")
            
            return True
            
    except Exception as e:
        print(f"❌ Error checking symbol data: {e}")
        return False

def check_data_sources_status():
    """Check overall data sources status"""
    print(f"\n🌐 DATA SOURCES OVERVIEW")
    print("=" * 25)
    
    try:
        db.initialize()
        
        with db.get_session() as session:
            # Alpha Vantage data
            av_daily = session.execute(text("""
                SELECT COUNT(DISTINCT symbol) FROM raw_market_data_daily 
                WHERE data_source = 'alphavantage'
            """)).scalar()
            
            av_fundamentals = session.execute(text("""
                SELECT COUNT(DISTINCT symbol) FROM fundamentals_summary 
                WHERE data_source = 'alphavantage'
            """)).scalar()
            
            av_earnings = session.execute(text("""
                SELECT COUNT(*) FROM earnings_calendar 
                WHERE data_source = 'alphavantage'
            """)).scalar()
            
            print(f"📊 Alpha Vantage Data:")
            print(f"   Price data symbols: {av_daily}")
            print(f"   Fundamentals symbols: {av_fundamentals}")
            print(f"   Earnings records: {av_earnings}")
            
            # Massive API data (if available)
            try:
                massive_indicators = session.execute(text("""
                    SELECT COUNT(DISTINCT symbol) FROM indicators_daily 
                    WHERE data_source = 'massive'
                """)).scalar()
                
                print(f"📈 Massive API Data:")
                print(f"   Technical indicators symbols: {massive_indicators}")
            except:
                print(f"📈 Massive API Data: Not available")
            
    except Exception as e:
        print(f"❌ Error checking data sources: {e}")

def main():
    """Main function"""
    print("🚀 SYMBOL DATA COMPREHENSIVE CHECK")
    print("=" * 40)
    
    # Check NVDA data
    check_symbol_data("NVDA")
    
    # Check overall data sources
    check_data_sources_status()
    
    print(f"\n🎯 ANALYSIS COMPLETE!")
    print(f"✅ Data availability assessed")
    print(f"✅ Signal generation capability evaluated")
    print(f"✅ Strategy recommendations provided")

if __name__ == "__main__":
    main()
