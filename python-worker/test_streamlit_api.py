#!/usr/bin/env python3
"""
Test Streamlit API for TQQQ Signal Engine
Shows how to use the API in Streamlit applications
"""

import requests
import json

def test_streamlit_api():
    """Test the Streamlit API endpoint"""
    
    print("🧪 TESTING STREAMLIT API FOR TQQQ SIGNAL ENGINE")
    print("=" * 60)
    
    # API endpoint
    url = "http://127.0.0.1:8001/api/streamlit/signal-analysis"
    
    # Test payload
    payload = {
        "symbol": "TQQQ",
        "date": None,  # Latest data
        "include_historical": True,
        "include_performance": True
    }
    
    print(f"📡 API Endpoint: {url}")
    print(f"📋 Payload: {json.dumps(payload, indent=2)}")
    print()
    
    try:
        print("🔄 Making API request...")
        response = requests.post(url, json=payload)
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('success'):
                print("✅ API call successful!")
                print()
                
                # Show key data sections
                result_data = data['data']
                
                print("🎯 SIGNAL SUMMARY:")
                print("-" * 30)
                signal = result_data['signal_summary']
                print(f"  Signal: {signal['signal']}")
                print(f"  Confidence: {signal['confidence_percent']}%")
                print(f"  Price: ${signal['price']}")
                print(f"  Regime: {signal['regime']}")
                print()
                
                print("📈 MARKET OVERVIEW:")
                print("-" * 30)
                market = result_data['market_overview']
                print(f"  Price: ${market['price']}")
                print(f"  Daily Change: {market['daily_change_percent']}")
                print(f"  Volume: {market['volume_formatted']}")
                print(f"  Volatility: {market['volatility']}% ({market['volatility_status']})")
                print()
                
                print("📊 TECHNICAL INDICATORS:")
                print("-" * 30)
                tech = result_data['technical_indicators']
                print(f"  RSI: {tech['rsi']} ({tech['rsi_status']})")
                print(f"  Trend: {tech['trend']}")
                print(f"  Price vs SMA20: {tech['price_vs_sma20']}")
                print(f"  Price vs SMA50: {tech['price_vs_sma50']}")
                print()
                
                print("⚠️ RISK ASSESSMENT:")
                print("-" * 30)
                risk = result_data['risk_assessment']
                print(f"  Risk Level: {risk['risk_level']}")
                print(f"  Position Size: {risk['suggested_position']}")
                print()
                
                print("🎯 TRADING PLAN:")
                print("-" * 30)
                plan = result_data['trading_plan']
                print(f"  Action: {plan['action']}")
                print(f"  Entry: ${plan['entry_price']}")
                print(f"  Target: {plan['target_return']}")
                print(f"  Stop Loss: {plan['stop_loss']}")
                print(f"  Hold Time: {plan['hold_time']}")
                print()
                
                print("📋 REGIME INFO:")
                print("-" * 30)
                regime = result_data['regime_info']
                print(f"  Name: {regime['name']}")
                print(f"  Description: {regime['description']}")
                print(f"  Focus: {regime['focus']}")
                print(f"  Best For: {regime['best_for']}")
                print()
                
                # Show historical performance if available
                if 'historical_performance' in result_data:
                    print("📊 HISTORICAL PERFORMANCE:")
                    print("-" * 30)
                    perf = result_data['historical_performance']
                    
                    if 'buy_signals' in perf:
                        buy = perf['buy_signals']
                        print(f"  BUY Signals: {buy['count']} total")
                        print(f"    Avg Return: {buy['avg_return']:+.2%}")
                        print(f"    Win Rate: {buy['win_rate']:.1f}%")
                        print(f"    Success Rate: {buy['success_rate']}")
                    
                    if 'current_regime' in perf:
                        current = perf['current_regime']
                        print(f"  Current Regime ({current['name']}):")
                        print(f"    BUY Signals: {current['buy_signals']}")
                        print(f"    Avg Return: {current['avg_return']:+.2%}")
                        print(f"    Win Rate: {current['win_rate']:.1f}%")
                    print()
                
                # Show historical data if available
                if 'historical_data' in result_data:
                    hist = result_data['historical_data']
                    print("📈 HISTORICAL DATA:")
                    print("-" * 30)
                    print(f"  Data Points: {len(hist['dates'])}")
                    print(f"  Date Range: {hist['dates'][0]} to {hist['dates'][-1]}")
                    print(f"  Price Range: ${min(hist['prices']):.2f} - ${max(hist['prices']):.2f}")
                    print()
                
                print("🎉 API is working perfectly for Streamlit integration!")
                print()
                print("📋 STREAMLIT USAGE EXAMPLE:")
                print("-" * 40)
                print("```python")
                print("import requests")
                print()
                print("# Get signal analysis")
                print("response = requests.post(")
                print("    'http://127.0.0.1:8001/api/streamlit/signal-analysis',")
                print("    json={")
                print("        'symbol': 'TQQQ',")
                print("        'include_historical': True,")
                print("        'include_performance': True")
                print("    }")
                print(")")
                print()
                print("if response.status_code == 200:")
                print("    data = response.json()")
                print("    signal = data['data']['signal_summary']")
                print("    st.metric('Signal', signal['signal'])")
                print("```")
                
            else:
                print(f"❌ API returned error: {data.get('error')}")
        
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(f"Response: {response.text}")
    
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_streamlit_api()
