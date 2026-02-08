#!/usr/bin/env python3
"""
Compare curl vs Python requests to identify the difference
"""
import sys
import os
import requests
import json
from datetime import datetime

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

API_KEY = "4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ"
BASE_URL = "https://financialmodelingprep.com/stable"


def test_curl_equivalent():
    """Test exact curl equivalent in Python"""
    print("🔍 TESTING CURL EQUIVALENT IN PYTHON")
    print("=" * 60)
    
    # Test 1: Key Metrics - exact curl equivalent
    print("\n1️⃣ Testing Key Metrics (curl equivalent)...")
    
    # This is exactly what curl does:
    # curl "https://financialmodelingprep.com/stable/key-metrics?symbol=AAPL&period=quarter&apikey=4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ"
    
    url = "https://financialmodelingprep.com/stable/key-metrics"
    params = {
        "symbol": "AAPL",
        "period": "quarter", 
        "apikey": "4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ"
    }
    
    print(f"   URL: {url}")
    print(f"   Params: {params}")
    
    try:
        # Try with different approaches
        approaches = [
            ("Basic requests.get", lambda: requests.get(url, params=params)),
            ("With headers", lambda: requests.get(url, params=params, headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate"
            })),
            ("With session", lambda: requests.Session().get(url, params=params)),
            ("URL params in string", lambda: requests.get(f"{url}?symbol=AAPL&period=quarter&apikey=4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ")),
        ]
        
        for approach_name, approach_func in approaches:
            print(f"\n   Trying: {approach_name}")
            try:
                response = approach_func()
                print(f"   Status Code: {response.status_code}")
                print(f"   Headers: {dict(response.headers)}")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"   ✅ SUCCESS: {len(data)} records")
                    if data:
                        print(f"   ✅ Market Cap: ${data[0]['marketCap']:,}")
                    break
                else:
                    print(f"   ❌ FAILED: {response.text}")
                    print(f"   Response headers: {dict(response.headers)}")
                    
            except Exception as e:
                print(f"   ❌ EXCEPTION: {e}")
        
    except Exception as e:
        print(f"   ❌ MAJOR ERROR: {e}")
    
    # Test 2: Compare with working endpoint
    print("\n2️⃣ Testing Quote (working endpoint) for comparison...")
    try:
        url = "https://financialmodelingprep.com/stable/quote"
        params = {
            "symbol": "AAPL",
            "apikey": "4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ"
        }
        
        response = requests.get(url, params=params)
        print(f"   Status Code: {response.status_code}")
        print(f"   Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ SUCCESS: {len(data)} records")
            if data:
                print(f"   ✅ Price: ${data[0]['price']}")
        else:
            print(f"   ❌ FAILED: {response.text}")
            
    except Exception as e:
        print(f"   ❌ ERROR: {e}")


def test_different_base_urls():
    """Test different base URLs"""
    print("\n🔍 TESTING DIFFERENT BASE URLS")
    print("=" * 60)
    
    base_urls = [
        "https://financialmodelingprep.com/stable",
        "https://financialmodelingprep.com/api/v3",
        "https://api.financialmodelingprep.com/stable",
        "https://api.financialmodelingprep.com/api/v3",
    ]
    
    endpoint = "/key-metrics"
    params = {
        "symbol": "AAPL",
        "period": "quarter",
        "apikey": API_KEY
    }
    
    for base_url in base_urls:
        print(f"\n📊 Testing: {base_url}")
        try:
            url = f"{base_url}{endpoint}"
            response = requests.get(url, params=params, timeout=10)
            
            print(f"   Status Code: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ SUCCESS: {len(data)} records")
                break
            elif response.status_code == 402:
                print(f"   ❌ PAYMENT REQUIRED")
            else:
                print(f"   ❌ FAILED: {response.text[:100]}")
                
        except Exception as e:
            print(f"   ❌ EXCEPTION: {e}")


