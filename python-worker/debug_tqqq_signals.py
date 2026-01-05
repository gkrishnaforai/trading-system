#!/usr/bin/env python3
"""
Debug TQQQ engine to see what's happening with BUY signals
"""

import requests
import json

def debug_tqqq_engine():
    """Debug TQQQ engine signal generation"""
    
    print("🔍 Debugging TQQQ Engine Signal Generation")
    print("=" * 50)
    
    test_dates = ["2025-05-01", "2025-04-01", "2025-03-17"]
    
    for date in test_dates:
        print(f"\n📅 Testing {date}:")
        
        try:
            response = requests.post(
                "http://localhost:8001/admin/signals/generate",
                headers={"Content-Type": "application/json"},
                json={
                    "symbols": ["TQQQ"],
                    "strategy": "tqqq_swing",
                    "backtest_date": date
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("signals"):
                    signal_data = data["signals"][0]
                    signal = signal_data.get("signal", "unknown")
                    confidence = signal_data.get("confidence", 0)
                    reason = signal_data.get("reason", "")
                    
                    print(f"  Signal: {signal}")
                    print(f"  Confidence: {confidence:.1%}")
                    print(f"  Reason: {reason}")
                    
                    # Extract RSI from reason if available
                    if "RSI" in reason:
                        rsi_part = [part for part in reason.split("|") if "RSI" in part]
                        if rsi_part:
                            print(f"  RSI Info: {rsi_part[0].strip()}")
                    
                    # Check if RSI < 50 should trigger BUY
                    if "RSI" in reason and "oversold" in reason:
                        rsi_str = reason.split("RSI")[1].split(":")[1].strip()
                        try:
                            rsi_value = float(rsi_str.split()[0])
                            if rsi_value < 50:
                                print(f"  ⚠️  RSI {rsi_value} < 50 should trigger BUY but got {signal}")
                            else:
                                print(f"  ✅ RSI {rsi_value} >= 50, HOLD is correct")
                        except:
                            pass
            else:
                print(f"  ❌ Error: {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ Exception: {e}")

if __name__ == "__main__":
    debug_tqqq_engine()
