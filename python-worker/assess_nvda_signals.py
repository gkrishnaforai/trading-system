#!/usr/bin/env python3
"""
Assess NVDA Signal Generation Capabilities
Comprehensive analysis of available data for NVDA trading signals
"""
import sys
import os
from datetime import datetime

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import db
from app.observability.logging import get_logger
from sqlalchemy import text

logger = get_logger("assess_nvda_signals")

def assess_nvda_signal_capabilities():
    """Assess what signals we can generate for NVDA"""
    print("🎯 NVDA SIGNAL GENERATION ASSESSMENT")
    print("=" * 45)
    
    try:
        db.initialize()
        
        with db.get_session() as session:
            symbol = "NVDA"
            
            # 1. Check available data
            print(f"\n📊 AVAILABLE DATA FOR {symbol}")
            print("=" * 35)
            
            # Company overview (Massive)
            overview = session.execute(text("""
                SELECT name, sector, industry, market_cap, pe_ratio, eps, beta,
                       revenue_ttm, profit_margin, roe, debt_to_equity
                FROM fundamentals_summary 
                WHERE symbol = :symbol AND data_source = 'massive'
                LIMIT 1
            """), {"symbol": symbol}).fetchone()
            
            if overview:
                print(f"✅ Company Overview (Massive API):")
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
                if overview[7]:
                    print(f"   Revenue TTM: ${overview[7]:,}")
                if overview[8]:
                    print(f"   Profit Margin: {overview[8]:.2%}")
                if overview[9]:
                    print(f"   ROE: {overview[9]:.2%}")
                if overview[10]:
                    print(f"   Debt/Equity: {overview[10]}")
            else:
                print(f"❌ No company overview data")
            
            # Price data (Alpha Vantage)
            daily_count = session.execute(text("""
                SELECT COUNT(*) FROM raw_market_data_daily 
                WHERE symbol = :symbol AND data_source = 'alphavantage'
            """), {"symbol": symbol}).scalar()
            
            if daily_count > 0:
                latest_price = session.execute(text("""
                    SELECT date, close, high, low, volume FROM raw_market_data_daily 
                    WHERE symbol = :symbol AND data_source = 'alphavantage'
                    ORDER BY date DESC LIMIT 1
                """), {"symbol": symbol}).fetchone()
                
                print(f"\n✅ Price Data (Alpha Vantage):")
                print(f"   Daily records: {daily_count}")
                if latest_price:
                    print(f"   Latest price: ${latest_price[1]:.2f} on {latest_price[0]}")
                    print(f"   Day range: ${latest_price[3]:.2f} - ${latest_price[2]:.2f}")
                    print(f"   Volume: {latest_price[4]:,}")
            else:
                print(f"\n❌ No price data available")
            
            # Earnings data
            earnings = session.execute(text("""
                SELECT company_name, report_date, estimated_eps, currency 
                FROM earnings_calendar 
                WHERE symbol = :symbol AND data_source = 'alphavantage'
                AND report_date >= CURRENT_DATE
                ORDER BY report_date ASC
                LIMIT 1
            """), {"symbol": symbol}).fetchone()
            
            if earnings:
                print(f"\n✅ Earnings Data:")
                print(f"   Next earnings: {earnings[0]} on {earnings[1]}")
                if earnings[2]:
                    print(f"   EPS estimate: {earnings[2]} {earnings[3]}")
            else:
                print(f"\n❌ No upcoming earnings data")
            
            # 2. Assess signal generation capabilities
            print(f"\n🎯 SIGNAL GENERATION CAPABILITIES")
            print("=" * 40)
            
            capabilities = []
            strategies = []
            
            # Fundamental Analysis
            if overview:
                capabilities.append("✅ Fundamental Analysis")
                strategies.append("• Value Investing (P/E, P/B ratios)")
                strategies.append("• Growth Analysis (Revenue, EPS trends)")
                strategies.append("• Quality Metrics (ROE, Profit Margin)")
                strategies.append("• Risk Assessment (Beta, Debt/Equity)")
            
            # Technical Analysis
            if daily_count >= 50:
                capabilities.append("✅ Technical Analysis")
                strategies.append("• Moving Average Crossovers")
                strategies.append("• Price Momentum Indicators")
                strategies.append("• Volume Analysis")
            
            if daily_count >= 200:
                strategies.append("• Long-term Trend Analysis")
                strategies.append("• Volatility Patterns")
            
            # Earnings Strategies
            if earnings:
                capabilities.append("✅ Earnings-Based Strategies")
                strategies.append("• Earnings Surprise Plays")
                strategies.append("• Pre/Post Earnings Momentum")
                strategies.append("• EPS Trend Analysis")
            
            # Display capabilities
            for capability in capabilities:
                print(f"   {capability}")
            
            # 3. Recommended Strategies
            print(f"\n📋 RECOMMENDED TRADING STRATEGIES FOR NVDA")
            print("=" * 50)
            
            if strategies:
                for strategy in strategies:
                    print(f"   {strategy}")
            else:
                print("   ❌ Insufficient data for strategy recommendations")
            
            # 4. Data Quality Score
            print(f"\n📊 DATA QUALITY SCORE")
            print("=" * 25)
            
            score = 0
            max_score = 100
            
            # Fundamentals: 40 points
            if overview:
                score += 40
                print(f"   Fundamentals: 40/40 ✅")
            else:
                print(f"   Fundamentals: 0/40 ❌")
            
            # Price Data: 30 points
            if daily_count >= 200:
                score += 30
                print(f"   Price Data: 30/30 ✅ (200+ days)")
            elif daily_count >= 50:
                score += 20
                print(f"   Price Data: 20/30 ⚡ (50-199 days)")
            elif daily_count > 0:
                score += 10
                print(f"   Price Data: 10/30 ⚠️ (<50 days)")
            else:
                print(f"   Price Data: 0/30 ❌")
            
            # Earnings: 20 points
            if earnings:
                score += 20
                print(f"   Earnings Data: 20/20 ✅")
            else:
                print(f"   Earnings Data: 0/20 ❌")
            
            # Technical Indicators: 10 points
            indicators_count = session.execute(text("""
                SELECT COUNT(*) FROM indicators_daily 
                WHERE symbol = :symbol AND data_source = 'massive'
            """), {"symbol": symbol}).scalar()
            
            if indicators_count > 0:
                score += 10
                print(f"   Technical Indicators: 10/10 ✅")
            else:
                print(f"   Technical Indicators: 0/10 ❌")
            
            percentage = (score / max_score) * 100
            print(f"\n🎯 OVERALL SCORE: {score}/{max_score} ({percentage:.1f}%)")
            
            # 5. Recommendations
            print(f"\n💡 RECOMMENDATIONS")
            print("=" * 20)
            
            if percentage >= 80:
                print(f"🔥 EXCELLENT: NVDA is ready for comprehensive signal generation!")
                print(f"   • Implement multi-factor trading models")
                print(f"   • Combine fundamental and technical analysis")
                print(f"   • Use earnings calendar for timing strategies")
            elif percentage >= 60:
                print(f"⚡ GOOD: NVDA has solid data for basic signal generation!")
                print(f"   • Focus on available data types")
                print(f"   • Consider loading missing data sources")
                print(f"   • Start with fundamental-based strategies")
            elif percentage >= 40:
                print(f"⚠️  LIMITED: NVDA has minimal data for signal generation!")
                print(f"   • Load price data from Alpha Vantage")
                print(f"   • Add technical indicators from Massive")
                print(f"   • Focus on company overview analysis")
            else:
                print(f"❌ INSUFFICIENT: NVDA needs more data for signal generation!")
                print(f"   • Load all missing data sources")
                print(f"   • Verify API connections")
                print(f"   • Start with basic data collection")
            
            return True
            
    except Exception as e:
        print(f"❌ Error assessing NVDA signals: {e}")
        return False

def main():
    """Main function"""
    print("🚀 NVDA COMPREHENSIVE SIGNAL ASSESSMENT")
    print("=" * 45)
    print("Evaluating data availability for trading signal generation")
    
    success = assess_nvda_signal_capabilities()
    
    if success:
        print(f"\n🎯 ASSESSMENT COMPLETED!")
        print(f"✅ NVDA signal generation capability evaluated")
        print(f"✅ Trading strategies recommended")
        print(f"✅ Data quality score calculated")
        
        print(f"\n📋 NEXT STEPS:")
        print(f"   1. Load missing data sources (price data, technical indicators)")
        print(f"   2. Implement signal generation algorithms")
        print(f"   3. Set up automated screening and alerts")
        print(f"   4. Backtest strategies with historical data")
        
    else:
        print(f"\n❌ ASSESSMENT FAILED")
        print(f"   Check database connection and data availability")
    
    return success

if __name__ == "__main__":
    main()
