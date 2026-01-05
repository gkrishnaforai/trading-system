#!/usr/bin/env python3
"""
Debug Remaining Unit Test Failures
Fix the specific SELL logic issues
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions

def debug_remaining_failures():
    """Debug the remaining 3 failing unit tests"""
    
    print("🔍 DEBUGGING REMAINING UNIT TEST FAILURES")
    print("=" * 60)
    
    # Initialize engine
    config = SignalConfig(
        rsi_oversold=45,
        rsi_moderately_oversold=35,
        rsi_mildly_oversold=50,
        max_volatility=8.0
    )
    
    engine = UnifiedTQQQSwingEngine(config)
    
    # Debug Test 2: Mean Reversion SELL - Overbought
    print("\n📋 Test 2: Mean Reversion SELL - Overbought")
    print("-" * 50)
    
    test2_conditions = MarketConditions(
        rsi=69.0,
        sma_20=44.50,  # Below SMA50 to avoid uptrend
        sma_50=45.80,
        ema_20=44.50,
        current_price=45.20,
        recent_change=0.025,  # +2.5%
        macd=0.8,
        macd_signal=0.6,
        volatility=4.2
    )
    
    print(f"   RSI: {test2_conditions.rsi}")
    print(f"   SMA20: {test2_conditions.sma_20}")
    print(f"   SMA50: {test2_conditions.sma_50}")
    print(f"   Current Price: {test2_conditions.current_price}")
    print(f"   Recent Change: {test2_conditions.recent_change:+.2%}")
    
    # Check regime detection logic
    is_uptrend = (
        test2_conditions.sma_20 > test2_conditions.sma_50 and
        test2_conditions.current_price > test2_conditions.sma_50
    )
    
    print(f"   Is Uptrend: {is_uptrend}")
    print(f"   SMA20 > SMA50: {test2_conditions.sma_20 > test2_conditions.sma_50}")
    print(f"   Price > SMA50: {test2_conditions.current_price > test2_conditions.sma_50}")
    
    # Check breakout conditions
    breakout_conditions = (
        test2_conditions.recent_change > 0.02 and
        test2_conditions.rsi > 55 and
        test2_conditions.current_price > test2_conditions.sma_20
    )
    
    print(f"   Breakout Conditions:")
    print(f"     Recent Change > 2%: {test2_conditions.recent_change > 0.02}")
    print(f"     RSI > 55: {test2_conditions.rsi > 55}")
    print(f"     Price > SMA20: {test2_conditions.current_price > test2_conditions.sma_20}")
    print(f"     Overall: {breakout_conditions}")
    
    # Get actual regime
    regime = engine.detect_market_regime(test2_conditions)
    print(f"   Detected Regime: {regime.value}")
    
    # Get signal
    signal_result = engine.generate_signal(test2_conditions)
    print(f"   Signal: {signal_result.signal.value.upper()}")
    print(f"   Reasoning: {signal_result.reasoning[0] if signal_result.reasoning else 'No reasoning'}")
    
    # Debug Test 4: Trend Continuation SELL - Trend Failure
    print("\n📋 Test 4: Trend Continuation SELL - Trend Failure")
    print("-" * 50)
    
    test4_conditions = MarketConditions(
        rsi=42.0,
        sma_20=41.85,
        sma_50=43.03,
        ema_20=41.85,
        current_price=41.85,  # Below SMA50
        recent_change=-0.074,  # -7.4%
        macd=-0.8,
        macd_signal=-0.5,
        volatility=5.2
    )
    
    print(f"   RSI: {test4_conditions.rsi}")
    print(f"   SMA20: {test4_conditions.sma_20}")
    print(f"   SMA50: {test4_conditions.sma_50}")
    print(f"   Current Price: {test4_conditions.current_price}")
    print(f"   Recent Change: {test4_conditions.recent_change:+.2%}")
    
    # Check trend conditions
    is_uptrend = (
        test4_conditions.sma_20 > test4_conditions.sma_50 and
        test4_conditions.current_price > test4_conditions.sma_50
    )
    
    print(f"   Is Uptrend: {is_uptrend}")
    print(f"   SMA20 > SMA50: {test4_conditions.sma_20 > test4_conditions.sma_50}")
    print(f"   Price > SMA50: {test4_conditions.current_price > test4_conditions.sma_50}")
    
    # Get actual regime and signal
    regime = engine.detect_market_regime(test4_conditions)
    print(f"   Detected Regime: {regime.value}")
    
    signal_result = engine.generate_signal(test4_conditions)
    print(f"   Signal: {signal_result.signal.value.upper()}")
    print(f"   Reasoning: {signal_result.reasoning[0] if signal_result.reasoning else 'No reasoning'}")
    
    # Debug Test 6: Breakout SELL - Failed Breakout
    print("\n📋 Test 6: Breakout SELL - Failed Breakout")
    print("-" * 50)
    
    test6_conditions = MarketConditions(
        rsi=35.0,
        sma_20=42.60,
        sma_50=42.27,
        ema_20=42.60,
        current_price=42.60,
        recent_change=-0.005,  # Small decline
        macd=-0.2,
        macd_signal=0.1,
        volatility=4.1
    )
    
    print(f"   RSI: {test6_conditions.rsi}")
    print(f"   SMA20: {test6_conditions.sma_20}")
    print(f"   SMA50: {test6_conditions.sma_50}")
    print(f"   Current Price: {test6_conditions.current_price}")
    print(f"   Recent Change: {test6_conditions.recent_change:+.2%}")
    
    # Check trend conditions
    is_uptrend = (
        test6_conditions.sma_20 > test6_conditions.sma_50 and
        test6_conditions.current_price > test6_conditions.sma_50
    )
    
    print(f"   Is Uptrend: {is_uptrend}")
    print(f"   SMA20 > SMA50: {test6_conditions.sma_20 > test6_conditions.sma_50}")
    print(f"   Price > SMA50: {test6_conditions.current_price > test6_conditions.sma_50}")
    
    # Check breakout conditions
    breakout_conditions = (
        test6_conditions.recent_change > 0.02 and
        test6_conditions.rsi > 55 and
        test6_conditions.current_price > test6_conditions.sma_20
    )
    
    print(f"   Breakout Conditions:")
    print(f"     Recent Change > 2%: {test6_conditions.recent_change > 0.02}")
    print(f"     RSI > 55: {test6_conditions.rsi > 55}")
    print(f"     Price > SMA20: {test6_conditions.current_price > test6_conditions.sma_20}")
    print(f"     Overall: {breakout_conditions}")
    
    # Get actual regime and signal
    regime = engine.detect_market_regime(test6_conditions)
    print(f"   Detected Regime: {regime.value}")
    
    signal_result = engine.generate_signal(test6_conditions)
    print(f"   Signal: {signal_result.signal.value.upper()}")
    print(f"   Reasoning: {signal_result.reasoning[0] if signal_result.reasoning else 'No reasoning'}")

if __name__ == "__main__":
    debug_remaining_failures()
