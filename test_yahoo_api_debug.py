#!/usr/bin/env python3
"""
Debug script to test Yahoo Finance API with different symbols
"""

import sys
import os
import yfinance as yf

# Add the python-worker directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'python-worker'))

from app.providers.yahoo_finance.client import YahooFinanceClient, YahooFinanceConfig

def test_multiple_symbols():
    """Test Yahoo Finance API with different symbols"""
    
    print("=" * 60)
    print("Testing Yahoo Finance API with Multiple Symbols")
    print("=" * 60)
    
    # Test symbols - mix of large caps and potentially problematic ones
    test_symbols = [
        "AAPL",   # Large cap - should work
        "MSFT",   # Large cap - should work  
        "TSLA",   # Large cap - should work
        "IREN",   # Our problematic symbol
        "GME",    # Meme stock - might have issues
        "NVDA",   # Large cap - should work
        "AMZN",   # Large cap - should work
        "XYZ",    # Invalid symbol - should fail
    ]
    
    config = YahooFinanceConfig()
    client = YahooFinanceClient(config)
    
    for symbol in test_symbols:
        print(f"\n--- Testing {symbol} ---")
        
        try:
            # Test 1: Direct yfinance ticker.info call
            print(f"1. Testing yfinance.Ticker('{symbol}').info...")
            ticker = yf.Ticker(symbol)
            
            # First try to get history to validate symbol exists
            hist = ticker.history(period="1d")
            if hist.empty:
                print(f"   ❌ No price history - symbol likely invalid")
                continue
            else:
                print(f"   ✅ Price history available: {len(hist)} days")
            
            # Now try info (this is where 404 happens)
            info = ticker.info
            if info:
                print(f"   ✅ Info available: {len(info)} fields")
                key_fields = ['symbol', 'shortName', 'sector', 'industry', 'marketCap']
                for field in key_fields:
                    value = info.get(field)
                    if value:
                        print(f"      - {field}: {value}")
            else:
                print(f"   ❌ Info returned None or empty")
                
        except Exception as e:
            print(f"   ❌ Error with yfinance direct: {e}")
        
        try:
            # Test 2: Using our client's fetch_symbol_details
            print(f"2. Testing client.fetch_symbol_details('{symbol}')...")
            details = client.fetch_symbol_details(symbol)
            if details:
                print(f"   ✅ Client details available: {len(details)} fields")
                key_fields = ['symbol', 'name', 'sector', 'industry', 'market_cap']
                for field in key_fields:
                    value = details.get(field)
                    if value:
                        print(f"      - {field}: {value}")
            else:
                print(f"   ❌ Client details returned empty")
                
        except Exception as e:
            print(f"   ❌ Error with client: {e}")
        
        try:
            # Test 3: Using our client's fetch_fundamentals
            print(f"3. Testing client.fetch_fundamentals('{symbol}')...")
            fundamentals = client.fetch_fundamentals(symbol)
            if fundamentals:
                print(f"   ✅ Fundamentals available: {len(fundamentals)} fields")
                # Show a few key fields
                key_fields = ['symbol', 'sector', 'industry', 'market_cap', 'revenue']
                for field in key_fields:
                    value = fundamentals.get(field)
                    if value:
                        print(f"      - {field}: {value}")
            else:
                print(f"   ❌ Fundamentals returned empty")
                
        except Exception as e:
            print(f"   ❌ Error with fundamentals: {e}")
    
    print("\n" + "=" * 60)
    print("Analysis Complete")
    print("=" * 60)

def test_yfinance_endpoints():
    """Test which yfinance endpoints are working"""
    
    print("\n" + "=" * 60)
    print("Testing yfinance Endpoints Directly")
    print("=" * 60)
    
    symbol = "IREN"
    ticker = yf.Ticker(symbol)
    
    print(f"\nTesting endpoints for {symbol}:")
    
    # Test different endpoints
    endpoints = [
        ("history", lambda: ticker.history(period="5d")),
        ("info", lambda: ticker.info),
        ("financials", lambda: ticker.financials),
        ("balance_sheet", lambda: ticker.balance_sheet),
        ("cashflow", lambda: ticker.cashflow),
        ("earnings", lambda: ticker.earnings),
        ("quarterly_financials", lambda: ticker.quarterly_financials),
    ]
    
    for name, func in endpoints:
        try:
            print(f"\n{name}:")
            result = func()
            if hasattr(result, 'empty'):  # DataFrame
                if not result.empty:
                    print(f"   ✅ Available: {result.shape}")
                else:
                    print(f"   ❌ Empty DataFrame")
            elif isinstance(result, dict):
                if result:
                    print(f"   ✅ Available: {len(result)} keys")
                else:
                    print(f"   ❌ Empty dict")
            elif result is not None:
                print(f"   ✅ Available: {type(result)}")
            else:
                print(f"   ❌ None")
        except Exception as e:
            print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    test_multiple_symbols()
    test_yfinance_endpoints()
