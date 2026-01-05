#!/usr/bin/env python3
"""
Find all BUY signals in 2025
"""

import requests
import json
from datetime import datetime, timedelta

def find_buy_signals():
    """Find all dates with BUY signals in 2025"""
    
    print("🔍 Searching for BUY Signals in 2025")
    print("=" * 50)
    
    buy_signals = []
    total_tested = 0
    
    # Test key dates throughout 2025
    test_dates = []
    current_date = datetime(2025, 1, 1).date()
    end_date = datetime(2025, 12, 31).date()
    
    # Sample every 5 days
    while current_date <= end_date:
        if current_date.weekday() < 5:  # Weekdays only
            test_dates.append(current_date)
        current_date += timedelta(days=5)
    
    print(f"Testing {len(test_dates)} dates...")
    
    for date in test_dates:
        try:
            response = requests.post(
                "http://localhost:8001/admin/signals/generate",
                headers={"Content-Type": "application/json"},
                json={
                    "symbols": ["TQQQ"],
                    "strategy": "tqqq_swing",
                    "backtest_date": date.isoformat()
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("signals"):
                    signal_data = data["signals"][0]
                    signal = signal_data.get("signal", "unknown")
                    confidence = signal_data.get("confidence", 0)
                    reason = signal_data.get("reason", "")
                    
                    total_tested += 1
                    
                    if signal == "BUY":
                        buy_signals.append({
                            "date": date.isoformat(),
                            "confidence": confidence,
                            "reason": reason
                        })
                        print(f"🟢 BUY found: {date} ({confidence:.1%}) - {reason}")
                    elif signal == "SELL":
                        print(f"🔴 SELL: {date} ({confidence:.1%})")
                    elif signal == "HOLD":
                        print(f"🟡 HOLD: {date} ({confidence:.1%})")
                    else:
                        print(f"❓ Unknown: {date}")
            else:
                print(f"❌ API Error for {date}")
                
        except Exception as e:
            print(f"❌ Error testing {date}: {e}")
    
    print(f"\n📊 Results Summary:")
    print(f"  Total dates tested: {total_tested}")
    print(f"  BUY signals found: {len(buy_signals)}")
    print(f"  BUY signal rate: {(len(buy_signals)/total_tested*100):.1f}%")
    
    if buy_signals:
        print(f"\n🟢 All BUY Signals:")
        for signal in buy_signals:
            print(f"  {signal['date']}: {signal['confidence']:.1%} - {signal['reason']}")
    else:
        print(f"\n❌ No BUY signals found!")
        print("This indicates the BUY signal logic is too conservative.")
    
    return buy_signals

if __name__ == "__main__":
    find_buy_signals()
