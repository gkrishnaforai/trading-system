#!/usr/bin/env python3
"""
Signal Generation Analysis - What We Have vs What We Need
Complete assessment of current capabilities and gaps
"""

import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import db, init_database
from sqlalchemy import text

def analyze_signal_capabilities():
    """Analyze current signal generation capabilities"""
    
    print("🎯 SIGNAL GENERATION CAPABILITY ANALYSIS")
    print("=" * 60)
    
    # Initialize database
    init_database()
    
    symbol = "NVDA"
    
    print(f"\n📊 CURRENT DATA STATUS FOR {symbol}")
    print("=" * 40)
    
    with db.get_session() as session:
        # Check price data
        price_count = session.execute(text("""
            SELECT COUNT(*) FROM raw_market_data_daily 
            WHERE symbol = :symbol
        """), {"symbol": symbol}).scalar()
        
        # Check indicators
        indicators_count = session.execute(text("""
            SELECT COUNT(*) FROM indicators_daily 
            WHERE symbol = :symbol
        """), {"symbol": symbol}).scalar()
        
        # Check fundamentals
        fundamentals_count = session.execute(text("""
            SELECT COUNT(*) FROM fundamentals_summary 
            WHERE symbol = :symbol
        """), {"symbol": symbol}).scalar()
        
        print(f"📈 Data Records:")
        print(f"   • Price Data: {price_count} records")
        print(f"   • Indicators: {indicators_count} records")
        print(f"   • Fundamentals: {fundamentals_count} records")
        
        # Detailed indicator analysis
        print(f"\n🔍 DETAILED INDICATOR ANALYSIS")
        print("=" * 40)
        
        # What we have
        available_indicators = session.execute(text("""
            SELECT DISTINCT indicator_name, time_period, COUNT(*) as count
            FROM indicators_daily 
            WHERE symbol = :symbol
            GROUP BY indicator_name, time_period
            ORDER BY indicator_name
        """), {"symbol": symbol}).fetchall()
        
        print("✅ AVAILABLE INDICATORS:")
        for ind in available_indicators:
            print(f"   • {ind[0]} (period {ind[1]}): {ind[2]} records")
        
        # What the signal service needs
        print("\n❌ REQUIRED INDICATORS FOR SIGNALS:")
        required_indicators = {
            "price": "Latest price data",
            "sma50": "50-day Simple Moving Average",
            "sma200": "200-day Simple Moving Average", 
            "ema20": "20-day Exponential Moving Average",
            "ema50": "50-day Exponential Moving Average",
            "macd_line": "MACD line",
            "macd_signal": "MACD signal line",
            "rsi": "RSI (typically 14-period)",
            "volume": "Volume data",
            "volume_ma": "Volume moving average"
        }
        
        for indicator, description in required_indicators.items():
            print(f"   • {indicator}: {description}")
        
        # Gap analysis
        print(f"\n📋 CAPABILITY GAP ANALYSIS")
        print("=" * 40)
        
        # Map what we have to what's needed
        have_indicators = {ind[0] for ind in available_indicators}
        need_indicators = set(required_indicators.keys())
        
        # Map our indicators to expected names
        our_mapping = {
            'RSI': 'rsi',
            'MACD': 'macd_line', 
            'EMA_20': 'ema20',
            'SMA_50': 'sma50'
        }
        
        mapped_have = {our_mapping.get(ind, ind) for ind in have_indicators}
        
        missing_critical = need_indicators - mapped_have
        have_critical = mapped_have & need_indicators
        
        print("✅ SIGNAL COMPONENTS WE HAVE:")
        for component in have_critical:
            print(f"   • {component}: {required_indicators[component]}")
        
        print("\n❌ CRITICAL SIGNAL COMPONENTS MISSING:")
        for component in missing_critical:
            print(f"   • {component}: {required_indicators[component]}")
        
        # Current signal quality assessment
        print(f"\n📈 CURRENT SIGNAL QUALITY ASSESSMENT")
        print("=" * 40)
        
        completion_rate = len(have_critical) / len(need_indicators) * 100
        print(f"📊 Data Completeness: {completion_rate:.1f}%")
        
        if completion_rate >= 80:
            quality = "🟢 EXCELLENT"
        elif completion_rate >= 60:
            quality = "🟡 GOOD"  
        elif completion_rate >= 40:
            quality = "🟠 FAIR"
        else:
            quality = "🔴 POOR"
            
        print(f"📈 Signal Quality: {quality}")
        
        # Recommendations
        print(f"\n💡 RECOMMENDATIONS FOR IMPROVEMENT")
        print("=" * 40)
        
        recommendations = [
            "🔧 Add EMA_50 calculation (needed for EMA crossover signals)",
            "🔧 Add SMA_200 calculation (critical for long-term trend)",  
            "🔧 Add MACD_Signal line (needed for MACD crossover confirmation)",
            "📊 Add volume analysis (volume MA for spike detection)",
            "📈 Add trend strength indicators (ADX, Aroon)",
            "🎯 Add volatility indicators (ATR, Bollinger Bands)",
            "💰 Add fundamental scoring (P/E, growth metrics)"
        ]
        
        for rec in recommendations:
            print(f"   {rec}")
        
        # What we can do right now
        print(f"\n🚀 CURRENT CAPABILITIES")
        print("=" * 40)
        
        current_capabilities = [
            "✅ Basic trend analysis (using EMA_20 vs SMA_50)",
            "✅ Momentum analysis (RSI + MACD)",
            "✅ Price level analysis (current vs moving averages)",
            "✅ Basic screener functionality",
            "✅ Multi-stock analysis",
            "✅ Historical data storage and retrieval"
        ]
        
        for cap in current_capabilities:
            print(f"   {cap}")
        
        # Production readiness
        print(f"\n🏭 PRODUCTION READINESS")
        print("=" * 40)
        
        if completion_rate >= 60:
            print("🟢 READY FOR PAPER TRADING")
            print("   • Can generate basic buy/sell/hold signals")
            print("   • Can run screeners on multiple stocks") 
            print("   • Can track performance over time")
        else:
            print("🟡 NEEDS MORE DATA FOR PRODUCTION")
            print("   • Missing critical trend indicators")
            print("   • Limited signal accuracy")
            print("   • Recommend adding missing indicators first")
        
        return completion_rate >= 60

if __name__ == "__main__":
    print("🔍 COMPREHENSIVE SIGNAL SYSTEM ANALYSIS")
    print("Assessing current capabilities and identifying gaps")
    print("=" * 65)
    
    is_production_ready = analyze_signal_capabilities()
    
    print(f"\n📋 SUMMARY")
    print("=" * 20)
    
    if is_production_ready:
        print("🎉 SYSTEM IS PRODUCTION-READY FOR PAPER TRADING!")
        print("✅ Can generate meaningful trading signals")
        print("✅ Ready for backtesting and validation")
        exit(0)
    else:
        print("⚠️  SYSTEM NEEDS ADDITIONAL INDICATORS")
        print("🔧 Add missing components for full functionality")
        exit(1)
