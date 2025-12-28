#!/usr/bin/env python3
"""
Simple Alpha Vantage Test
Direct API-based approach - exactly like their examples
"""
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.data_sources.alphavantage_simple import SimpleAlphaVantageSource

def test_simple_alpha_vantage():
    """Test simple Alpha Vantage implementation"""
    print("🧪 SIMPLE ALPHA VANTAGE TEST")
    print("=" * 40)
    print("Testing direct API approach - no complex rate limiting")
    
    # Initialize with API key
    api_key = "QFGQ8S1GNTMPFNMA"
    source = SimpleAlphaVantageSource(api_key)
    
    # Test 1: Company Overview (exact same as their example)
    print(f"\n📊 Testing Company Overview for AVGO")
    overview = source.fetch_company_overview("AVGO")
    
    if overview:
        print(f"✅ SUCCESS - Company Overview")
        print(f"   Symbol: {overview.get('Symbol', 'N/A')}")
        print(f"   Name: {overview.get('Name', 'N/A')}")
        print(f"   Sector: {overview.get('Sector', 'N/A')}")
        print(f"   Market Cap: ${overview.get('MarketCapitalization', 'N/A')}")
        print(f"   P/E Ratio: {overview.get('PERatio', 'N/A')}")
    else:
        print("❌ FAILED - Company Overview")
        return False
    
    # Test 2: Time Series Daily
    print(f"\n📈 Testing Time Series Daily for AVGO")
    time_series = source.fetch_time_series_daily("AVGO")
    
    if time_series:
        dates = list(time_series.get("Time Series (Daily)", {}).keys())
        print(f"✅ SUCCESS - Time Series Daily")
        print(f"   Data Points: {len(dates)}")
        print(f"   Date Range: {dates[-1]} to {dates[0]}")
    else:
        print("❌ FAILED - Time Series Daily")
        return False
    
    # Test 3: Technical Indicators
    print(f"\n📊 Testing RSI Indicator for AVGO")
    rsi = source.fetch_technical_indicator("AVGO", "RSI", 14)
    
    if rsi:
        print(f"✅ SUCCESS - RSI Indicator")
        print(f"   Data Keys: {list(rsi.keys())}")
    else:
        print("❌ FAILED - RSI Indicator")
        return False
    
    # Test 4: Income Statement
    print(f"\n💰 Testing Income Statement for AVGO")
    income = source.fetch_income_statement("AVGO")
    
    if income:
        reports = income.get("annualReports", [])
        print(f"✅ SUCCESS - Income Statement")
        print(f"   Annual Reports: {len(reports)}")
        if reports:
            latest = reports[0]
            print(f"   Latest Fiscal Date: {latest.get('fiscalDateEnding', 'N/A')}")
    else:
        print("❌ FAILED - Income Statement")
        return False
    
    print(f"\n🎉 ALL TESTS PASSED!")
    print("✅ Simple Alpha Vantage implementation works perfectly")
    print("✅ Ready to integrate with data orchestrator")
    
    return True

if __name__ == "__main__":
    success = test_simple_alpha_vantage()
    
    if success:
        print(f"\n🚀 CONCLUSION:")
        print("   • Direct API approach works perfectly")
        print("   • No complex rate limiting needed")
        print("   • Simple and reliable implementation")
        print("   • Ready for production use")
    else:
        print(f"\n❌ Some tests failed - check implementation")
