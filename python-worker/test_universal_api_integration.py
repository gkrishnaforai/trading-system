#!/usr/bin/env python3
"""
Integration Test for Universal Backtest API
Tests all endpoints with proper error handling and validation
"""

import requests
import json
import time
from datetime import datetime, timedelta
import os

def test_universal_api_integration():
    """Comprehensive integration test for universal API"""
    
    base_url = "http://127.0.0.1:8001"
    
    print("🧪 Universal API Integration Test")
    print("=" * 60)
    
    # Test 1: Health Check
    print("1. Testing Health Check...")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health Check: {data['status']}")
            assert data['status'] == 'healthy', "Health check failed"
        else:
            print(f"❌ Health Check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health Check error: {e}")
        return False
    
    # Test 2: Supported Assets
    print("\n2. Testing Supported Assets...")
    try:
        response = requests.get(f"{base_url}/api/v1/universal/assets/supported", timeout=10)
        if response.status_code == 200:
            data = response.json()
            assets = data['data']['supported_assets']
            print(f"✅ Supported Assets: {list(assets.keys())}")
            assert '3x_etf' in assets, "3x_etf not supported"
            assert 'regular_etf' in assets, "regular_etf not supported"
            assert 'stock' in assets, "stock not supported"
        else:
            print(f"❌ Supported Assets failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Supported Assets error: {e}")
        return False
    
    # Test 3: Data Availability for QQQ
    print("\n3. Testing Data Availability for QQQ...")
    try:
        response = requests.get(f"{base_url}/api/v1/universal/data/availability/QQQ", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['data']['available']:
                print(f"✅ QQQ Data Available: {data['data']['total_records']} records")
                assert data['data']['total_records'] > 0, "No records found"
            else:
                print("⚠️ QQQ Data Not Available - may need to load data")
        else:
            print(f"❌ Data Availability failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Data Availability error: {e}")
        return False
    
    # Test 4: Historical Data for QQQ
    print("\n4. Testing Historical Data for QQQ...")
    try:
        response = requests.get(f"{base_url}/api/v1/universal/historical-data/QQQ?limit=5", timeout=10)
        if response.status_code == 200:
            data = response.json()
            records = data['data']['historical_data']
            print(f"✅ Historical Data: Retrieved {len(records)} records")
            if records:
                print(f"   Latest: {records[-1]['date']} - Close: ${records[-1]['close']}")
                assert 'close' in records[-1], "Missing close price"
                assert 'date' in records[-1], "Missing date"
        else:
            print(f"❌ Historical Data failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Historical Data error: {e}")
        return False
    
    # Test 5: Signal Generation for 3x ETF (TQQQ)
    print("\n5. Testing Signal Generation for TQQQ (3x ETF)...")
    try:
        payload = {
            "symbol": "TQQQ",
            "date": "2025-01-10",  # Use a recent date that should have data
            "asset_type": "3x_etf"
        }
        response = requests.post(f"{base_url}/api/v1/universal/signal/universal", json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            signal = data['data']['signal']['signal']
            confidence = data['data']['signal']['confidence']
            print(f"✅ TQQQ Signal: {signal.upper()} (Confidence: {confidence:.1%})")
            assert signal in ['buy', 'sell', 'hold'], f"Invalid signal: {signal}"
            assert 0 <= confidence <= 1, f"Invalid confidence: {confidence}"
        else:
            print(f"❌ Signal Generation failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Signal Generation error: {e}")
        return False
    
    # Test 6: Signal Generation for Regular ETF (QQQ)
    print("\n6. Testing Signal Generation for QQQ (Regular ETF)...")
    try:
        payload = {
            "symbol": "QQQ",
            "date": "2025-01-10",
            "asset_type": "regular_etf"
        }
        response = requests.post(f"{base_url}/api/v1/universal/signal/universal", json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            signal = data['data']['signal']['signal']
            confidence = data['data']['signal']['confidence']
            print(f"✅ QQQ Signal: {signal.upper()} (Confidence: {confidence:.1%})")
            assert signal in ['buy', 'sell', 'hold'], f"Invalid signal: {signal}"
            assert 0 <= confidence <= 1, f"Invalid confidence: {confidence}"
        else:
            print(f"❌ Signal Generation failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Signal Generation error: {e}")
        return False
    
    # Test 7: Signal Generation for Stock (NVDA)
    print("\n7. Testing Signal Generation for NVDA (Stock)...")
    try:
        payload = {
            "symbol": "NVDA",
            "date": "2025-01-10",
            "asset_type": "stock"
        }
        response = requests.post(f"{base_url}/api/v1/universal/signal/universal", json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            signal = data['data']['signal']['signal']
            confidence = data['data']['signal']['confidence']
            print(f"✅ NVDA Signal: {signal.upper()} (Confidence: {confidence:.1%})")
            assert signal in ['buy', 'sell', 'hold'], f"Invalid signal: {signal}"
            assert 0 <= confidence <= 1, f"Invalid confidence: {confidence}"
        else:
            print(f"❌ Signal Generation failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Signal Generation error: {e}")
        return False
    
    # Test 8: Test Fear/Greed Integration
    print("\n8. Testing Fear/Greed Integration...")
    try:
        payload = {
            "symbol": "TQQQ",
            "date": "2025-01-10",
            "asset_type": "3x_etf"
        }
        response = requests.post(f"{base_url}/api/v1/universal/signal/universal", json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            metadata = data['data']['signal']['metadata']
            
            # Check Fear/Greed specific fields
            assert 'fear_greed_state' in metadata, "Missing fear_greed_state"
            assert 'fear_greed_bias' in metadata, "Missing fear_greed_bias"
            assert 'recovery_detected' in metadata, "Missing recovery_detected"
            
            fg_state = metadata['fear_greed_state']
            fg_bias = metadata['fear_greed_bias']
            recovery = metadata['recovery_detected']
            
            print(f"✅ Fear/Greed Integration: {fg_state} | {fg_bias} | Recovery: {recovery}")
            assert fg_state in ['extreme_fear', 'fear', 'neutral', 'greed', 'extreme_greed'], f"Invalid fear_greed_state: {fg_state}"
            assert isinstance(recovery, bool), f"recovery_detected should be boolean: {recovery}"
        else:
            print(f"❌ Fear/Greed test failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Fear/Greed test error: {e}")
        return False
    
    # Test 9: Test Invalid Date
    print("\n9. Testing Invalid Date Handling...")
    try:
        payload = {
            "symbol": "TQQQ",
            "date": "2025-13-45",  # Invalid date
            "asset_type": "3x_etf"
        }
        response = requests.post(f"{base_url}/api/v1/universal/signal/universal", json=payload, timeout=30)
        if response.status_code >= 400:
            print(f"✅ Invalid Date Properly Rejected: {response.status_code}")
        else:
            print(f"❌ Invalid Date Not Rejected: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Invalid Date test error: {e}")
        return False
    
    # Test 10: Test Invalid Symbol
    print("\n10. Testing Invalid Symbol Handling...")
    try:
        payload = {
            "symbol": "INVALID123",
            "date": "2025-01-10",
            "asset_type": "3x_etf"
        }
        response = requests.post(f"{base_url}/api/v1/universal/signal/universal", json=payload, timeout=30)
        if response.status_code >= 400:
            print(f"✅ Invalid Symbol Properly Rejected: {response.status_code}")
        else:
            print(f"❌ Invalid Symbol Not Rejected: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Invalid Symbol test error: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("🎉 All Universal API Integration Tests Passed!")
    print("📖 Documentation: http://localhost:8001/docs")
    print("🔗 Universal Endpoints: http://localhost:8001/api/v1/universal/")
    
    return True

def test_streamlit_compatibility():
    """Test that API responses are compatible with Streamlit dashboards"""
    
    base_url = "http://127.0.0.1:8001"
    
    print("\n🔄 Testing Streamlit Compatibility...")
    print("-" * 40)
    
    try:
        # Test signal generation with full response structure
        payload = {
            "symbol": "TQQQ",
            "date": "2025-01-10",
            "asset_type": "3x_etf"
        }
        response = requests.post(f"{base_url}/api/v1/universal/signal/universal", json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            # Check required fields for Streamlit
            required_fields = [
                'engine', 'market_data', 'signal', 'analysis', 'timestamp'
            ]
            
            for field in required_fields:
                assert field in data['data'], f"Missing required field: {field}"
            
            # Check signal structure
            signal_fields = ['signal', 'confidence', 'reasoning', 'metadata']
            for field in signal_fields:
                assert field in data['data']['signal'], f"Missing signal field: {field}"
            
            # Check market data structure
            market_fields = ['symbol', 'date', 'price', 'rsi', 'sma_20', 'sma_50']
            for field in market_fields:
                assert field in data['data']['market_data'], f"Missing market field: {field}"
            
            print("✅ Streamlit Compatibility: All required fields present")
            return True
        else:
            print(f"❌ Streamlit Compatibility test failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Streamlit Compatibility error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting Universal API Integration Tests")
    print("⏰ Started at:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    # Run integration tests
    success = test_universal_api_integration()
    
    if success:
        # Run Streamlit compatibility tests
        streamlit_success = test_streamlit_compatibility()
        
        if streamlit_success:
            print("\n🎉 ALL TESTS PASSED!")
            print("✅ Universal API is ready for production use")
            print("✅ Streamlit dashboards should work correctly")
        else:
            print("\n⚠️ Integration tests passed but Streamlit compatibility failed")
    else:
        print("\n❌ INTEGRATION TESTS FAILED!")
        print("🔧 Please fix the issues before using in production")
    
    print("⏰ Completed at:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
