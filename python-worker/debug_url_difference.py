#!/usr/bin/env python3
"""
Debug the exact URL difference between curl and Python
"""
import sys
import os
import requests
import urllib.parse

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

API_KEY = "4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ"


def debug_url_construction():
    """Debug how Python constructs the URL vs curl"""
    print("🔍 DEBUGGING URL CONSTRUCTION")
    print("=" * 60)
    
    # Manual URL construction (like curl)
    manual_url = "https://financialmodelingprep.com/stable/key-metrics?symbol=AAPL&period=quarter&apikey=4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ"
    print(f"\n📋 Manual URL (like curl):")
    print(f"   {manual_url}")
    
    # Python requests URL construction
    base_url = "https://financialmodelingprep.com/stable/key-metrics"
    params = {
        "symbol": "AAPL",
        "period": "quarter",
        "apikey": API_KEY
    }
    
    # Create session with headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    })
    
    # Create request to see the actual URL
    request = requests.Request('GET', base_url, params=params)
    prepared_request = session.prepare_request(request)
    
    print(f"\n📋 Python requests URL:")
    print(f"   {prepared_request.url}")
    
    # Compare URLs
    print(f"\n🔍 URL COMPARISON:")
    print(f"   Manual:  {manual_url}")
    print(f"   Python:  {prepared_request.url}")
    print(f"   Same:    {manual_url == prepared_request.url}")
    
    # Test both URLs
    print(f"\n📊 TESTING BOTH URLS:")
    
    # Test manual URL
    print(f"\n1️⃣ Testing Manual URL...")
    try:
        response = session.get(manual_url, timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ SUCCESS: {len(data)} records")
        else:
            print(f"   ❌ FAILED: {response.text[:100]}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    # Test Python constructed URL
    print(f"\n2️⃣ Testing Python URL...")
    try:
        response = session.get(prepared_request.url, timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ SUCCESS: {len(data)} records")
        else:
            print(f"   ❌ FAILED: {response.text[:100]}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")


def test_parameter_ordering():
    """Test different parameter orderings"""
    print(f"\n🔍 TESTING PARAMETER ORDERING")
    print("=" * 60)
    
    base_url = "https://financialmodelingprep.com/stable/key-metrics"
    
    # Different parameter orders
    param_orders = [
        # Original order
        {"symbol": "AAPL", "period": "quarter", "apikey": API_KEY},
        # API key first
        {"apikey": API_KEY, "symbol": "AAPL", "period": "quarter"},
        # Different order
        {"period": "quarter", "apikey": API_KEY, "symbol": "AAPL"},
        # Only symbol and API key (no period)
        {"symbol": "AAPL", "apikey": API_KEY},
    ]
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
    })
    
    for i, params in enumerate(param_orders):
        print(f"\n{i+1}️⃣ Testing order: {list(params.keys())}")
        
        # Create request to see URL
        request = requests.Request('GET', base_url, params=params)
        prepared = session.prepare_request(request)
        
        print(f"   URL: {prepared.url}")
        
        try:
            response = session.get(prepared.url, timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ SUCCESS: {len(data)} records")
                break
            elif response.status_code == 402:
                print(f"   ❌ PAYMENT REQUIRED")
            else:
                print(f"   ❌ FAILED: {response.text[:100]}")
                
        except Exception as e:
            print(f"   ❌ ERROR: {e}")


def test_url_encoding():
    """Test URL encoding differences"""
    print(f"\n🔍 TESTING URL ENCODING")
    print("=" * 60)
    
    # Test with and without encoding
    base_url = "https://financialmodelingprep.com/stable/key-metrics"
    
    # Method 1: Direct string concatenation
    url1 = f"{base_url}?symbol=AAPL&period=quarter&apikey={API_KEY}"
    
    # Method 2: URL encode parameters
    params = {
        "symbol": "AAPL",
        "period": "quarter",
        "apikey": API_KEY
    }
    encoded_params = urllib.parse.urlencode(params)
    url2 = f"{base_url}?{encoded_params}"
    
    # Method 3: Let requests handle it
    session = requests.Session()
    request = requests.Request('GET', base_url, params=params)
    prepared = session.prepare_request(request)
    url3 = prepared.url
    
    print(f"📋 URL ENCODING COMPARISON:")
    print(f"   Method 1 (direct): {url1}")
    print(f"   Method 2 (encoded): {url2}")
    print(f"   Method 3 (requests): {url3}")
    
    # Test all three
    urls_to_test = [
        ("Direct String", url1),
        ("URL Encoded", url2),
        ("Requests Library", url3),
    ]
    
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
    })
    
    for method_name, url in urls_to_test:
        print(f"\n📊 Testing {method_name}...")
        try:
            response = session.get(url, timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ SUCCESS: {len(data)} records")
                break
            elif response.status_code == 402:
                print(f"   ❌ PAYMENT REQUIRED")
            else:
                print(f"   ❌ FAILED: {response.text[:100]}")
                
        except Exception as e:
            print(f"   ❌ ERROR: {e}")


def test_with_working_endpoint():
    """Test with a working endpoint for comparison"""
    print(f"\n🔍 TESTING WITH WORKING ENDPOINT")
    print("=" * 60)
    
    # Test quote endpoint (works)
    quote_url = "https://financialmodelingprep.com/stable/quote"
    quote_params = {"symbol": "AAPL", "apikey": API_KEY}
    
    # Test key metrics endpoint (fails)
    metrics_url = "https://financialmodelingprep.com/stable/key-metrics"
    metrics_params = {"symbol": "AAPL", "period": "quarter", "apikey": API_KEY}
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
    })
    
    # Test quote
    print(f"\n1️⃣ Testing Quote (WORKING)...")
    quote_request = requests.Request('GET', quote_url, params=quote_params)
    quote_prepared = session.prepare_request(quote_request)
    
    print(f"   URL: {quote_prepared.url}")
    try:
        response = session.get(quote_prepared.url, timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ SUCCESS: {len(data)} records")
        else:
            print(f"   ❌ FAILED: {response.text[:100]}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    # Test metrics
    print(f"\n2️⃣ Testing Key Metrics (FAILING)...")
    metrics_request = requests.Request('GET', metrics_url, params=metrics_params)
    metrics_prepared = session.prepare_request(metrics_request)
    
    print(f"   URL: {metrics_prepared.url}")
    try:
        response = session.get(metrics_prepared.url, timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ SUCCESS: {len(data)} records")
        else:
            print(f"   ❌ FAILED: {response.text[:100]}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    # Compare headers
    print(f"\n🔍 HEADER COMPARISON:")
    print(f"   Quote Request Headers: {dict(quote_prepared.headers)}")
    print(f"   Metrics Request Headers: {dict(metrics_prepared.headers)}")
    print(f"   Headers Same: {dict(quote_prepared.headers) == dict(metrics_prepared.headers)}")


def main():
    """Main debug function"""
    print("🐛 DEBUGGING CURL VS PYTHON URL DIFFERENCE")
    print("=" * 60)
    print("This will help identify why curl works but Python fails")
    print("=" * 60)
    
    # Debug URL construction
    debug_url_construction()
    
    # Test parameter ordering
    test_parameter_ordering()
    
    # Test URL encoding
    test_url_encoding()
    
    # Test with working endpoint
    test_with_working_endpoint()
    
    print("\n" + "=" * 60)
    print("🎯 DEBUG COMPLETE")
    print("=" * 60)
    print("If we find a difference, we can fix the Python implementation!")


if __name__ == "__main__":
    main()