def test_different_params():
    """Test different parameter combinations"""
    print("\n🔍 TESTING DIFFERENT PARAMETER COMBINATIONS")
    print("=" * 60)
    
    base_url = "https://financialmodelingprep.com/stable/key-metrics"
    
    param_combinations = [
        # Standard
        {"symbol": "AAPL", "period": "quarter", "apikey": API_KEY},
        # Without period
        {"symbol": "AAPL", "apikey": API_KEY},
        # Different period
        {"symbol": "AAPL", "period": "annual", "apikey": API_KEY},
        # API key first
        {"apikey": API_KEY, "symbol": "AAPL", "period": "quarter"},
        # Different parameter names
        {"symbol": "AAPL", "period": "quarter", "api_key": API_KEY},
    ]
    
    for i, params in enumerate(param_combinations):
        print(f"\n📊 Testing params combination {i+1}: {params}")
        try:
            response = requests.get(base_url, params=params, timeout=10)
            
            print(f"   Status Code: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ SUCCESS: {len(data)} records")
                break
            elif response.status_code == 402:
                print(f"   ❌ PAYMENT REQUIRED")
            else:
                print(f"   ❌ FAILED: {response.text[:100]}")
                
        except Exception as e:
            print(f"   ❌ EXCEPTION: {e}")


def test_with_authentication():
    """Test with different authentication methods"""
    print("\n🔍 TESTING DIFFERENT AUTHENTICATION METHODS")
    print("=" * 60)
    
    base_url = "https://financialmodelingprep.com/stable/key-metrics"
    
    auth_methods = [
        # Query parameter (standard)
        ("Query Parameter", lambda: requests.get(base_url, params={
            "symbol": "AAPL", 
            "period": "quarter", 
            "apikey": API_KEY
        })),
        # Header
        ("Header", lambda: requests.get(base_url, params={
            "symbol": "AAPL", 
            "period": "quarter"
        }, headers={
            "Authorization": f"Bearer {API_KEY}"
        })),
        # Custom header
        ("Custom Header", lambda: requests.get(base_url, params={
            "symbol": "AAPL", 
            "period": "quarter"
        }, headers={
            "X-API-Key": API_KEY
        })),
    ]
    
    for method_name, method_func in auth_methods:
        print(f"\n📊 Testing: {method_name}")
        try:
            response = method_func()
            
            print(f"   Status Code: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ SUCCESS: {len(data)} records")
                break
            elif response.status_code == 402:
                print(f"   ❌ PAYMENT REQUIRED")
            else:
                print(f"   ❌ FAILED: {response.text[:100]}")
                
        except Exception as e:
            print(f"   ❌ EXCEPTION: {e}")


def analyze_curl_vs_python():
    """Analyze the exact difference between curl and Python"""
    print("\n🔍 ANALYZING CURL VS PYTHON DIFFERENCES")
    print("=" * 60)
    
    print("📋 CURL Command (WORKS):")
    print('curl "https://financialmodelingprep.com/stable/key-metrics?symbol=AAPL&period=quarter&apikey=4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ"')
    
    print("\n📋 Python requests (FAILS):")
    print('requests.get("https://financialmodelingprep.com/stable/key-metrics", params={')
    print('    "symbol": "AAPL",')
    print('    "period": "quarter",')
    print('    "apikey": "4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ"')
    print('})')
    
    print("\n🤔 POSSIBLE DIFFERENCES:")
    print("1. User-Agent string")
    print("2. HTTP headers")
    print("3. URL encoding")
    print("4. Session vs direct request")
    print("5. SSL/TLS configuration")
    print("6. Request ordering")
    print("7. API key format/encoding")


def main():
    """Main comparison function"""
    print("🔍 CURL vs PYTHON REQUESTS COMPARISON")
    print("=" * 60)
    print(f"API Key: {API_KEY}")
    print("=" * 60)
    
    # Test curl equivalent
    test_curl_equivalent()
    
    # Test different base URLs
    test_different_base_urls()
    
    # Test different parameters
    test_different_params()
    
    # Test authentication methods
    test_with_authentication()
    
    # Analyze differences
    analyze_curl_vs_python()
    
    print("\n" + "=" * 60)
    print("🎯 COMPARISON COMPLETE")
    print("=" * 60)
    print("If curl works but Python fails, the issue is likely:")
    print("1. User-Agent or headers difference")
    print("2. URL encoding difference")
    print("3. Session vs direct request")
    print("4. Rate limiting or IP blocking")


if __name__ == "__main__":
    main()
