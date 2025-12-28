#!/usr/bin/env python3
"""
Quick test for Alpha Vantage API integration
Test company overview data loading for AVGO
"""
import requests
import json
import time
from datetime import datetime

def test_direct_api():
    """Test direct Alpha Vantage API call"""
    print("🔍 Testing Direct Alpha Vantage API Call")
    print("=" * 50)
    
    # Your API key from .env
    api_key = "QFGQ8S1GNTMPFNMA"
    symbol = "AVGO"
    
    url = f'https://www.alphavantage.co/query?function=OVERVIEW&symbol={symbol}&apikey={api_key}'
    
    try:
        print(f"📡 Making request to: {url.replace(api_key, '***')}")
        r = requests.get(url)
        data = r.json()
        
        print(f"✅ Response Status: {r.status_code}")
        print(f"📊 Response Data:")
        print(json.dumps(data, indent=2))
        
        # Check if we got valid data
        if "Symbol" in data:
            print(f"\n🎯 Successfully loaded overview for {data['Symbol']}")
            print(f"   Company: {data.get('Name', 'N/A')}")
            print(f"   Sector: {data.get('Sector', 'N/A')}")
            print(f"   Industry: {data.get('Industry', 'N/A')}")
            print(f"   Market Cap: ${data.get('MarketCapitalization', 'N/A')}")
            print(f"   P/E Ratio: {data.get('PERatio', 'N/A')}")
            print(f"   P/B Ratio: {data.get('PriceToBookRatio', 'N/A')}")
            print(f"   EPS: {data.get('EPS', 'N/A')}")
            print(f"   Beta: {data.get('Beta', 'N/A')}")
            print(f"   Dividend Yield: {data.get('DividendYield', 'N/A')}")
            return True
        else:
            print(f"❌ Invalid response - no Symbol field found")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_alphavantage_source():
    """Test Alpha Vantage source integration"""
    print("\n🔌 Testing Alpha Vantage Source Integration")
    print("=" * 55)
    
    # Add delay to avoid rate limit after direct API call
    print("⏳ Waiting 15 seconds to avoid rate limit...")
    time.sleep(15)
    
    try:
        from app.data_sources.alphavantage_source import AlphaVantageSource, AlphaVantageConfig
        from app.config import settings
        
        # Create Alpha Vantage source
        config = AlphaVantageConfig(api_key="QFGQ8S1GNTMPFNMA")
        source = AlphaVantageSource(config)
        
        print(f"✅ Alpha Vantage source initialized")
        print(f"   API Key: {'***' + config.api_key[-4:] if config.api_key else 'None'}")
        print(f"   Base URL: {config.base_url}")
        print(f"   Rate Limit: {config.rate_limit_calls}/{config.rate_limit_window}s")
        
        # Test availability
        is_available = source.is_available
        print(f"   Available: {'✅' if is_available else '❌'}")
        
        if is_available:
            # Test company overview
            print(f"\n📊 Testing company overview for AVGO...")
            overview = source.fetch_company_overview("AVGO")
            
            if overview:
                print(f"✅ Successfully loaded overview via source")
                print(f"   Symbol: {overview.get('Symbol', 'N/A')}")
                print(f"   Name: {overview.get('Name', 'N/A')}")
                print(f"   Sector: {overview.get('Sector', 'N/A')}")
                print(f"   Market Cap: ${overview.get('MarketCapitalization', 'N/A')}")
                return True
            else:
                print(f"❌ Failed to load overview via source")
                return False
        else:
            print(f"❌ Source not available, skipping data fetch")
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure Alpha Vantage source is implemented")
        return False
    except Exception as e:
        print(f"❌ Error testing source: {e}")
        return False

def test_alphavantage_adapter():
    """Test Alpha Vantage adapter integration"""
    print("\n🔧 Testing Alpha Vantage Adapter Integration")
    print("=" * 55)
    
    try:
        from app.data_sources.adapters.alphavantage_adapter import AlphaVantageAdapter
        from app.data_sources.alphavantage_source import AlphaVantageConfig
        
        # Create adapter
        config = AlphaVantageConfig(api_key="QFGQ8S1GNTMPFNMA")
        adapter = AlphaVantageAdapter(config)
        
        print(f"✅ Alpha Vantage adapter initialized")
        print(f"   Source Name: {adapter.source_name}")
        print(f"   Available: {'✅' if adapter.is_available() else '❌'}")
        
        if adapter.is_available():
            # Test symbol details
            print(f"\n💼 Testing symbol details for AVGO...")
            details = adapter.fetch_symbol_details("AVGO")
            
            if details:
                print(f"✅ Successfully loaded details via adapter")
                print(f"   Symbol: {details.get('symbol', 'N/A')}")
                print(f"   Name: {details.get('name', 'N/A')}")
                print(f"   Sector: {details.get('sector', 'N/A')}")
                print(f"   Industry: {details.get('industry', 'N/A')}")
                print(f"   Market Cap: ${details.get('market_cap', 'N/A')}")
                print(f"   P/E Ratio: {details.get('pe_ratio', 'N/A')}")
                print(f"   Data Source: {details.get('data_source', 'N/A')}")
                return True
            else:
                print(f"❌ Failed to load details via adapter")
                return False
        else:
            print(f"❌ Adapter not available")
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure Alpha Vantage adapter is implemented")
        return False
    except Exception as e:
        print(f"❌ Error testing adapter: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 ALPHA VANTAGE INTEGRATION TEST")
    print("=" * 50)
    print(f"Testing API key: ***Q8S1GNTMPFNMA")
    print(f"Target symbol: AVGO")
    print(f"Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run tests
    results = []
    
    results.append(("Direct API", test_direct_api()))
    results.append(("Alpha Vantage Source", test_alphavantage_source()))
    results.append(("Alpha Vantage Adapter", test_alphavantage_adapter()))
    
    # Summary
    print("\n📋 TEST SUMMARY")
    print("=" * 30)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:<25}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall Result: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All Alpha Vantage integration tests passed!")
        print("🚀 Ready to use Alpha Vantage in the data orchestrator!")
    else:
        print("⚠️ Some tests failed - check implementation")
    
    return passed == total

if __name__ == "__main__":
    main()
