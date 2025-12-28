#!/usr/bin/env python3
"""
Test Massive.com API for stock symbol details
"""
import requests
import json
from app.config import settings

def test_massive_api(symbol="AAPL"):
    """Test Massive.com API directly"""
    print(f"🔍 Testing Massive.com API for {symbol}")
    print("=" * 40)
    
    url = f"https://api.massive.com/v3/reference/tickers/{symbol.upper()}"
    params = {"apiKey": settings.massive_api_key}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if "results" in data and data["results"]:
            ticker = data["results"]
            
            print(f"✅ Symbol: {ticker.get('ticker', 'N/A')}")
            print(f"📛 Name: {ticker.get('name', 'N/A')}")
            print(f"💼 Market: {ticker.get('market', 'N/A')}")
            print(f"🏢 Exchange: {ticker.get('primary_exchange', 'N/A')}")
            print(f"💰 Market Cap: ${ticker.get('market_cap', 0):,.0f}")
            print(f"💵 Currency: {ticker.get('currency_name', 'N/A')}")
            print(f"🌍 Country: {ticker.get('locale', 'N/A').upper()}")
            print(f"📊 Type: {ticker.get('type', 'N/A')}")
            print(f"✅ Active: {ticker.get('active', False)}")
            print(f"👥 Employees: {ticker.get('total_employees', 'N/A'):,}")
            print(f"📞 Phone: {ticker.get('phone_number', 'N/A')}")
            print(f"🌐 Website: {ticker.get('homepage_url', 'N/A')}")
            
            # Address
            address = ticker.get('address', {})
            if address:
                print(f"📍 Address: {address.get('address1', '')}, {address.get('city', '')}, {address.get('state', '')} {address.get('postal_code', '')}")
            
            # Description (truncated)
            description = ticker.get('description', '')
            if description:
                print(f"📝 Description: {description[:200]}...")
            
            print(f"\n🎯 Full Response Status: {data.get('status', 'N/A')}")
            print(f"🆔 Request ID: {data.get('request_id', 'N/A')}")
            
            return True
        else:
            print(f"❌ No data found for {symbol}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ HTTP Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_multiple_symbols():
    """Test multiple symbols"""
    symbols = ["AAPL", "MSFT", "GOOGL", "TSLA"]
    
    print("\n📊 Testing Multiple Symbols")
    print("=" * 30)
    
    results = {}
    for symbol in symbols:
        print(f"\nTesting {symbol}...")
        results[symbol] = test_massive_api(symbol)
        print("-" * 40)
    
    # Summary
    print(f"\n📋 Summary:")
    working = sum(1 for success in results.values() if success)
    print(f"✅ Working: {working}/{len(symbols)} symbols")
    
    for symbol, success in results.items():
        status = "✅" if success else "❌"
        print(f"   {status} {symbol}")

if __name__ == "__main__":
    print("🚀 Massive.com API Test")
    print("=" * 30)
    
    # Test single symbol
    if test_massive_api("AAPL"):
        print("\n✅ Single symbol test passed!")
        
        # Test multiple symbols
        test_multiple_symbols()
        
        print(f"\n🎉 API is working! You can use:")
        print(f"curl -X GET \"https://api.massive.com/v3/reference/tickers/AAPL?apiKey={settings.massive_api_key}\"")
    else:
        print("\n❌ API test failed!")
