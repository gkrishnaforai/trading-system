#!/usr/bin/env python3
"""
Test FMP Technical Indicators API
Debug script to verify FMP API calls are working properly
"""

import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_fmp_api():
    """Test FMP technical indicators API directly"""
    
    print("🔍 TESTING FMP TECHNICAL INDICATORS API")
    print("=" * 60)
    
    try:
        from app.providers.financial_modeling_prep.client import FinancialModelingPrepClient
        from app.observability.logging import get_logger
        
        logger = get_logger("fmp_test")
        logger.setLevel("DEBUG")  # Enable debug logging
        
        print("✅ FMP Client imported successfully")
        
        # Create FMP client
        client = FinancialModelingPrepClient.from_settings()
        print("✅ FMP Client initialized")
        
        # Test symbols
        test_symbols = ["AAPL", "NVDA", "SMH"]
        
        for symbol in test_symbols:
            print(f"\n🔄 Testing {symbol}...")
            
            try:
                # Test a single indicator first
                print(f"📊 Testing EMA20 for {symbol}...")
                ema_data = client.get_technical_indicators_ema(symbol, 20, "1day")
                
                if ema_data:
                    print(f"✅ EMA20 SUCCESS: {len(ema_data)} data points")
                    print(f"   Sample: {ema_data[0] if ema_data else 'No data'}")
                else:
                    print(f"❌ EMA20 FAILED: No data returned")
                
                # Test all indicators
                print(f"📊 Testing ALL indicators for {symbol}...")
                all_indicators = client.get_all_technical_indicators(symbol, "1day")
                
                if all_indicators:
                    total_points = sum(len(data) for data in all_indicators.values())
                    successful_indicators = sum(1 for data in all_indicators.values() if data)
                    failed_indicators = sum(1 for data in all_indicators.values() if not data)
                    
                    print(f"✅ ALL INDICATORS SUCCESS:")
                    print(f"   Total data points: {total_points}")
                    print(f"   Successful indicators: {successful_indicators}")
                    print(f"   Failed indicators: {failed_indicators}")
                    
                    for indicator_name, data in all_indicators.items():
                        status = "✅" if data else "❌"
                        count = f"({len(data)} points)" if data else "(no data)"
                        print(f"   {status} {indicator_name}: {count}")
                else:
                    print(f"❌ ALL INDICATORS FAILED: No data returned")
                
            except Exception as e:
                print(f"❌ Error testing {symbol}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n🎯 FMP API TEST COMPLETED")
        print("Check the logs above for detailed API call information")
        
    except Exception as e:
        print(f"❌ Test setup failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fmp_api()
