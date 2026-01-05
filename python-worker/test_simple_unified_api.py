#!/usr/bin/env python3
"""
Test Simple Unified TQQQ API
Demonstrates how to use the unified engine API for specific dates
"""

import requests
import json
from datetime import datetime, timedelta

def test_unified_api():
    """Test the unified TQQQ API"""
    
    print("🧪 TESTING UNIFIED TQQQ SWING ENGINE API")
    print("=" * 50)
    
    base_url = "http://127.0.0.1:8001"
    
    # Test 1: Health check
    print("📋 Test 1: Health Check")
    print("-" * 30)
    
    try:
        response = requests.get(f"{base_url}/signal/unified-tqqq/health")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            health = response.json()
            print(f"✅ Engine Status: {health['status']}")
            print(f"📊 Engine: {health['engine']}")
            print(f"🔢 Version: {health['version']}")
            print(f"⏰ Timestamp: {health['timestamp']}")
            print(f"🎯 Features: {', '.join(health['features'])}")
        else:
            print(f"❌ Health check failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print()
    
    # Test 2: Latest signal
    print("📋 Test 2: Latest Signal")
    print("-" * 30)
    
    try:
        payload = {
            "symbol": "TQQQ"
            # No date specified = latest
        }
        
        response = requests.post(f"{base_url}/signal/unified-tqqq", json=payload)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            if data['success']:
                result = data['data']
                print(f"✅ Signal Generated Successfully!")
                print(f"📅 Date: {result['date']}")
                print(f"🎯 Signal: {result['signal']}")
                print(f"🎯 Confidence: {result['confidence_percent']}%")
                print(f"📋 Regime: {result['regime']}")
                print(f"💰 Price: ${result['market_data']['price']}")
                print(f"📊 RSI: {result['market_data']['rsi']}")
                print(f"📈 Trend: {result['technical_analysis']['trend']}")
                print()
                print("🧠 Engine Reasoning:")
                for i, reason in enumerate(result['reasoning'], 1):
                    print(f"  {i}. {reason}")
            else:
                print(f"❌ API Error: {data['error']}")
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print()
    
    # Test 3: Specific date signal
    print("📋 Test 3: Specific Date Signal (2025-08-22)")
    print("-" * 30)
    
    try:
        payload = {
            "symbol": "TQQQ",
            "date": "2025-08-22"
        }
        
        response = requests.post(f"{base_url}/signal/unified-tqqq", json=payload)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            if data['success']:
                result = data['data']
                print(f"✅ Signal Generated Successfully!")
                print(f"📅 Date: {result['date']}")
                print(f"🎯 Signal: {result['signal']}")
                print(f"🎯 Confidence: {result['confidence_percent']}%")
                print(f"📋 Regime: {result['regime']}")
                print(f"💰 Price: ${result['market_data']['price']}")
                print(f"📊 RSI: {result['market_data']['rsi']}")
                print(f"📈 Trend: {result['technical_analysis']['trend']}")
                print()
                print("🧠 Engine Reasoning:")
                for i, reason in enumerate(result['reasoning'], 1):
                    print(f"  {i}. {reason}")
                print()
                print("📊 Market Data:")
                market = result['market_data']
                print(f"  Price: ${market['price']}")
                print(f"  Daily Change: {market['recent_change']:+.2f}%")
                print(f"  Volume: {market['volume']:,}")
                print(f"  Volatility: {market['volatility']}%")
                print(f"  High: ${market['high']}")
                print(f"  Low: ${market['low']}")
                print()
                print("🔍 Technical Analysis:")
                tech = result['technical_analysis']
                print(f"  RSI Status: {tech['rsi_status']}")
                print(f"  Trend: {tech['trend']}")
                print(f"  Price vs SMA20: {tech['price_vs_sma20']}")
                print(f"  Price vs SMA50: {tech['price_vs_sma50']}")
            else:
                print(f"❌ API Error: {data['error']}")
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print()
    
    # Test 4: Multiple dates
    print("📋 Test 4: Multiple Date Analysis")
    print("-" * 30)
    
    test_dates = ["2025-08-20", "2025-08-21", "2025-08-22", "2025-08-25", "2025-08-26"]
    
    for date in test_dates:
        try:
            payload = {
                "symbol": "TQQQ",
                "date": date
            }
            
            response = requests.post(f"{base_url}/signal/unified-tqqq", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if data['success']:
                    result = data['data']
                    print(f"📅 {date}: {result['signal']} ({result['confidence_percent']}%) - {result['regime']}")
                else:
                    print(f"📅 {date}: ❌ {data['error']}")
            else:
                print(f"📅 {date}: ❌ HTTP {response.status_code}")
                
        except Exception as e:
            print(f"📅 {date}: ❌ Error: {e}")
    
    print()
    
    # Usage examples
    print("📚 USAGE EXAMPLES:")
    print("=" * 30)
    print()
    print("🔗 API Endpoint:")
    print("POST http://127.0.0.1:8001/signal/unified-tqqq")
    print()
    print("📋 Request Body (Latest):")
    print(json.dumps({"symbol": "TQQQ"}, indent=2))
    print()
    print("📋 Request Body (Specific Date):")
    print(json.dumps({"symbol": "TQQQ", "date": "2025-08-22"}, indent=2))
    print()
    print("📋 Response Format:")
    print(json.dumps({
        "success": True,
        "data": {
            "symbol": "TQQQ",
            "date": "2025-08-22",
            "signal": "BUY",
            "confidence": 0.75,
            "confidence_percent": 75,
            "regime": "Mean Reversion",
            "reasoning": ["Oversold stabilization", "RSI oversold: 37.0"],
            "market_data": {
                "price": 45.19,
                "rsi": 37.0,
                "sma20": 57.62,
                "sma50": 57.98,
                "volume": 132726400,
                "recent_change": 3.04,
                "volatility": 4.2
            }
        }
    }, indent=2))
    print()
    print("🎯 INTEGRATION WITH STREAMLIT:")
    print("-" * 30)
    print("```python")
    print("import requests")
    print()
    print("# Get signal for specific date")
    print("response = requests.post(")
    print("    'http://127.0.0.1:8001/signal/unified-tqqq',")
    print("    json={'symbol': 'TQQQ', 'date': '2025-08-22'}")
    print(")")
    print()
    print("if response.status_code == 200:")
    print("    data = response.json()")
    print("    if data['success']:")
    print("        signal = data['data']")
    print("        st.metric('Signal', signal['signal'])")
    print("        st.metric('Confidence', f\"{signal['confidence_percent']}%\")")
    print("        st.write('Reasoning:', signal['reasoning'])")
    print("```")

if __name__ == "__main__":
    test_unified_api()
