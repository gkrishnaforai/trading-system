#!/usr/bin/env python3
"""
Simple Data Source Connectivity Test
Tests all available data sources to see which ones work and can fetch free stock data
"""
import sys
import logging
from datetime import datetime

# Configure logging to see clear messages
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_data_source(source_name, source):
    """Test a single data source for connectivity and data fetching"""
    print(f"\n=== Testing {source_name} ===")
    
    try:
        # Check availability
        available = source.is_available()
        print(f"Available: {'✅ Yes' if available else '❌ No'}")
        
        if not available:
            return False
        
        # Test fetching basic stock info (usually free)
        test_symbol = "AAPL"
        
        print(f"Testing data fetch for {test_symbol}...")
        
        # Try current price (usually free)
        try:
            price = source.fetch_current_price(test_symbol)
            if price:
                print(f"✅ Current Price: ${price}")
                return True
            else:
                print("⚠️ Current Price: None")
        except Exception as e:
            print(f"❌ Current Price failed: {str(e)[:60]}...")
        
        # Try price data (might be free)
        try:
            data = source.fetch_price_data(test_symbol, period="5d")
            if data is not None and not data.empty:
                print(f"✅ Price Data: {len(data)} rows")
                if 'close' in data.columns:
                    latest_close = data['close'].iloc[-1]
                    print(f"   Latest Close: ${latest_close}")
                return True
            else:
                print("⚠️ Price Data: Empty")
        except Exception as e:
            print(f"❌ Price Data failed: {str(e)[:60]}...")
        
        # Try fundamentals (might be paid)
        try:
            fundamentals = source.fetch_fundamentals(test_symbol)
            if fundamentals:
                print(f"✅ Fundamentals: {len(fundamentals)} fields")
                return True
            else:
                print("⚠️ Fundamentals: None")
        except Exception as e:
            print(f"❌ Fundamentals failed: {str(e)[:60]}...")
        
        return False
        
    except Exception as e:
        print(f"❌ Source test failed: {str(e)}")
        return False

def main():
    """Main test function"""
    print("🔍 Data Source Connectivity Test")
    print("=" * 50)
    print(f"Testing at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    working_sources = []
    failed_sources = []
    
    # Test using new adapter system
    print("\n📊 Testing New Adapter System")
    print("-" * 30)
    
    try:
        from app.data_sources.adapters import create_adapter, get_adapter_factory
        
        factory = get_adapter_factory()
        available_adapters = factory.list_enabled_adapters()
        print(f"Available adapters: {available_adapters}")
        
        for adapter_name in available_adapters:
            try:
                adapter = create_adapter(adapter_name)
                
                # Initialize with config
                config = {}
                if adapter_name == "massive":
                    from app.config import settings
                    config = {
                        'api_key': settings.massive_api_key,
                        'rate_limit_calls': settings.massive_rate_limit_calls,
                        'rate_limit_window': settings.massive_rate_limit_window
                    }
                elif adapter_name == "yahoo_finance":
                    config = {'timeout': 30, 'retry_count': 3}
                elif adapter_name == "fallback":
                    config = {'cache_enabled': True, 'cache_ttl': 3600}
                
                adapter.initialize(config)
                
                if test_data_source(f"{adapter_name} (Adapter)", adapter):
                    working_sources.append(f"{adapter_name} (adapter)")
                else:
                    failed_sources.append(f"{adapter_name} (adapter)")
                    
            except Exception as e:
                print(f"\n❌ {adapter_name} adapter failed: {str(e)[:80]}...")
                failed_sources.append(f"{adapter_name} (adapter)")
    
    except Exception as e:
        print(f"❌ Adapter system failed: {e}")
    
    # Test using legacy system
    print("\n📊 Testing Legacy System")
    print("-" * 30)
    
    try:
        from app.data_sources import get_data_source
        
        # Test individual sources
        test_sources = ['yahoo_finance', 'massive', 'fallback']
        
        for source_name in test_sources:
            try:
                source = get_data_source(source_name)
                if test_data_source(f"{source_name} (Legacy)", source):
                    working_sources.append(f"{source_name} (legacy)")
                else:
                    failed_sources.append(f"{source_name} (legacy)")
            except Exception as e:
                print(f"\n❌ {source_name} legacy failed: {str(e)[:80]}...")
                failed_sources.append(f"{source_name} (legacy)")
    
    except Exception as e:
        print(f"❌ Legacy system failed: {e}")
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 SUMMARY")
    print("=" * 50)
    
    if working_sources:
        print(f"✅ Working Sources ({len(working_sources)}):")
        for source in working_sources:
            print(f"   • {source}")
    else:
        print("❌ No working sources found!")
    
    if failed_sources:
        print(f"\n❌ Failed Sources ({len(failed_sources)}):")
        for source in failed_sources:
            print(f"   • {source}")
    
    print(f"\n🎯 Success Rate: {len(working_sources)}/{len(working_sources) + len(failed_sources)} sources working")
    
    if working_sources:
        print("\n🎉 At least one data source is working! You can fetch stock data.")
        return 0
    else:
        print("\n⚠️ No data sources are working. Check configuration or API keys.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
