#!/usr/bin/env python3
"""
Debug FMP API Issues
Test the API key and identify what's causing the 402 errors
"""
import sys
import os
import requests
from datetime import datetime

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

API_KEY = "4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ"
BASE_URL = "https://financialmodelingprep.com/stable"


def test_direct_requests():
    """Test direct requests without any wrapper"""
    print("🔍 TESTING DIRECT REQUESTS")
    print("=" * 50)
    
    # Test 1: Quote (should work)
    print("\n1️⃣ Testing Quote Endpoint...")
    try:
        url = f"{BASE_URL}/quote"
        params = {"symbol": "AAPL", "apikey": API_KEY}
        response = requests.get(url, params=params, timeout=10)
        
        print(f"   Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ SUCCESS: {len(data)} records")
            if data:
                print(f"   ✅ AAPL Price: ${data[0]['price']}")
        else:
            print(f"   ❌ FAILED: {response.text}")
    except Exception as e:
        print(f"   ❌ EXCEPTION: {e}")
    
    # Test 2: Key Metrics (should work based on curl)
    print("\n2️⃣ Testing Key Metrics Endpoint...")
    try:
        url = f"{BASE_URL}/key-metrics"
        params = {"symbol": "AAPL", "period": "quarter", "apikey": API_KEY}
        response = requests.get(url, params=params, timeout=10)
        
        print(f"   Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ SUCCESS: {len(data)} records")
            if data:
                print(f"   ✅ Latest Market Cap: ${data[0]['marketCap']:,}")
        else:
            print(f"   ❌ FAILED: {response.text}")
    except Exception as e:
        print(f"   ❌ EXCEPTION: {e}")
    
    # Test 3: Financial Ratios (should work based on curl)
    print("\n3️⃣ Testing Financial Ratios Endpoint...")
    try:
        url = f"{BASE_URL}/ratios"
        params = {"symbol": "AAPL", "period": "quarter", "apikey": API_KEY}
        response = requests.get(url, params=params, timeout=10)
        
        print(f"   Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ SUCCESS: {len(data)} records")
            if data:
                print(f"   ✅ Latest P/E Ratio: {data[0].get('priceEarningsRatio', 'N/A')}")
        else:
            print(f"   ❌ FAILED: {response.text}")
    except Exception as e:
        print(f"   ❌ EXCEPTION: {e}")


def test_enhanced_client():
    """Test the enhanced FMP client"""
    print("\n🔍 TESTING ENHANCED FMP CLIENT")
    print("=" * 50)
    
    try:
        # Import the enhanced client
        from app.providers.financial_modeling_prep.client import EnhancedFMPClient, FinancialModelingPrepConfig
        
        # Create config
        config = FinancialModelingPrepConfig(
            api_key=API_KEY,
            base_url=BASE_URL,
            timeout=30,
            max_retries=3,
            retry_delay=1.0,
            rate_limit_calls=60,
            rate_limit_window=60.0
        )
        
        # Create client
        client = EnhancedFMPClient(config)
        print(f"✅ Enhanced client created successfully")
        
        # Test quote
        print("\n1️⃣ Testing Quote with Enhanced Client...")
        try:
            quote = client.get_real_time_quote("AAPL")
            if quote:
                print(f"   ✅ SUCCESS: AAPL Price: ${quote['price']}")
            else:
                print(f"   ❌ FAILED: No data returned")
        except Exception as e:
            print(f"   ❌ EXCEPTION: {e}")
        
        # Test key metrics
        print("\n2️⃣ Testing Key Metrics with Enhanced Client...")
        try:
            metrics = client.get_key_metrics("AAPL", "quarter")
            if metrics:
                print(f"   ✅ SUCCESS: {len(metrics)} records")
                if metrics:
                    print(f"   ✅ Latest Market Cap: ${metrics[0]['marketCap']:,}")
            else:
                print(f"   ❌ FAILED: No data returned")
        except Exception as e:
            print(f"   ❌ EXCEPTION: {e}")
        
        # Test financial ratios
        print("\n3️⃣ Testing Financial Ratios with Enhanced Client...")
        try:
            ratios = client.get_financial_ratios("AAPL", "quarter")
            if ratios:
                print(f"   ✅ SUCCESS: {len(ratios)} records")
                if ratios:
                    print(f"   ✅ Latest P/E Ratio: {ratios[0].get('priceEarningsRatio', 'N/A')}")
            else:
                print(f"   ❌ FAILED: No data returned")
        except Exception as e:
            print(f"   ❌ EXCEPTION: {e}")
        
    except ImportError as e:
        print(f"❌ IMPORT ERROR: {e}")
        print("   This suggests missing dependencies or import issues")
    except Exception as e:
        print(f"❌ CLIENT ERROR: {e}")


