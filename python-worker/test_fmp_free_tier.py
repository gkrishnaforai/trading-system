#!/usr/bin/env python3
"""
FMP Free Tier API Test
Tests only the free endpoints that work with your API key
"""
import sys
import os
import requests
from datetime import datetime

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

API_KEY = "4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ"
BASE_URL = "https://financialmodelingprep.com/stable"


class FMPFreeTierTester:
    """Test only free-tier FMP endpoints"""
    
    def __init__(self):
        self.api_key = API_KEY
        self.base_url = BASE_URL
        self.test_symbol = "AAPL"
    
    def test_endpoint(self, endpoint: str, params: dict = None) -> dict:
        """Test a single endpoint"""
        try:
            url = f"{self.base_url}{endpoint}"
            if params is None:
                params = {}
            params["apikey"] = self.api_key
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": data,
                    "message": "✅ SUCCESS"
                }
            elif response.status_code == 402:
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "data": None,
                    "message": "❌ PREMIUM ENDPOINT (Payment Required)"
                }
            else:
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "data": None,
                    "message": f"❌ ERROR: {response.status_code}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "status_code": 0,
                "data": None,
                "message": f"❌ EXCEPTION: {str(e)}"
            }
    
    def test_all_endpoints(self):
        """Test all FMP endpoints and categorize by tier"""
        print("🔍 TESTING FMP API ENDPOINTS")
        print("=" * 60)
        print(f"API Key: {self.api_key}")
        print(f"Test Symbol: {self.test_symbol}")
        print("=" * 60)
        
        # Test endpoints
        endpoints = [
            # FREE ENDPOINTS
            ("/quote", {"symbol": self.test_symbol}, "Real-time Price"),
            ("/profile", {"symbol": self.test_symbol}, "Company Profile"),
            ("/stock-list", {}, "Stock List"),
            ("/search-name", {"query": "apple", "limit": 5}, "Symbol Search"),
            ("/historical-price-eod/full", {"symbol": self.test_symbol}, "Historical Prices"),
            ("/income-statement", {"symbol": self.test_symbol, "period": "quarter"}, "Income Statement"),
            ("/balance-sheet-statement", {"symbol": self.test_symbol, "period": "quarter"}, "Balance Sheet"),
            ("/cash-flow-statement", {"symbol": self.test_symbol, "period": "quarter"}, "Cash Flow"),
            
            # PREMIUM ENDPOINTS
            ("/key-metrics", {"symbol": self.test_symbol, "period": "quarter"}, "Key Metrics"),
            ("/ratios", {"symbol": self.test_symbol, "period": "quarter"}, "Financial Ratios"),
            ("/financial-scores", {"symbol": self.test_symbol}, "Financial Scores"),
            ("/ratings-snapshot", {"symbol": self.test_symbol}, "Ratings Snapshot"),
            ("/grades", {"symbol": self.test_symbol}, "Stock Grades"),
            ("/price-target-consensus", {"symbol": self.test_symbol}, "Price Targets"),
            ("/analyst-estimates", {"symbol": self.test_symbol}, "Analyst Estimates"),
            ("/earning-call-transcript-latest", {}, "Latest Earnings Transcripts"),
            ("/news/stock-latest", {"page": 0, "limit": 5}, "Stock News"),
            ("/earnings-calendar", {}, "Earnings Calendar"),
        ]
        
        free_endpoints = []
        premium_endpoints = []
        failed_endpoints = []
        
        for endpoint, params, description in endpoints:
            print(f"\n📊 Testing: {description}")
            print(f"   URL: {endpoint}")
            
            result = self.test_endpoint(endpoint, params)
            print(f"   Result: {result['message']}")
            
            if result["success"]:
                free_endpoints.append({
                    "endpoint": endpoint,
                    "params": params,
                    "description": description,
                    "data_sample": result["data"][:2] if isinstance(result["data"], list) else result["data"]
                })
                if isinstance(result["data"], list):
                    print(f"   Data: {len(result['data'])} records")
                else:
                    print(f"   Data: Available ✅")
            elif result["status_code"] == 402:
                premium_endpoints.append({
                    "endpoint": endpoint,
                    "params": params,
                    "description": description
                })
                print(f"   Status: PREMIUM TIER REQUIRED")
            else:
                failed_endpoints.append({
                    "endpoint": endpoint,
                    "params": params,
                    "description": description,
                    "error": result["message"]
                })
                print(f"   Status: FAILED")
        
        # Summary
        print("\n" + "=" * 60)
        print("📋 SUMMARY")
        print("=" * 60)
        
        print(f"\n✅ FREE ENDPOINTS ({len(free_endpoints)}):")
        for endpoint in free_endpoints:
            print(f"   • {endpoint['description']} - {endpoint['endpoint']}")
        
        print(f"\n💰 PREMIUM ENDPOINTS ({len(premium_endpoints)}):")
        for endpoint in premium_endpoints:
            print(f"   • {endpoint['description']} - {endpoint['endpoint']}")
        
        print(f"\n❌ FAILED ENDPOINTS ({len(failed_endpoints)}):")
        for endpoint in failed_endpoints:
            print(f"   • {endpoint['description']} - {endpoint['error']}")
        
        # Recommendations
        print(f"\n🎯 RECOMMENDATIONS:")
        print(f"   • Your API key works with {len(free_endpoints)} free endpoints")
        print(f"   • Upgrade to premium for {len(premium_endpoints)} additional endpoints")
        print(f"   • Focus on free endpoints for current development")
        
        return {
            "free_endpoints": free_endpoints,
            "premium_endpoints": premium_endpoints,
            "failed_endpoints": failed_endpoints
        }
    
    def test_basic_functionality(self):
        """Test basic functionality with free endpoints"""
        print("\n🚀 TESTING BASIC FUNCTIONALITY")
        print("=" * 40)
        
        # Test 1: Real-time price
        print("\n1️⃣ Testing Real-time Price...")
        price_result = self.test_endpoint("/quote", {"symbol": self.test_symbol})
        if price_result["success"]:
            price_data = price_result["data"][0]
            print(f"   ✅ {self.test_symbol} Price: ${price_data['price']}")
            print(f"   ✅ Change: {price_data['change']} ({price_data['changePercentage']}%)")
        else:
            print(f"   ❌ Failed: {price_result['message']}")
        
        # Test 2: Company profile
        print("\n2️⃣ Testing Company Profile...")
        profile_result = self.test_endpoint("/profile", {"symbol": self.test_symbol})
        if profile_result["success"]:
            profile_data = profile_result["data"][0]
            print(f"   ✅ Company: {profile_data['companyName']}")
            print(f"   ✅ Sector: {profile_data['sector']}")
            print(f"   ✅ Market Cap: ${profile_data['marketCap']:,}")
        else:
            print(f"   ❌ Failed: {profile_result['message']}")
        
        # Test 3: Historical prices
        print("\n3️⃣ Testing Historical Prices...")
        hist_result = self.test_endpoint("/historical-price-eod/full", {"symbol": self.test_symbol})
        if hist_result["success"]:
            hist_data = hist_result["data"]
            print(f"   ✅ Historical records: {len(hist_data['historical'])}")
            if hist_data["historical"]:
                latest = hist_data["historical"][0]
                print(f"   ✅ Latest: ${latest['close']} on {latest['date']}")
        else:
            print(f"   ❌ Failed: {hist_result['message']}")
        
        # Test 4: Income statement
        print("\n4️⃣ Testing Income Statement...")
        income_result = self.test_endpoint("/income-statement", {"symbol": self.test_symbol, "period": "quarter"})
        if income_result["success"]:
            income_data = income_result["data"]
            print(f"   ✅ Income statements: {len(income_data)}")
            if income_data:
                latest = income_data[0]
                print(f"   ✅ Latest Revenue: ${latest.get('revenue', 'N/A'):,}")
                print(f"   ✅ Latest Net Income: ${latest.get('netIncome', 'N/A'):,}")
        else:
            print(f"   ❌ Failed: {income_result['message']}")
        
        # Test 5: Symbol search
        print("\n5️⃣ Testing Symbol Search...")
        search_result = self.test_endpoint("/search-name", {"query": "apple", "limit": 3})
        if search_result["success"]:
            search_data = search_result["data"]
            print(f"   ✅ Search results: {len(search_data)}")
            for result in search_data[:2]:
                print(f"   ✅ {result['name']} ({result['symbol']})")
        else:
            print(f"   ❌ Failed: {search_result['message']}")


def main():
    """Main test runner"""
    tester = FMPFreeTierTester()
    
    # Test all endpoints
    results = tester.test_all_endpoints()
    
    # Test basic functionality
    tester.test_basic_functionality()
    
    # Final recommendation
    print(f"\n🎉 CONCLUSION:")
    free_count = len(results["free_endpoints"])
    premium_count = len(results["premium_endpoints"])
    
    if free_count > 0:
        print(f"   ✅ Your API key is VALID and works with {free_count} free endpoints")
        print(f"   ✅ You can build a solid trading system with free endpoints")
        print(f"   💰 Consider upgrading to premium for {premium_count} additional features")
        
        print(f"\n📚 NEXT STEPS:")
        print(f"   1. Use free endpoints for core functionality")
        print(f"   2. Implement caching to reduce API calls")
        print(f"   3. Upgrade to premium when you need advanced analytics")
        
        return 0
    else:
        print(f"   ❌ Your API key doesn't work with any endpoints")
        print(f"   🔧 Check your API key or subscription status")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
