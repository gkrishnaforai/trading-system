#!/usr/bin/env python3
"""
Comprehensive TQQQ Backtest Test Suite
Tests BUY, SELL, and HOLD scenarios based on actual chart analysis
"""

import requests
import json
from datetime import datetime

def test_tqqq_scenarios():
    """Test TQQQ signal generation across different market scenarios"""
    
    print("🧪 TQQQ Comprehensive Backtest Suite")
    print("=" * 60)
    
    # Test scenarios based on chart analysis
    test_scenarios = {
        # 🟢 BUY SCENARIOS - Uptrends and Reversals
        "2025-11-03": {
            "expected": "BUY",
            "reason": "Early November uptrend beginning",
            "confidence_threshold": 0.6
        },
        "2025-11-12": {
            "expected": "BUY", 
            "reason": "Mid-November bullish breakout",
            "confidence_threshold": 0.6
        },
        "2025-12-26": {
            "expected": "BUY",
            "reason": "Late December year-end rally",
            "confidence_threshold": 0.6
        },
        
        # 🔴 SELL SCENARIOS - Downtrends and Breakdowns  
        "2025-10-28": {
            "expected": "SELL",
            "reason": "Late October bearish breakdown",
            "confidence_threshold": 0.6
        },
        "2025-12-10": {
            "expected": "SELL",
            "reason": "Early December sharp decline",
            "confidence_threshold": 0.6
        },
        "2025-12-17": {
            "expected": "SELL",
            "reason": "Mid-December continued downtrend", 
            "confidence_threshold": 0.6
        },
        
        # 🟡 HOLD SCENARIOS - Sideways and Consolidation
        "2025-11-25": {
            "expected": "HOLD",
            "reason": "Late November range-bound consolidation",
            "confidence_threshold": 0.4
        },
        "2025-12-31": {
            "expected": "HOLD",
            "reason": "Year-end choppy sideways action",
            "confidence_threshold": 0.4
        },
        "2026-01-02": {
            "expected": "HOLD", 
            "reason": "Early January consolidation",
            "confidence_threshold": 0.4
        }
    }
    
    results = []
    correct_predictions = 0
    total_tests = len(test_scenarios)
    
    print(f"📋 Testing {total_tests} scenarios...")
    print()
    
    for date, scenario in test_scenarios.items():
        print(f"🔍 Testing {date} - {scenario['reason']}")
        
        try:
            # Generate signal
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
                    
                    actual_signal = signal_data.get("signal", "UNKNOWN")
                    confidence = signal_data.get("confidence", 0)
                    reason = signal_data.get("reason", "No reason")
                    
                    # Evaluate prediction
                    expected = scenario["expected"]
                    is_correct = actual_signal == expected
                    
                    if is_correct:
                        correct_predictions += 1
                        status = "✅ CORRECT"
                    else:
                        status = "❌ INCORRECT"
                    
                    # Check confidence threshold
                    confidence_ok = confidence >= scenario["confidence_threshold"]
                    conf_status = "📈" if confidence_ok else "📉"
                    
                    result = {
                        "date": date,
                        "expected": expected,
                        "actual": actual_signal,
                        "confidence": confidence,
                        "reason": reason,
                        "correct": is_correct,
                        "confidence_ok": confidence_ok,
                        "scenario": scenario["reason"]
                    }
                    
                    results.append(result)
                    
                    print(f"   {status} Expected: {expected}, Got: {actual_signal} ({confidence:.1%}) {conf_status}")
                    print(f"   📝 Reason: {reason}")
                    
                else:
                    print("   ❌ No signal generated")
                    results.append({
                        "date": date,
                        "expected": scenario["expected"],
                        "actual": "NO_SIGNAL",
                        "confidence": 0,
                        "reason": "No signal generated",
                        "correct": False,
                        "confidence_ok": False,
                        "scenario": scenario["reason"]
                    })
            else:
                print(f"   ❌ API Error: {response.status_code}")
                results.append({
                    "date": date,
                    "expected": scenario["expected"],
                    "actual": "API_ERROR",
                    "confidence": 0,
                    "reason": f"API Error: {response.status_code}",
                    "correct": False,
                    "confidence_ok": False,
                    "scenario": scenario["reason"]
                })
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            results.append({
                "date": date,
                "expected": scenario["expected"],
                "actual": "ERROR",
                "confidence": 0,
                "reason": str(e),
                "correct": False,
                "confidence_ok": False,
                "scenario": scenario["reason"]
            })
        
        print()
    
    # Summary Analysis
    print("📊 COMPREHENSIVE RESULTS SUMMARY")
    print("=" * 60)
    
    accuracy = (correct_predictions / total_tests) * 100
    print(f"🎯 Overall Accuracy: {accuracy:.1f}% ({correct_predictions}/{total_tests})")
    
    # Breakdown by signal type
    buy_tests = [r for r in results if r["expected"] == "BUY"]
    sell_tests = [r for r in results if r["expected"] == "SELL"]
    hold_tests = [r for r in results if r["expected"] == "HOLD"]
    
    def calculate_accuracy(tests):
        if not tests:
            return 0, 0
        correct = len([t for t in tests if t["correct"]])
        return correct, len(tests)
    
    buy_correct, buy_total = calculate_accuracy(buy_tests)
    sell_correct, sell_total = calculate_accuracy(sell_tests)
    hold_correct, hold_total = calculate_accuracy(hold_tests)
    
    print(f"\n🟢 BUY Signals: {buy_correct}/{buy_total} ({(buy_correct/buy_total*100) if buy_total else 0:.1f}%)")
    print(f"🔴 SELL Signals: {sell_correct}/{sell_total} ({(sell_correct/sell_total*100) if sell_total else 0:.1f}%)")
    print(f"🟡 HOLD Signals: {hold_correct}/{hold_total} ({(hold_correct/hold_total*100) if hold_total else 0:.1f}%)")
    
    # Confidence Analysis
    avg_confidence = sum(r["confidence"] for r in results) / len(results)
    confidence_ok_count = len([r for r in results if r["confidence_ok"]])
    confidence_rate = (confidence_ok_count / total_tests) * 100
    
    print(f"\n📈 Average Confidence: {avg_confidence:.1%}")
    print(f"✅ Confidence Threshold Met: {confidence_rate:.1f}%")
    
    # Detailed Results
    print(f"\n📋 DETAILED RESULTS:")
    print("-" * 60)
    
    for result in results:
        status = "✅" if result["correct"] else "❌"
        conf_status = "📈" if result["confidence_ok"] else "📉"
        
        print(f"{status} {result['date']} | Expected: {result['expected']:4} | "
              f"Actual: {result['actual']:4} | {result['confidence']:.1%} {conf_status}")
        print(f"    📝 {result['scenario']}")
        if result["reason"] != "No reason":
            print(f"    🔍 {result['reason'][:80]}...")
        print()
    
    # Performance Grade
    if accuracy >= 80:
        grade = "🌟 EXCELLENT"
    elif accuracy >= 70:
        grade = "👍 GOOD"
    elif accuracy >= 60:
        grade = "⚠️ FAIR"
    else:
        grade = "❌ POOR"
    
    print(f"🏆 PERFORMANCE GRADE: {grade}")
    print(f"📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return results

if __name__ == "__main__":
    test_tqqq_scenarios()
