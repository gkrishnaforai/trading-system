#!/usr/bin/env python3
"""
Test Alpha Vantage with Proper Rate Limiting
Respects the 5 calls/minute limit for free tier
"""
import sys
import os
import time

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.data_orchestrator import data_orchestrator

def test_with_rate_limit():
    """Test with proper rate limiting"""
    print("🐌 TESTING WITH RATE LIMIT RESPECT")
    print("=" * 50)
    print("Alpha Vantage Free Tier: 5 calls per minute")
    print("Adding 15-second delays between calls...")
    
    symbol = "AVGO"
    
    # Test 1: Company Overview
    print(f"\n📊 Testing Company Overview for {symbol}")
    overview = data_orchestrator.fetch_alphavantage_simple("company_overview", symbol)
    
    if overview:
        print(f"✅ SUCCESS - Company Overview")
        print(f"   Symbol: {overview.get('Symbol', 'N/A')}")
        print(f"   Name: {overview.get('Name', 'N/A')}")
        print(f"   Market Cap: ${overview.get('MarketCapitalization', 'N/A')}")
    else:
        print("❌ FAILED - Company Overview")
        return False
    
    # Wait to respect rate limit
    print(f"\n⏳ Waiting 15 seconds to respect rate limit...")
    time.sleep(15)
    
    # Test 2: Income Statement
    print(f"\n💰 Testing Income Statement for {symbol}")
    income = data_orchestrator.fetch_alphavantage_simple("income_statement", symbol)
    
    if income:
        reports = income.get("annualReports", [])
        print(f"✅ SUCCESS - Income Statement")
        print(f"   Annual Reports: {len(reports)}")
        if reports:
            latest = reports[0]
            print(f"   Latest Fiscal Date: {latest.get('fiscalDateEnding', 'N/A')}")
            print(f"   Total Revenue: ${latest.get('totalRevenue', 'N/A')}")
    else:
        print("❌ FAILED - Income Statement")
        return False
    
    # Wait to respect rate limit
    print(f"\n⏳ Waiting 15 seconds to respect rate limit...")
    time.sleep(15)
    
    # Test 3: Balance Sheet
    print(f"\n🏦 Testing Balance Sheet for {symbol}")
    balance_sheet = data_orchestrator.fetch_alphavantage_simple("balance_sheet", symbol)
    
    if balance_sheet:
        reports = balance_sheet.get("annualReports", [])
        print(f"✅ SUCCESS - Balance Sheet")
        print(f"   Annual Reports: {len(reports)}")
        if reports:
            latest = reports[0]
            print(f"   Latest Fiscal Date: {latest.get('fiscalDateEnding', 'N/A')}")
    else:
        print("❌ FAILED - Balance Sheet")
        return False
    
    print(f"\n🎉 ALL TESTS PASSED WITH RATE LIMITING!")
    print("✅ Alpha Vantage integration working perfectly")
    print("✅ Ready for production with proper rate management")
    
    return True

def test_single_call_verification():
    """Test a single call to verify API works"""
    print(f"\n🔍 SINGLE CALL VERIFICATION")
    print("=" * 30)
    
    symbol = "AAPL"  # Use different symbol to avoid any caching
    
    print(f"📊 Testing single overview call for {symbol}")
    overview = data_orchestrator.fetch_alphavantage_simple("company_overview", symbol)
    
    if overview:
        print(f"✅ Single call works perfectly")
        print(f"   Symbol: {overview.get('Symbol', 'N/A')}")
        print(f"   Name: {overview.get('Name', 'N/A')}")
        print(f"   Sector: {overview.get('Sector', 'N/A')}")
        return True
    else:
        print("❌ Single call failed")
        return False

def main():
    """Main test function"""
    print("🚀 ALPHA VANTAGE RATE LIMIT AWARE TESTING")
    print("=" * 60)
    
    # First verify single call works
    if not test_single_call_verification():
        print("❌ Basic API call failed - check configuration")
        return False
    
    # Then test with rate limiting
    success = test_with_rate_limit()
    
    if success:
        print(f"\n🎯 FINAL RESULT: SUCCESS!")
        print(f"✅ Alpha Vantage integration is working")
        print(f"✅ Rate limiting properly handled")
        print(f"✅ All data types accessible")
        print(f"✅ Ready for production use")
        
        print(f"\n📋 PRODUCTION GUIDELINES:")
        print(f"   • Rate limit: 5 calls per minute (free tier)")
        print(f"   • Use delays between consecutive calls")
        print(f"   • Consider upgrading to premium for higher limits")
        print(f"   • Cache data to minimize API calls")
        
    else:
        print(f"\n❌ TESTS FAILED")
        print(f"   Check API key and rate limiting")
    
    return success

if __name__ == "__main__":
    main()
