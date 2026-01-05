#!/usr/bin/env python3
"""
Trace exactly where the 404 error comes from
"""

import sys
import os
import logging
import yfinance as yf

# Add the python-worker directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'python-worker'))

# Enable debug logging to see all calls
logging.basicConfig(level=logging.DEBUG)

from app.providers.yahoo_finance.client import YahooFinanceClient, YahooFinanceConfig

def trace_exact_404():
    """Trace exactly where 404 happens"""
    
    print("=" * 60)
    print("Tracing Exact 404 Error Location")
    print("=" * 60)
    
    symbol = "IREN"
    
    print(f"\n🔍 Testing symbol: {symbol}")
    
    # Test 1: Direct yfinance calls
    print(f"\n--- Test 1: Direct yfinance calls ---")
    
    print("1a. Creating ticker...")
    ticker = yf.Ticker(symbol)
    print("✅ Ticker created")
    
    print("1b. Testing ticker.history...")
    hist = ticker.history(period="1d")
    print(f"✅ History works: {hist['Close'].iloc[-1]:.2f}")
    
    print("1c. Testing ticker.info (this should show 404)...")
    try:
        info = ticker.info
        print(f"✅ Info works: {len(info)} fields")
    except Exception as e:
        print(f"❌ Info failed: {e}")
        print(f"📍 FOUND 404 in direct yfinance call!")
    
    # Test 2: Our client with debug logging
    print(f"\n--- Test 2: Our client calls ---")
    
    # Enable debug logging for our client
    logger = logging.getLogger("yahoo_finance_client")
    logger.setLevel(logging.DEBUG)
    
    config = YahooFinanceConfig()
    client = YahooFinanceClient(config)
    
    print("2a. Testing _get_ticker...")
    try:
        ticker = client._get_ticker(symbol)
        print("✅ _get_ticker works")
    except Exception as e:
        print(f"❌ _get_ticker failed: {e}")
    
    print("2b. Testing fetch_symbol_details...")
    try:
        details = client.fetch_symbol_details(symbol)
        print(f"✅ fetch_symbol_details works: {len(details)} fields")
    except Exception as e:
        print(f"❌ fetch_symbol_details failed: {e}")
        print(f"📍 FOUND 404 in fetch_symbol_details!")
    
    print("2c. Testing fetch_fundamentals...")
    try:
        fundamentals = client.fetch_fundamentals(symbol)
        print(f"✅ fetch_fundamentals works: {len(fundamentals)} fields")
    except Exception as e:
        print(f"❌ fetch_fundamentals failed: {e}")
        print(f"📍 FOUND 404 in fetch_fundamentals!")

def test_yfinance_version():
    """Check yfinance version and configuration"""
    
    print(f"\n--- yfinance Version Info ---")
    import yfinance as yf
    print(f"yfinance version: {yf.__version__}")
    
    # Check if there are any configuration options
    print(f"yfinance utils: {dir(yf.utils)}")

if __name__ == "__main__":
    test_yfinance_version()
    trace_exact_404()
