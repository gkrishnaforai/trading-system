#!/usr/bin/env python3
"""
Analyze and fix BUY signal detection to achieve 30-40% BUY signal rate
"""

import psycopg2
import os
from datetime import datetime, timedelta

def analyze_signal_distribution():
    """Analyze current signal distribution"""
    
    print("📊 Analyzing Current Signal Distribution")
    print("=" * 50)
    
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Test a comprehensive set of dates
        test_dates = []
        current_date = datetime(2025, 1, 1).date()
        end_date = datetime(2025, 12, 31).date()
        
        # Sample every 5 days
        while current_date <= end_date:
            if current_date.weekday() < 5:  # Weekdays only
                test_dates.append(current_date)
            current_date += timedelta(days=5)
        
        print(f"Testing {len(test_dates)} dates for signal distribution...")
        
        signal_counts = {"BUY": 0, "SELL": 0, "HOLD": 0, "ERROR": 0}
        detailed_results = []
        
        for date in test_dates:
            try:
                import requests
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
                        
                        if signal in signal_counts:
                            signal_counts[signal] += 1
                        else:
                            signal_counts["ERROR"] += 1
                        
                        detailed_results.append({
                            "date": date,
                            "signal": signal,
                            "confidence": confidence,
                            "reason": reason
                        })
                else:
                    signal_counts["ERROR"] += 1
                    
            except Exception as e:
                signal_counts["ERROR"] += 1
        
        # Calculate percentages
        total_valid = signal_counts["BUY"] + signal_counts["SELL"] + signal_counts["HOLD"]
        
        print(f"\n📊 Signal Distribution Analysis:")
        print(f"  Total Valid Signals: {total_valid}")
        print(f"  BUY Signals: {signal_counts['BUY']} ({signal_counts['BUY']/total_valid*100:.1f}%)")
        print(f"  SELL Signals: {signal_counts['SELL']} ({signal_counts['SELL']/total_valid*100:.1f}%)")
        print(f"  HOLD Signals: {signal_counts['HOLD']} ({signal_counts['HOLD']/total_valid*100:.1f}%)")
        print(f"  Errors: {signal_counts['ERROR']}")
        
        # Analyze BUY signal patterns
        buy_signals = [r for r in detailed_results if r["signal"] == "BUY"]
        if buy_signals:
            print(f"\n🟢 BUY Signal Analysis:")
            for signal in buy_signals:
                print(f"  {signal['date']}: {signal['confidence']:.1%} - {signal['reason']}")
        
        # Target analysis
        print(f"\n🎯 Target vs Actual:")
        print(f"  Target BUY Rate: 30-40%")
        print(f"  Actual BUY Rate: {signal_counts['BUY']/total_valid*100:.1f}%")
        print(f"  Gap: {30 - signal_counts['BUY']/total_valid*100:.1f}%")
        
        return signal_counts, detailed_results
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return {}, []
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    analyze_signal_distribution()
