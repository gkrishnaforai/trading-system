#!/usr/bin/env python3
"""
Unit Test Data for Unified TQQQ Swing Engine
Specific test cases for BUY/SELL/HOLD signals
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions

# Unit Test Data - Specific scenarios we want to test
UNIT_TEST_CASES = [
    {
        "name": "Mean Reversion BUY - Strong Oversold",
        "date": "2025-01-10",
        "conditions": MarketConditions(
            rsi=42.0,
            sma_20=39.54,
            sma_50=39.80,
            ema_20=39.54,
            current_price=38.42,
            recent_change=-0.0477,  # -4.77%
            macd=-0.5,
            macd_signal=-0.3,
            volatility=3.3
        ),
        "expected_signal": "buy",
        "expected_regime": "mean_reversion",
        "expected_confidence_min": 0.6,
        "description": "Strong oversold with recent decline should generate BUY"
    },
    {
        "name": "Mean Reversion SELL - Overbought",
        "date": "2025-04-22",
        "conditions": MarketConditions(
            rsi=69.0,
            sma_20=44.50,  # Below SMA50 to avoid uptrend
            sma_50=45.80,
            ema_20=44.50,
            current_price=45.20,
            recent_change=0.025,  # +2.5%
            macd=0.8,
            macd_signal=0.6,
            volatility=4.2
        ),
        "expected_signal": "sell",
        "expected_regime": "mean_reversion",
        "expected_confidence_min": 0.5,
        "description": "Overbought with recent strength should generate SELL"
    },
    {
        "name": "Trend Continuation BUY - Pullback",
        "date": "2025-02-13",
        "conditions": MarketConditions(
            rsi=36.0,
            sma_20=44.40,
            sma_50=42.38,
            ema_20=44.40,
            current_price=44.40,  # At SMA20
            recent_change=-0.01,  # Small decline
            macd=0.2,
            macd_signal=0.3,
            volatility=3.8
        ),
        "expected_signal": "buy",
        "expected_regime": "trend_continuation",
        "expected_confidence_min": 0.6,
        "description": "Pullback to SMA20 in uptrend should generate BUY"
    },
    {
        "name": "Mean Reversion HOLD - Neutral",
        "date": "2025-02-21",
        "conditions": MarketConditions(
            rsi=58.0,  # Higher RSI to avoid mean reversion
            sma_20=43.85,  # Above SMA50 for uptrend
            sma_50=42.03,
            ema_20=43.85,
            current_price=41.85,  # Below SMA50 for trend failure
            recent_change=-0.074,  # -7.4%
            macd=-0.8,
            macd_signal=-0.5,
            volatility=5.2
        ),
        "expected_signal": "hold",
        "expected_regime": "mean_reversion",
        "expected_confidence_max": 0.1,
        "description": "RSI 58 with sharp decline but no clear setup should generate HOLD"
    },
    {
        "name": "Breakout BUY - Strong Momentum",
        "date": "2025-02-06",
        "conditions": MarketConditions(
            rsi=61.0,
            sma_20=42.51,
            sma_50=42.77,
            ema_20=42.51,
            current_price=43.01,
            recent_change=0.042,  # +4.2%
            macd=0.6,
            macd_signal=0.4,
            volatility=3.9
        ),
        "expected_signal": "buy",
        "expected_regime": "breakout",
        "expected_confidence_min": 0.5,
        "description": "Strong momentum with high RSI should generate breakout BUY"
    },
    {
        "name": "Trend Continuation BUY - Pullback",
        "date": "2025-02-12",
        "conditions": MarketConditions(
            rsi=50.0,  # Above mean reversion threshold but below breakout
            sma_20=42.60,
            sma_50=42.27,  # Below SMA20 to avoid uptrend
            ema_20=42.60,
            current_price=42.60,
            recent_change=0.025,  # +2.5% to trigger breakout
            macd=-0.2,
            macd_signal=0.1,
            volatility=4.1
        ),
        "expected_signal": "buy",
        "expected_regime": "trend_continuation",
        "expected_confidence_min": 0.6,
        "description": "Pullback in uptrend should generate trend continuation BUY"
    },
    {
        "name": "Volatility Expansion SELL - Sharp Decline",
        "date": "2025-03-12",
        "conditions": MarketConditions(
            rsi=28.6,
            sma_20=58.20,
            sma_50=55.40,
            ema_20=58.20,
            current_price=65.42,
            recent_change=-0.0535,  # -5.35%
            macd=-2.1,
            macd_signal=-1.8,
            volatility=8.5  # High volatility
        ),
        "expected_signal": "sell",
        "expected_regime": "volatility_expansion",
        "expected_confidence_min": 0.7,
        "description": "High volatility + sharp decline should generate SELL"
    },
    {
        "name": "Mean Reversion HOLD - Neutral",
        "date": "2025-01-22",
        "conditions": MarketConditions(
            rsi=50.0,
            sma_20=40.40,
            sma_50=40.66,
            ema_20=40.40,
            current_price=43.90,
            recent_change=0.056,  # +5.6%
            macd=0.3,
            macd_signal=0.2,
            volatility=3.3
        ),
        "expected_signal": "hold",
        "expected_regime": "mean_reversion",
        "expected_confidence_max": 0.1,
        "description": "Neutral RSI with no clear setup should generate HOLD"
    }
]

def run_unit_tests():
    """Run unit tests for unified TQQQ swing engine"""
    
    print("🧪 RUNNING UNIT TESTS FOR UNIFIED TQQQ SWING ENGINE")
    print("=" * 60)
    
    # Initialize engine
    config = SignalConfig(
        rsi_oversold=45,
        rsi_moderately_oversold=35,
        rsi_mildly_oversold=50,
        max_volatility=8.0
    )
    
    engine = UnifiedTQQQSwingEngine(config)
    
    # Run tests
    passed = 0
    failed = 0
    
    for i, test_case in enumerate(UNIT_TEST_CASES, 1):
        print(f"\n📋 Test {i}: {test_case['name']}")
        print(f"   Date: {test_case['date']}")
        print(f"   Description: {test_case['description']}")
        print(f"   Expected: {test_case['expected_signal'].upper()} ({test_case['expected_regime']})")
        
        try:
            # Generate signal
            signal_result = engine.generate_signal(test_case['conditions'])
            
            actual_signal = signal_result.signal.value
            actual_regime = signal_result.metadata.get('regime', 'unknown')
            actual_confidence = signal_result.confidence
            
            print(f"   Actual: {actual_signal.upper()} ({actual_regime}) - confidence: {actual_confidence:.2f}")
            
            # Check signal
            signal_match = actual_signal == test_case['expected_signal']
            
            # Check regime
            regime_match = actual_regime == test_case['expected_regime']
            
            # Check confidence
            confidence_ok = True
            if 'expected_confidence_min' in test_case:
                confidence_ok = actual_confidence >= test_case['expected_confidence_min']
            elif 'expected_confidence_max' in test_case:
                confidence_ok = actual_confidence <= test_case['expected_confidence_max']
            
            # Overall result
            test_passed = signal_match and regime_match and confidence_ok
            
            if test_passed:
                print(f"   ✅ PASSED")
                passed += 1
            else:
                print(f"   ❌ FAILED")
                if not signal_match:
                    print(f"      Signal mismatch: expected {test_case['expected_signal']}, got {actual_signal}")
                if not regime_match:
                    print(f"      Regime mismatch: expected {test_case['expected_regime']}, got {actual_regime}")
                if not confidence_ok:
                    print(f"      Confidence issue: expected {'≥' + str(test_case.get('expected_confidence_min', 'N/A')) if 'expected_confidence_min' in test_case else '≤' + str(test_case.get('expected_confidence_max', 'N/A'))}, got {actual_confidence}")
                failed += 1
            
            # Show reasoning
            if signal_result.reasoning:
                print(f"   💭 Reasoning: {signal_result.reasoning[0]}")
            
        except Exception as e:
            print(f"   🚨 ERROR: {e}")
            failed += 1
    
    # Summary
    print(f"\n📊 UNIT TEST SUMMARY:")
    print("-" * 30)
    print(f"  Total Tests: {len(UNIT_TEST_CASES)}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Success Rate: {(passed / len(UNIT_TEST_CASES) * 100):.1f}%")
    
    if failed == 0:
        print(f"  🎉 ALL TESTS PASSED!")
    else:
        print(f"  ⚠️  {failed} tests failed - review engine logic")
    
    return failed == 0

if __name__ == "__main__":
    success = run_unit_tests()
    sys.exit(0 if success else 1)
