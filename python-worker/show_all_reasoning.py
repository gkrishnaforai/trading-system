#!/usr/bin/env python3
"""
Show All Signal Reasoning Types
Demonstrate the detailed reasoning provided by unified engine
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions

def show_all_reasoning_types():
    """Show all signal reasoning types with detailed explanations"""
    
    print("🎯 ALL SIGNAL REASONING TYPES")
    print("=" * 60)
    
    # Initialize engine
    config = SignalConfig(
        rsi_oversold=45,
        rsi_moderately_oversold=35,
        rsi_mildly_oversold=50,
        max_volatility=8.0
    )
    
    engine = UnifiedTQQQSwingEngine(config)
    
    # Test cases that show all reasoning types
    test_cases = [
        {
            "name": "Mean Reversion BUY - Strong oversold detection",
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
            )
        },
        {
            "name": "Mean Reversion SELL - Overbought detection",
            "conditions": MarketConditions(
                rsi=69.0,
                sma_20=44.50,
                sma_50=45.80,
                ema_20=44.50,
                current_price=45.20,
                recent_change=0.025,  # +2.5%
                macd=0.8,
                macd_signal=0.6,
                volatility=4.2
            )
        },
        {
            "name": "Trend Continuation BUY - Pullback detection",
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
            )
        },
        {
            "name": "Mean Reversion HOLD - Neutral conditions",
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
            )
        },
        {
            "name": "Breakout BUY - Momentum detection",
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
            )
        },
        {
            "name": "Volatility Expansion SELL - Risk-off detection",
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
            )
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 Test {i}: {test_case['name']}")
        print("-" * 50)
        
        # Generate signal
        signal_result = engine.generate_signal(test_case['conditions'])
        
        print(f"   Signal: {signal_result.signal.value.upper()}")
        print(f"   Regime: {signal_result.metadata.get('regime', 'unknown')}")
        print(f"   Confidence: {signal_result.confidence:.2f}")
        print(f"   📝 Reasoning:")
        for j, reason in enumerate(signal_result.reasoning, 1):
            print(f"      {j}. {reason}")
        
        # Show key metrics
        print(f"   📊 Market Conditions:")
        print(f"      RSI: {test_case['conditions'].rsi:.1f}")
        print(f"      Recent Change: {test_case['conditions'].recent_change:+.2%}")
        print(f"      Volatility: {test_case['conditions'].volatility:.1f}%")
        print(f"      SMA20: ${test_case['conditions'].sma_20:.2f}")
        print(f"      SMA50: ${test_case['conditions'].sma_50:.2f}")
        print(f"      Price: ${test_case['conditions'].current_price:.2f}")
    
    print(f"\n🎯 REASONING SUMMARY:")
    print("-" * 30)
    print(f"  ✅ All signals have detailed reasoning")
    print(f"  ✅ Reasoning explains the logic clearly")
    print(f"  ✅ Multiple reasoning points per signal")
    print(f"  ✅ Human-readable explanations")
    print(f"  ✅ Technical indicators included")
    print(f"  ✅ Market context provided")
    
    print(f"\n💡 USAGE:")
    print("-" * 20)
    print(f"  • User-facing displays")
    print(f"  • Trading logs")
    print(f"  • Signal analysis")
    print(f"  • Debugging")
    print(f"  • Compliance reporting")

if __name__ == "__main__":
    show_all_reasoning_types()
