#!/usr/bin/env python3
"""
Debug Specific Unit Test Failures
Understand why regime detection is failing
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions

def debug_failing_tests():
    """Debug the specific failing unit tests"""
    
    print("🔍 DEBUGGING FAILING UNIT TESTS")
    print("=" * 50)
    
    # Initialize engine
    config = SignalConfig(
        rsi_oversold=45,
        rsi_moderately_oversold=35,
        rsi_mildly_oversold=50,
        max_volatility=8.0
    )
    
    engine = UnifiedTQQQSwingEngine(config)
    
    # Debug Test 2: Mean Reversion SELL - Overbought
    print("\n📋 Debug Test 2: Mean Reversion SELL - Overbought")
    print("-" * 50)
    
    test2_conditions = MarketConditions(
        rsi=69.0,
        sma_20=45.50,
        sma_50=44.80,
        ema_20=45.50,
        current_price=46.20,
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
    print(f"   Volatility: {test2_conditions.volatility}")
    
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
    
    # Debug Test 3: Trend Continuation BUY - Pullback
    print("\n📋 Debug Test 3: Trend Continuation BUY - Pullback")
    print("-" * 50)
    
    test3_conditions = MarketConditions(
        rsi=36.0,
        sma_20=44.40,
        sma_50=42.38,
        ema_20=44.40,
        current_price=44.40,  # At SMA20
        recent_change=-0.01,  # Small decline
        macd=0.2,
        macd_signal=0.3,
        volatility=3.8
    )
    
    print(f"   RSI: {test3_conditions.rsi}")
    print(f"   SMA20: {test3_conditions.sma_20}")
    print(f"   SMA50: {test3_conditions.sma_50}")
    print(f"   Current Price: {test3_conditions.current_price}")
    print(f"   Recent Change: {test3_conditions.recent_change:+.2%}")
    
    # Check pullback conditions
    pullback_to_sma = (
        test3_conditions.current_price < test3_conditions.sma_20 and
        test3_conditions.current_price > test3_conditions.sma_50
    )
    
    print(f"   Pullback Conditions:")
    print(f"     Price < SMA20: {test3_conditions.current_price < test3_conditions.sma_20}")
    print(f"     Price > SMA50: {test3_conditions.current_price > test3_conditions.sma_50}")
    print(f"     Overall: {pullback_to_sma}")
    
    print(f"   RSI Range Check: 35 < {test3_conditions.rsi} < 60 = {35 < test3_conditions.rsi < 60}")
    
    # Get actual regime and signal
    regime = engine.detect_market_regime(test3_conditions)
    print(f"   Detected Regime: {regime.value}")
    
    signal_result = engine.generate_signal(test3_conditions)
    print(f"   Signal: {signal_result.signal.value.upper()}")
    print(f"   Reasoning: {signal_result.reasoning[0] if signal_result.reasoning else 'No reasoning'}")

if __name__ == "__main__":
    debug_failing_tests()
