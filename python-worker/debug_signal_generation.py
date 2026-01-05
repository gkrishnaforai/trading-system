#!/usr/bin/env python3
"""
Debug script to check what's happening with signal generation
"""

import sys
import os
sys.path.append('/app')

from datetime import datetime
from app.services.strategy_service import StrategyService
from app.utils.database_helper import DatabaseQueryHelper

def debug_signal_generation():
    """Debug signal generation for a specific date"""
    
    print("🔍 Debugging Signal Generation")
    print("=" * 50)
    
    # Test date
    test_date = "2025-12-07"
    symbol = "TQQQ"
    strategy = "tqqq_swing"
    
    try:
        # Get strategy service
        strategy_service = StrategyService()
        
        # Get indicators for the test date
        print(f"📊 Getting indicators for {symbol} on {test_date}...")
        
        # Try to get indicators
        from app.database import db
        
        query = """
            SELECT sma_50, sma_200, ema_20, rsi_14, macd, macd_signal 
            FROM indicators_daily 
            WHERE symbol = :symbol AND date <= :backtest_date 
            ORDER BY date DESC LIMIT 1
        """
        
        indicators_data = db.execute_query(query, {
            "symbol": symbol, 
            "backtest_date": test_date
        })
        
        if indicators_data:
            indicators = indicators_data[0]
            print(f"✅ Found indicators: {indicators}")
            
            # Add required fields for strategy
            indicators["price"] = indicators.get("sma_50", 0)
            indicators["ema20"] = indicators.get("ema_20", 0)
            indicators["ema50"] = indicators.get("sma_50", 0)
            indicators["sma200"] = indicators.get("sma_200", 0)
            indicators["macd_line"] = indicators.get("macd", 0)
            indicators["rsi"] = indicators.get("rsi_14", 50)
            
            print(f"📈 Prepared indicators: {indicators}")
            
            # Generate signal
            print(f"🚀 Generating signal using {strategy} strategy...")
            signal_result = strategy_service.execute_strategy(strategy, indicators)
            
            print(f"📊 Signal Result:")
            print(f"  Signal: {signal_result.signal if hasattr(signal_result, 'signal') else 'N/A'}")
            print(f"  Confidence: {signal_result.confidence if hasattr(signal_result, 'confidence') else 'N/A'}")
            print(f"  Reasoning: {signal_result.reasoning if hasattr(signal_result, 'reasoning') else 'N/A'}")
            
            # Check metadata
            if hasattr(signal_result, 'metadata'):
                print(f"  Metadata: {signal_result.metadata}")
            
        else:
            print(f"❌ No indicators found for {symbol} on or before {test_date}")
            
            # Check what dates are available
            dates_query = """
                SELECT DISTINCT date, COUNT(*) as count
                FROM indicators_daily 
                WHERE symbol = :symbol
                GROUP BY date
                ORDER BY date DESC
                LIMIT 10
            """
            
            available_dates = db.execute_query(dates_query, {"symbol": symbol})
            
            if available_dates:
                print(f"📅 Available dates for {symbol}:")
                for date_row in available_dates:
                    print(f"  {date_row['date']}: {date_row['count']} records")
            else:
                print(f"❌ No data at all for {symbol}")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_signal_generation()
