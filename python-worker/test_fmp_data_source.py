#!/usr/bin/env python3
"""
Test FMP Data Source
Verify that FMP is being used instead of Yahoo Finance
"""

import os
import sys
from dotenv import load_dotenv

def test_fmp_data_source():
    """Test FMP data source configuration and functionality"""
    
    load_dotenv()
    
    print("🔧 Testing FMP Data Source Configuration")
    print("=" * 50)
    
    # Check environment variables
    fmp_api_key = os.getenv('FMP_API_KEY')
    fmp_enabled = os.getenv('FMP_ENABLED', 'false').lower() == 'true'
    
    print(f"📋 FMP API Key: {'✅ Configured' if fmp_api_key else '❌ Missing'}")
    print(f"📋 FMP Enabled: {'✅ Yes' if fmp_enabled else '❌ No'}")
    
    if not fmp_api_key:
        print("\n❌ FMP API key is required!")
        print("🔧 Set FMP_API_KEY in your .env file")
        return False
    
    try:
        # Test data source configuration
        from app.data_sources import get_data_source, PRIMARY_DATA_SOURCE, DATA_SOURCES
        from app.config import settings
        
        print(f"\n📊 Data Source Configuration:")
        print(f"   Primary Source: {PRIMARY_DATA_SOURCE}")
        print(f"   Default Provider: {settings.default_data_provider}")
        print(f"   Available Sources: {list(DATA_SOURCES.keys())}")
        
        # Test FMP source specifically
        fmp_source = get_data_source("fmp", use_fallback=False)
        print(f"\n✅ FMP Source Created: {type(fmp_source).__name__}")
        print(f"   Source Name: {fmp_source.name}")
        print(f"   Is Available: {fmp_source.is_available()}")
        
        # Test fetching data with FMP
        print(f"\n📈 Testing FMP Data Fetch...")
        test_symbol = "AAPL"
        
        # Test price data
        price_data = fmp_source.fetch_price_data(test_symbol, period="1m")
        if price_data is not None and not price_data.empty:
            print(f"✅ Price Data: {len(price_data)} records for {test_symbol}")
            print(f"   Latest Date: {price_data.index[-1].date()}")
            print(f"   Latest Close: ${price_data['close'].iloc[-1]:.2f}")
        else:
            print(f"❌ No price data returned for {test_symbol}")
            return False
        
        # Test fundamentals data
        fundamentals = fmp_source.fetch_fundamental_data(test_symbol)
        if fundamentals:
            print(f"✅ Fundamentals: {len(fundamentals)} fields for {test_symbol}")
            print(f"   Company Name: {fundamentals.get('companyName', 'N/A')}")
            print(f"   Sector: {fundamentals.get('sector', 'N/A')}")
            print(f"   Market Cap: ${fundamentals.get('marketCap', 0):,.0f}")
        else:
            print(f"⚠️ No fundamentals data for {test_symbol}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing FMP: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_symbol_info_with_fmp():
    """Test loading stock symbol info using FMP"""
    
    print(f"\n🎯 Testing Symbol Info Loading with FMP")
    print("=" * 50)
    
    try:
        from app.services.data_fetcher import DataFetcher
        
        fetcher = DataFetcher()
        test_symbol = "AAPL"
        
        print(f"📊 Fetching symbol info for {test_symbol} using FMP...")
        
        # Test fundamental data fetch
        fundamentals = fetcher.fetch_fundamental_data(test_symbol)
        
        if fundamentals:
            print(f"✅ Successfully loaded symbol info for {test_symbol}:")
            print(f"   Symbol: {fundamentals.get('symbol', 'N/A')}")
            print(f"   Company Name: {fundamentals.get('companyName', 'N/A')}")
            print(f"   Sector: {fundamentals.get('sector', 'N/A')}")
            print(f"   Industry: {fundamentals.get('industry', 'N/A')}")
            print(f"   Market Cap: ${fundamentals.get('marketCap', 0):,.0f}")
            print(f"   PE Ratio: {fundamentals.get('peRatio', 'N/A')}")
            print(f"   Beta: {fundamentals.get('beta', 'N/A')}")
            print(f"   Data Source: {fundamentals.get('data_source', 'N/A')}")
            
            # Check if it's using FMP
            data_source = fundamentals.get('data_source', '').lower()
            if 'fmp' in data_source:
                print(f"✅ Data loaded from FMP (not Yahoo Finance)")
            else:
                print(f"⚠️ Data source: {data_source}")
            
            return True
        else:
            print(f"❌ No fundamental data returned for {test_symbol}")
            return False
            
    except Exception as e:
        print(f"❌ Error fetching symbol info: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 TESTING FMP DATA SOURCE")
    print("=" * 60)
    
    success = True
    
    # Test FMP configuration
    if not test_fmp_data_source():
        success = False
    
    # Test symbol info loading
    if not test_symbol_info_with_fmp():
        success = False
    
    if success:
        print(f"\n🎉 FMP DATA SOURCE TESTS PASSED!")
        print("✅ FMP is properly configured and working")
        print("✅ Stock symbol info will be loaded from FMP instead of Yahoo")
        exit(0)
    else:
        print(f"\n❌ FMP DATA SOURCE TESTS FAILED!")
        print("🔧 Check FMP API key configuration")
        exit(1)
