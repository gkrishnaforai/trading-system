#!/usr/bin/env python3
"""
Test script for Universal Backtest API
Verifies all endpoints work correctly
"""

import requests
import json
import time
from datetime import datetime, timedelta

def test_universal_api():
    """Test all universal API endpoints"""
    
    base_url = "http://127.0.0.1:8001"
    
    print("🧪 Testing Universal Backtest API")
    print("=" * 50)
    
    # Test 1: Health Check
    print("1. Testing Health Check...")
    try:
        response = requests.get(f"{base_url}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health Check: {data['status']}")
        else:
            print(f"❌ Health Check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health Check error: {e}")
        return False
    
    # Test 2: Supported Assets
    print("\n2. Testing Supported Assets...")
    try:
        response = requests.get(f"{base_url}/api/v1/universal/assets/supported")
        if response.status_code == 200:
            data = response.json()
            assets = data['data']['supported_assets']
            print(f"✅ Supported Assets: {list(assets.keys())}")
        else:
            print(f"❌ Supported Assets failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Supported Assets error: {e}")
    
    # Test 3: Data Availability for QQQ
    print("\n3. Testing Data Availability for QQQ...")
    try:
        response = requests.get(f"{base_url}/api/v1/universal/data/availability/QQQ")
        if response.status_code == 200:
            data = response.json()
            if data['data']['available']:
                print(f"✅ QQQ Data Available: {data['data']['total_records']} records")
            else:
                print("❌ QQQ Data Not Available")
        else:
            print(f"❌ Data Availability failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Data Availability error: {e}")
    
    # Test 4: Historical Data for QQQ
    print("\n4. Testing Historical Data for QQQ...")
    try:
        response = requests.get(f"{base_url}/api/v1/universal/historical-data/QQQ?limit=5")
        if response.status_code == 200:
            data = response.json()
            records = data['data']['historical_data']
            print(f"✅ Historical Data: Retrieved {len(records)} records")
            if records:
                print(f"   Latest: {records[-1]['date']} - Close: ${records[-1]['close']}")
        else:
            print(f"❌ Historical Data failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Historical Data error: {e}")
    
    # Test 5: Signal Generation for 3x ETF (TQQQ)
    print("\n5. Testing Signal Generation for TQQQ (3x ETF)...")
    try:
        payload = {
            "symbol": "TQQQ",
            "date": "2025-05-19",
            "asset_type": "3x_etf"
        }
        response = requests.post(f"{base_url}/api/v1/universal/signal/universal", json=payload)
        if response.status_code == 200:
            data = response.json()
            signal = data['data']['signal']['signal']
            confidence = data['data']['signal']['confidence']
            print(f"✅ TQQQ Signal: {signal.upper()} (Confidence: {confidence:.1%})")
        else:
            print(f"❌ Signal Generation failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Signal Generation error: {e}")
    
    # Test 6: Signal Generation for Regular ETF (QQQ)
    print("\n6. Testing Signal Generation for QQQ (Regular ETF)...")
    try:
        payload = {
            "symbol": "QQQ",
            "date": "2025-05-19",
            "asset_type": "regular_etf"
        }
        response = requests.post(f"{base_url}/api/v1/universal/signal/universal", json=payload)
        if response.status_code == 200:
            data = response.json()
            signal = data['data']['signal']['signal']
            confidence = data['data']['signal']['confidence']
            print(f"✅ QQQ Signal: {signal.upper()} (Confidence: {confidence:.1%})")
        else:
            print(f"❌ Signal Generation failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Signal Generation error: {e}")
    
    # Test 7: Signal Generation for Stock (NVDA)
    print("\n7. Testing Signal Generation for NVDA (Stock)...")
    try:
        payload = {
            "symbol": "NVDA",
            "date": "2025-05-19",
            "asset_type": "stock"
        }
        response = requests.post(f"{base_url}/api/v1/universal/signal/universal", json=payload)
        if response.status_code == 200:
            data = response.json()
            signal = data['data']['signal']['signal']
            confidence = data['data']['signal']['confidence']
            print(f"✅ NVDA Signal: {signal.upper()} (Confidence: {confidence:.1%})")
        else:
            print(f"❌ Signal Generation failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Signal Generation error: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Universal API Testing Complete!")
    print("📖 Documentation: http://localhost:8001/docs")
    
    return True

if __name__ == "__main__":
    test_universal_api()
