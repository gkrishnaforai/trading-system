#!/usr/bin/env python3
"""
Debug Yahoo Finance Data Loading
Test Yahoo Finance directly to identify the issue
"""

import os
import sys
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yfinance as yf
import pandas as pd

def test_yahoo_finance_direct():
    """Test Yahoo Finance directly without adapters"""
    
    print("🔍 DEBUGGING YAHOO FINANCE DIRECTLY")
    print("=" * 50)
    
    symbol = "NVDA"
    
    try:
        print(f"📊 Testing yfinance.Ticker('{symbol}')...")
        ticker = yf.Ticker(symbol)
        print(f"✅ Ticker object created: {type(ticker)}")
        
        print(f"\n📈 Testing ticker.history()...")
        
        # Test different period parameters
        periods = ["1mo", "3mo", "6mo", "1y", "2y", "5y"]
        
        for period in periods:
            try:
                print(f"\n--- Testing period: {period} ---")
                data = ticker.history(period=period)
                
                if data is not None:
                    print(f"✅ Data type: {type(data)}")
                    print(f"✅ Data shape: {data.shape if hasattr(data, 'shape') else 'No shape'}")
                    print(f"✅ Data empty: {data.empty if hasattr(data, 'empty') else 'Unknown'}")
                    
                    if not data.empty:
                        print(f"✅ Columns: {list(data.columns)}")
                        print(f"✅ Date range: {data.index[0]} to {data.index[-1]}")
                        print(f"✅ Sample data:")
                        print(data.head(2))
                    else:
                        print("⚠️  Data is empty")
                else:
                    print("❌ Data is None")
                    
            except Exception as e:
                print(f"❌ Error with period '{period}': {type(e).__name__}: {str(e)}")
        
        # Test with specific date range
        print(f"\n--- Testing specific date range ---")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        try:
            data = ticker.history(start=start_date, end=end_date)
            print(f"✅ Date range data shape: {data.shape if hasattr(data, 'shape') else 'No shape'}")
            if not data.empty:
                print(f"✅ Date range: {data.index[0]} to {data.index[-1]}")
        except Exception as e:
            print(f"❌ Error with date range: {type(e).__name__}: {str(e)}")
        
        # Test ticker info
        print(f"\n--- Testing ticker.info ---")
        try:
            info = ticker.info
            print(f"✅ Info type: {type(info)}")
            if info:
                print(f"✅ Info keys: {list(info.keys())[:10]}...")  # Show first 10 keys
                print(f"✅ Company name: {info.get('longName', 'N/A')}")
                print(f"✅ Current price: {info.get('currentPrice', 'N/A')}")
            else:
                print("⚠️  Info is empty")
        except Exception as e:
            print(f"❌ Error getting info: {type(e).__name__}: {str(e)}")
        
    except Exception as e:
        print(f"❌ Critical error: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return False
    
    return True

def test_yahoo_finance_source():
    """Test Yahoo Finance source class"""
    
    print(f"\n🔍 TESTING YAHOO FINANCE SOURCE CLASS")
    print("=" * 50)
    
    try:
        from app.data_sources.yahoo_finance_source import YahooFinanceSource
        
        source = YahooFinanceSource()
        print(f"✅ YahooFinanceSource created: {type(source)}")
        
        symbol = "NVDA"
        print(f"\n📊 Testing fetch_price_data for {symbol}...")
        
        # Test with different periods
        periods = ["1mo", "3mo", "6mo", "1y"]
        
        for period in periods:
            try:
                print(f"\n--- Testing period: {period} ---")
                data = source.fetch_price_data(symbol, period=period)
                
                if data is not None:
                    print(f"✅ Data type: {type(data)}")
                    print(f"✅ Data shape: {data.shape}")
                    if not data.empty:
                        print(f"✅ Columns: {list(data.columns)}")
                        print(f"✅ Date range: {data.iloc[0]['date'] if 'date' in data.columns else data.index[0]} to {data.iloc[-1]['date'] if 'date' in data.columns else data.index[-1]}")
                else:
                    print("❌ Data is None")
                    
            except Exception as e:
                print(f"❌ Error with period '{period}': {type(e).__name__}: {str(e)}")
                import traceback
                print(f"Traceback: {traceback.format_exc()}")
        
    except Exception as e:
        print(f"❌ Critical error: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 YAHOO FINANCE DEBUG TEST")
    print("=" * 40)
    
    success = True
    
    # Test direct yfinance usage
    if not test_yahoo_finance_direct():
        success = False
    
    # Test YahooFinanceSource class
    if not test_yahoo_finance_source():
        success = False
    
    if success:
        print(f"\n🎉 YAHOO FINANCE DEBUG TESTS COMPLETED")
        print("Check the output above to identify any issues")
        exit(0)
    else:
        print(f"\n❌ YAHOO FINANCE DEBUG TESTS FAILED")
        exit(1)
