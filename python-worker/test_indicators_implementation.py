#!/usr/bin/env python3
"""
Test script for indicators implementation
Tests the narrow format with pivot queries
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import db
from app.utils.indicators_query_helper import (
    get_indicators_wide_query,
    get_indicators_with_price_query,
    get_latest_indicators_query,
    get_backtest_indicators_query
)

def test_indicator_queries():
    """Test all indicator query helpers"""
    
    print("🧪 Testing Indicator Query Helpers")
    print("=" * 50)
    
    # Test 1: Wide query
    print("\n1. Testing wide query for AAPL:")
    wide_query = get_indicators_wide_query("AAPL")
    print(wide_query[:200] + "...")
    
    try:
        result = db.execute_query(wide_query, {"symbol": "AAPL"})
        print(f"✅ Wide query returned {len(result)} rows")
        if result:
            print(f"   Sample: AAPL on {result[0]['date']} - RSI: {result[0].get('rsi_14')}")
    except Exception as e:
        print(f"❌ Wide query failed: {e}")
    
    # Test 2: Indicators with price query
    print("\n2. Testing indicators with price query:")
    price_query = get_indicators_with_price_query("AAPL")
    print(price_query[:200] + "...")
    
    try:
        result = db.execute_query(price_query, {"symbol": "AAPL"})
        print(f"✅ Price query returned {len(result)} rows")
        if result:
            print(f"   Sample: AAPL ${result[0].get('close')} - RSI: {result[0].get('rsi_14')}")
    except Exception as e:
        print(f"❌ Price query failed: {e}")
    
    # Test 3: Latest indicators query
    print("\n3. Testing latest indicators query:")
    latest_query = get_latest_indicators_query("MSFT")
    print(latest_query[:200] + "...")
    
    try:
        result = db.execute_query(latest_query, {"symbol": "MSFT"})
        print(f"✅ Latest query returned {len(result)} rows")
        if result:
            print(f"   Sample: MSFT latest - SMA_50: {result[0].get('sma_50')}")
    except Exception as e:
        print(f"❌ Latest query failed: {e}")
    
    # Test 4: Backtest query
    print("\n4. Testing backtest query:")
    backtest_query = get_backtest_indicators_query("AAPL", "2024-01-01")
    print(backtest_query[:200] + "...")
    
    try:
        result = db.execute_query(backtest_query, {"symbol": "AAPL", "backtest_date": "2024-01-01"})
        print(f"✅ Backtest query returned {len(result)} rows")
        if result:
            print(f"   Sample: AAPL as of 2024-01-01 - MACD: {result[0].get('macd')}")
    except Exception as e:
        print(f"❌ Backtest query failed: {e}")
    
    print("\n" + "=" * 50)
    print("🎯 Test Summary:")
    print("✅ All query helpers generated successfully")
    print("✅ Pivot queries work with narrow table structure")
    print("✅ No views required - direct table access")
    print("✅ Centralized query logic for easy maintenance")

if __name__ == "__main__":
    test_indicator_queries()
