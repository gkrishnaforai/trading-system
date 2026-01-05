#!/usr/bin/env python3
"""
Debug script to trace exactly where fetch_fundamentals fails for IREN
"""

import sys
import os
import traceback
import yfinance as yf

# Add the python-worker directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'python-worker'))

from app.providers.yahoo_finance.client import YahooFinanceClient, YahooFinanceConfig

def debug_fetch_fundamentals(symbol="IREN"):
    """Debug the exact fetch_fundamentals call step by step"""
    
    print("=" * 60)
    print(f"Debugging fetch_fundamentals for {symbol}")
    print("=" * 60)
    
    config = YahooFinanceConfig()
    client = YahooFinanceClient(config)
    
    print(f"\n🔍 Step 1: Calling fetch_fundamentals('{symbol}')...")
    
    try:
        # This is the exact call that's failing
        result = client.fetch_fundamentals(symbol)
        print(f"✅ SUCCESS: Got {len(result)} fields")
        return result
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        print(f"\n🔍 Let's trace where this happens...")
        
        # Step-by-step debugging
        print(f"\n--- Step 1: Get ticker ---")
        try:
            ticker = client._get_ticker(symbol)
            print(f"✅ Ticker created: {type(ticker)}")
        except Exception as e:
            print(f"❌ Failed to get ticker: {e}")
            return None
        
        print(f"\n--- Step 2: Test ticker.history (basic validation) ---")
        try:
            hist = ticker.history(period="1d")
            if hist.empty:
                print(f"❌ No history data - symbol might be invalid")
                return None
            else:
                print(f"✅ History works: {hist.shape[0]} days, price: {hist['Close'].iloc[-1]:.2f}")
        except Exception as e:
            print(f"❌ History failed: {e}")
            return None
        
        print(f"\n--- Step 3: Test ticker.info (this is where 404 happens) ---")
        try:
            print("   Calling ticker.info...")
            info = ticker.info
            if info:
                print(f"✅ Info available: {len(info)} fields")
                # Show some key fields
                key_fields = ['symbol', 'shortName', 'sector', 'industry', 'marketCap']
                for field in key_fields:
                    value = info.get(field)
                    if value:
                        print(f"      - {field}: {value}")
            else:
                print(f"❌ Info returned None or empty")
        except Exception as e:
            print(f"❌ Info failed: {e}")
            print(f"   This is the 404 error source!")
            
            # Let's see the exact error
            if "404" in str(e):
                print(f"   📍 CONFIRMED: 404 error from ticker.info")
                print(f"   📍 This means Yahoo's quoteSummary endpoint has no data for {symbol}")
        
        print(f"\n--- Step 4: Test fetch_symbol_details (calls ticker.info) ---")
        try:
            details = client.fetch_symbol_details(symbol)
            if details:
                print(f"✅ Symbol details work via fallback: {len(details)} fields")
            else:
                print(f"❌ Symbol details failed")
        except Exception as e:
            print(f"❌ Symbol details failed: {e}")
        
        print(f"\n--- Step 5: Test financial statements (different endpoints) ---")
        try:
            print("   Testing ticker.financials...")
            financials = ticker.financials
            if not financials.empty:
                print(f"✅ Financials work: {financials.shape}")
            else:
                print(f"❌ Financials empty")
        except Exception as e:
            print(f"❌ Financials failed: {e}")
        
        try:
            print("   Testing ticker.balance_sheet...")
            balance_sheet = ticker.balance_sheet
            if not balance_sheet.empty:
                print(f"✅ Balance sheet works: {balance_sheet.shape}")
            else:
                print(f"❌ Balance sheet empty")
        except Exception as e:
            print(f"❌ Balance sheet failed: {e}")
        
        try:
            print("   Testing ticker.cashflow...")
            cashflow = ticker.cashflow
            if not cashflow.empty:
                print(f"✅ Cashflow works: {cashflow.shape}")
            else:
                print(f"❌ Cashflow empty")
        except Exception as e:
            print(f"❌ Cashflow failed: {e}")
        
        return None

def test_working_symbol():
    """Test with a symbol that should work to confirm the API is functional"""
    
    print("\n" + "=" * 60)
    print("Testing with AAPL (should work)")
    print("=" * 60)
    
    config = YahooFinanceConfig()
    client = YahooFinanceClient(config)
    
    try:
        result = client.fetch_fundamentals("AAPL")
        print(f"✅ AAPL works: {len(result)} fields")
        
        # Show some fields
        key_fields = ['symbol', 'name', 'sector', 'market_cap', 'revenue']
        for field in key_fields:
            value = result.get(field)
            if value:
                print(f"   - {field}: {value}")
                
    except Exception as e:
        print(f"❌ Even AAPL failed: {e}")
        traceback.print_exc()

def test_yfinance_direct():
    """Test yfinance directly to understand the API behavior"""
    
    print("\n" + "=" * 60)
    print("Testing yfinance directly")
    print("=" * 60)
    
    symbols = ["AAPL", "IREN"]
    
    for symbol in symbols:
        print(f"\n--- Testing {symbol} directly with yfinance ---")
        
        try:
            ticker = yf.Ticker(symbol)
            
            # Test history first
            hist = ticker.history(period="1d")
            if hist.empty:
                print(f"   ❌ No history data")
                continue
            else:
                print(f"   ✅ History: {hist['Close'].iloc[-1]:.2f}")
            
            # Test info (where 404 happens)
            try:
                info = ticker.info
                if info and len(info) > 5:  # More than basic data
                    print(f"   ✅ Full info: {len(info)} fields")
                    print(f"      Name: {info.get('longName', 'N/A')}")
                    print(f"      Sector: {info.get('sector', 'N/A')}")
                else:
                    print(f"   ⚠️ Limited info: {len(info) if info else 0} fields")
            except Exception as e:
                print(f"   ❌ Info failed: {e}")
                if "404" in str(e):
                    print(f"      📍 404 from quoteSummary endpoint")
            
            # Test financials
            try:
                financials = ticker.financials
                if not financials.empty:
                    print(f"   ✅ Financials: {financials.shape}")
                else:
                    print(f"   ❌ Empty financials")
            except Exception as e:
                print(f"   ❌ Financials failed: {e}")
                
        except Exception as e:
            print(f"   ❌ Ticker failed: {e}")

if __name__ == "__main__":
    # Test the problematic symbol
    debug_fetch_fundamentals("IREN")
    
    # Test a working symbol
    test_working_symbol()
    
    # Test yfinance directly
    test_yfinance_direct()