def test_legacy_client():
    """Test the legacy FMP client wrapper"""
    print("\n🔍 TESTING LEGACY FMP CLIENT")
    print("=" * 50)
    
    try:
        # Import the legacy client
        from app.providers.financial_modeling_prep.client import FinancialModelingPrepClient
        
        # Create client from settings (this should use your API key)
        client = FinancialModelingPrepClient.from_settings()
        print(f"✅ Legacy client created successfully")
        print(f"   API Key: {client.config.api_key[:10]}...")
        print(f"   Base URL: {client.config.base_url}")
        
        # Test quote
        print("\n1️⃣ Testing Quote with Legacy Client...")
        try:
            quote = client.fetch_current_price("AAPL")
            if quote:
                print(f"   ✅ SUCCESS: AAPL Price: ${quote['price']}")
            else:
                print(f"   ❌ FAILED: No data returned")
        except Exception as e:
            print(f"   ❌ EXCEPTION: {e}")
        
        # Test fundamentals (this should call comprehensive data)
        print("\n2️⃣ Testing Fundamentals with Legacy Client...")
        try:
            fundamentals = client.fetch_fundamentals("AAPL")
            if fundamentals:
                print(f"   ✅ SUCCESS: Fundamentals data available")
                print(f"   ✅ Data keys: {list(fundamentals.keys())}")
            else:
                print(f"   ❌ FAILED: No data returned")
        except Exception as e:
            print(f"   ❌ EXCEPTION: {e}")
        
    except ImportError as e:
        print(f"❌ IMPORT ERROR: {e}")
        print("   This suggests missing dependencies or import issues")
    except Exception as e:
        print(f"❌ CLIENT ERROR: {e}")


def test_dependencies():
    """Test if all dependencies are available"""
    print("\n🔍 TESTING DEPENDENCIES")
    print("=" * 50)
    
    dependencies = [
        ("requests", "HTTP library"),
        ("pandas", "Data manipulation"),
        ("app.config", "Configuration"),
        ("app.utils.rate_limiter", "Rate limiting"),
        ("app.observability.logging", "Logging"),
    ]
    
    for module_name, description in dependencies:
        try:
            __import__(module_name)
            print(f"   ✅ {module_name} - {description}")
        except ImportError as e:
            print(f"   ❌ {module_name} - MISSING: {e}")


def main():
    """Main debug function"""
    print("🐛 FMP API DEBUG TOOL")
    print("=" * 60)
    print(f"API Key: {API_KEY}")
    print(f"Base URL: {BASE_URL}")
    print("=" * 60)
    
    # Test dependencies first
    test_dependencies()
    
    # Test direct requests
    test_direct_requests()
    
    # Test enhanced client
    test_enhanced_client()
    
    # Test legacy client
    test_legacy_client()
    
    print("\n" + "=" * 60)
    print("🎯 DEBUG COMPLETE")
    print("=" * 60)
    print("If direct requests work but the client fails, the issue is:")
    print("1. Missing dependencies (rate_limiter, logging)")
    print("2. Configuration issues (wrong API key from settings)")
    print("3. Rate limiting problems")
    print("4. Session/request handling issues")


if __name__ == "__main__":
    main()
