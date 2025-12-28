#!/usr/bin/env python3
"""
Debug Alpha Vantage Income Statement
See what the actual response structure looks like
"""
import requests
import json

def debug_income_statement():
    """Debug income statement response"""
    print("🔍 DEBUGGING INCOME STATEMENT RESPONSE")
    print("=" * 50)
    
    api_key = "QFGQ8S1GNTMPFNMA"
    symbol = "AVGO"
    
    url = f'https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol={symbol}&apikey={api_key}'
    
    print(f"📡 Requesting: {url.replace(api_key, '***')}")
    
    try:
        r = requests.get(url)
        print(f"✅ Status Code: {r.status_code}")
        
        data = r.json()
        print(f"📊 Response Keys: {list(data.keys())}")
        print(f"📊 Full Response:")
        print(json.dumps(data, indent=2))
        
        # Check different possible structures
        if "annualReports" in data:
            print(f"\n✅ Found annualReports: {len(data['annualReports'])} reports")
        elif "quarterlyReports" in data:
            print(f"\n✅ Found quarterlyReports: {len(data['quarterlyReports'])} reports")
        elif "Symbol" in data:
            print(f"\n✅ Found Symbol: {data['Symbol']}")
        else:
            print(f"\n❌ No expected structure found")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    debug_income_statement()
