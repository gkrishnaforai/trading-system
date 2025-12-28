#!/usr/bin/env python3
"""
Database Inspection Script
Check what data is loaded and readiness for signals/strategies
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from app.database import db
from app.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def inspect_database():
    """Comprehensive database inspection"""
    print("🔍 DATABASE INSPECTION - Data Readiness for Signals & Strategies")
    print("=" * 70)
    
    try:
        # Initialize database if needed
        if db.session_factory is None:
            db.initialize()
        
        with db.get_session() as session:
            print("\n📊 MARKET DATA TABLES")
            print("-" * 30)
            
            # Check market data tables
            tables_to_check = [
                ('raw_market_data_daily', 'Daily Price Data'),
                ('raw_market_data_intraday', 'Intraday Price Data'),
                ('indicators_daily', 'Daily Indicators'),
                ('fundamentals_snapshots', 'Fundamentals Snapshots'),
                ('industry_peers', 'Industry Peers'),
                ('data_ingestion_state', 'Data Ingestion State'),
            ]
            
            for table_name, description in tables_to_check:
                try:
                    result = session.execute(text(f"SELECT COUNT(*) as count FROM {table_name}"))
                    count = result.fetchone()[0]
                    print(f"✅ {table_name:<25} ({description}): {count:,} records")
                    
                    if count > 0:
                        # Get sample data
                        sample = session.execute(text(f"SELECT * FROM {table_name} LIMIT 1")).fetchone()
                        if sample:
                            cols = session.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position")).fetchall()
                            print(f"   Columns: {len(cols)} - {[col[0] for col in cols[:8]]}{'...' if len(cols) > 8 else ''}")
                            
                            # Get date range for data tables
                            if 'date' in [col[0] for col in cols]:
                                date_range = session.execute(text(f"SELECT MIN(date), MAX(date) FROM {table_name}")).fetchone()
                                if date_range[0]:
                                    print(f"   Date Range: {date_range[0]} to {date_range[1]}")
                            elif 'timestamp' in [col[0] for col in cols]:
                                ts_range = session.execute(text(f"SELECT MIN(timestamp), MAX(timestamp) FROM {table_name}")).fetchone()
                                if ts_range[0]:
                                    print(f"   Time Range: {ts_range[0]} to {ts_range[1]}")
                    
                except Exception as e:
                    print(f"❌ {table_name:<25} ({description}): ERROR - {str(e)[:50]}...")
            
            print("\n📈 MASSIVE FINANCIAL DATA TABLES")
            print("-" * 40)
            
            # Check Massive-specific tables
            massive_tables = [
                ('massive_balance_sheets', 'Balance Sheets'),
                ('massive_cash_flow_statements', 'Cash Flow Statements'),
                ('massive_income_statements', 'Income Statements'),
                ('massive_financial_ratios', 'Financial Ratios'),
                ('massive_short_interest', 'Short Interest'),
                ('massive_short_volume', 'Short Volume'),
                ('massive_technical_indicators', 'Technical Indicators'),
            ]
            
            for table_name, description in massive_tables:
                try:
                    result = session.execute(text(f"SELECT COUNT(*) as count FROM {table_name}"))
                    count = result.fetchone()[0]
                    print(f"✅ {table_name:<30} ({description}): {count:,} records")
                    
                    if count > 0:
                        # Get unique symbols
                        symbols = session.execute(text(f"SELECT COUNT(DISTINCT symbol) FROM {table_name}")).fetchone()[0]
                        print(f"   Symbols: {symbols:,}")
                        
                        # Get date range
                        if 'period_end' in [row[0] for row in session.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}'")).fetchall()]:
                            date_range = session.execute(text(f"SELECT MIN(period_end), MAX(period_end) FROM {table_name}")).fetchone()
                            if date_range[0]:
                                print(f"   Period Range: {date_range[0]} to {date_range[1]}")
                        elif 'timestamp' in [row[0] for row in session.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}'")).fetchall()]:
                            ts_range = session.execute(text(f"SELECT MIN(timestamp), MAX(timestamp) FROM {table_name}")).fetchone()
                            if ts_range[0]:
                                print(f"   Time Range: {ts_range[0]} to {ts_range[1]}")
                        
                        # Sample technical indicators
                        if table_name == 'massive_technical_indicators':
                            indicator_types = session.execute(text(f"SELECT DISTINCT indicator_type FROM {table_name}")).fetchall()
                            print(f"   Indicator Types: {[it[0] for it in indicator_types]}")
                    
                except Exception as e:
                    print(f"❌ {table_name:<30} ({description}): ERROR - {str(e)[:50]}...")
            
            print("\n🎯 SIGNALS & STRATEGIES READINESS ASSESSMENT")
            print("-" * 50)
            
            # Check readiness for different types of strategies
            readiness_score = 0
            max_score = 0
            
            # Initialize variables
            tech_count = 0
            fundamentals_count = 0
            sentiment_count = 0
            daily_count = 0
            
            # 1. Price Data Readiness
            try:
                daily_count = session.execute(text("SELECT COUNT(*) FROM raw_market_data_daily")).fetchone()[0]
                if daily_count > 0:
                    latest_data = session.execute(text("SELECT MAX(date) FROM raw_market_data_daily")).fetchone()[0]
                    days_old = (datetime.now().date() - latest_data).days if latest_data else 999
                    
                    if days_old <= 1:
                        print("✅ Daily Price Data: FRESH (≤1 day old)")
                        readiness_score += 25
                    elif days_old <= 7:
                        print("⚠️ Daily Price Data: RECENT (≤7 days old)")
                        readiness_score += 15
                    else:
                        print(f"❌ Daily Price Data: STALE ({days_old} days old)")
                        readiness_score += 5
                else:
                    print("❌ Daily Price Data: MISSING")
                max_score += 25
            except:
                print("❌ Daily Price Data: ERROR")
                max_score += 25
            
            # 2. Technical Indicators Readiness
            try:
                tech_count = session.execute(text("SELECT COUNT(*) FROM massive_technical_indicators")).fetchone()[0]
                if tech_count > 0:
                    indicator_types = session.execute(text("SELECT COUNT(DISTINCT indicator_type) FROM massive_technical_indicators")).fetchone()[0]
                    symbols = session.execute(text("SELECT COUNT(DISTINCT symbol) FROM massive_technical_indicators")).fetchone()[0]
                    
                    if indicator_types >= 4 and symbols >= 1:
                        print(f"✅ Technical Indicators: COMPLETE ({indicator_types} types, {symbols} symbols)")
                        readiness_score += 25
                    elif indicator_types >= 2:
                        print(f"⚠️ Technical Indicators: PARTIAL ({indicator_types} types, {symbols} symbols)")
                        readiness_score += 15
                    else:
                        print(f"❌ Technical Indicators: LIMITED ({indicator_types} types, {symbols} symbols)")
                        readiness_score += 5
                else:
                    print("❌ Technical Indicators: MISSING")
                max_score += 25
            except:
                print("❌ Technical Indicators: ERROR")
                max_score += 25
            
            # 3. Fundamentals Readiness
            try:
                fundamentals_count = sum([
                    session.execute(text("SELECT COUNT(*) FROM massive_balance_sheets")).fetchone()[0],
                    session.execute(text("SELECT COUNT(*) FROM massive_income_statements")).fetchone()[0],
                    session.execute(text("SELECT COUNT(*) FROM massive_cash_flow_statements")).fetchone()[0]
                ])
                
                if fundamentals_count > 0:
                    symbols = session.execute(text("SELECT COUNT(DISTINCT symbol) FROM massive_balance_sheets")).fetchone()[0]
                    if symbols >= 1:
                        print(f"✅ Fundamentals Data: AVAILABLE ({fundamentals_count:,} records, {symbols} symbols)")
                        readiness_score += 25
                    else:
                        print(f"⚠️ Fundamentals Data: LIMITED ({fundamentals_count:,} records)")
                        readiness_score += 10
                else:
                    print("❌ Fundamentals Data: MISSING")
                max_score += 25
            except:
                print("❌ Fundamentals Data: ERROR")
                max_score += 25
            
            # 4. Market Sentiment Readiness
            try:
                sentiment_count = sum([
                    session.execute(text("SELECT COUNT(*) FROM massive_short_interest")).fetchone()[0],
                    session.execute(text("SELECT COUNT(*) FROM massive_short_volume")).fetchone()[0]
                ])
                
                if sentiment_count > 0:
                    print(f"✅ Market Sentiment: AVAILABLE ({sentiment_count:,} records)")
                    readiness_score += 25
                else:
                    print("❌ Market Sentiment: MISSING")
                max_score += 25
            except:
                print("❌ Market Sentiment: ERROR")
                max_score += 25
            
            # Calculate overall readiness
            overall_score = (readiness_score / max_score * 100) if max_score > 0 else 0
            
            print(f"\n📊 OVERALL READINESS SCORE: {readiness_score}/{max_score} ({overall_score:.1f}%)")
            
            if overall_score >= 80:
                print("🎉 EXCELLENT: Ready for advanced strategies and signals!")
            elif overall_score >= 60:
                print("✅ GOOD: Ready for basic strategies and signals!")
            elif overall_score >= 40:
                print("⚠️ MODERATE: Partial readiness - some strategies may work!")
            else:
                print("❌ LIMITED: Not ready for production strategies!")
            
            print("\n🚀 RECOMMENDED NEXT STEPS:")
            if overall_score < 100:
                if readiness_score < max_score - 25:
                    print("   • Load more recent price data")
                if tech_count == 0:
                    print("   • Load technical indicators (RSI, MACD, EMA, SMA)")
                if fundamentals_count == 0:
                    print("   • Load fundamental data (balance sheets, income statements)")
                if sentiment_count == 0:
                    print("   • Load market sentiment data (short interest/volume)")
            
            print("\n📈 STRATEGY TYPES SUPPORTED:")
            if daily_count > 0 and tech_count > 0:
                print("   ✅ Technical Analysis Strategies (RSI, MACD, Moving Averages)")
            if fundamentals_count > 0:
                print("   ✅ Fundamental Analysis Strategies (Value, Growth)")
            if sentiment_count > 0:
                print("   ✅ Sentiment Analysis Strategies (Short Interest)")
            if daily_count > 0:
                print("   ✅ Price Action Strategies (Trend, Momentum)")
            
    except Exception as e:
        print(f"❌ Database inspection failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    inspect_database()
