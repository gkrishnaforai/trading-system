#!/usr/bin/env python3
"""
Demonstration of DRY and Testable Signal Calculation
Shows how the core logic can be reused and tested independently
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime

# Import the core signal calculator
from app.signal_engines.signal_calculator_core import (
    SignalCalculator, SignalConfig, SignalType,
    calculate_signal_from_dataframe
)
from app.signal_engines.generic_swing_engine_refactored import create_generic_swing_engine
from app.signal_engines.base import MarketContext

def demonstrate_dry_approach():
    """Demonstrate the DRY approach with reusable core logic"""
    
    print("🎯 DRY and Testable Signal Calculation Demo")
    print("=" * 60)
    
    # 1. Create test scenarios
    scenarios = create_test_scenarios()
    
    # 2. Test core logic directly
    print("\n📊 Testing Core Signal Calculator:")
    print("-" * 40)
    
    for name, df in scenarios.items():
        result = calculate_signal_from_dataframe(df, symbol="TQQQ")
        print(f"{name:15}: {result.signal.value:4} ({result.confidence:.2f}) - {result.reasoning[0][:50]}...")
    
    # 3. Test with different configurations
    print("\n⚙️ Testing Different Configurations:")
    print("-" * 40)
    
    aggressive_config = SignalConfig(
        rsi_oversold=60,  # Very aggressive
        max_volatility=15.0,  # Allow high volatility
        oversold_boost=0.25
    )
    
    conservative_config = SignalConfig(
        rsi_oversold=25,  # Very conservative
        max_volatility=3.0,  # Low volatility tolerance
        oversold_boost=0.05
    )
    
    test_df = scenarios["Oversold"]
    
    aggressive_result = calculate_signal_from_dataframe(
        test_df, symbol="TQQQ", config=aggressive_config
    )
    
    conservative_result = calculate_signal_from_dataframe(
        test_df, symbol="TQQQ", config=conservative_config
    )
    
    print(f"Aggressive   : {aggressive_result.signal.value} ({aggressive_result.confidence:.2f})")
    print(f"Conservative : {conservative_result.signal.value} ({conservative_result.confidence:.2f})")
    
    # 4. Test with refactored engine
    print("\n🔧 Testing Refactored Engine:")
    print("-" * 40)
    
    engine = create_generic_swing_engine()
    context = MarketContext(
        symbol="TQQQ",
        timestamp=datetime.now().isoformat(),
        current_price=100.0,
        volatility=0.02,
        trend="neutral"
    )
    
    for name, df in scenarios.items():
        signal = engine.generate_signal("TQQQ", df, context)
        print(f"{name:15}: {signal.signal:4} ({signal.confidence:.2f}) - Regime: {signal.metadata.get('regime', 'unknown')}")
    
    # 5. Demonstrate reusability across different symbols
    print("\n🔄 Testing Reusability Across Symbols:")
    print("-" * 40)
    
    symbols = ["TQQQ", "QQQ", "SPY", "AAPL"]
    test_df = scenarios["Neutral"]
    
    for symbol in symbols:
        result = calculate_signal_from_dataframe(test_df, symbol=symbol)
        print(f"{symbol:6}: {result.signal.value:4} ({result.confidence:.2f})")
    
    # 6. Show signal distribution analysis
    print("\n📈 Signal Distribution Analysis:")
    print("-" * 40)
    
    analyze_signal_distribution()
    
    print("\n✅ Benefits of DRY Approach:")
    print("  • Single source of truth for signal logic")
    print("  • Easy to test with different parameters")
    print("  • Reusable across multiple engines")
    print("  • Consistent behavior across symbols")
    print("  • Simple to maintain and update")

def create_test_scenarios() -> dict:
    """Create test scenarios for demonstration"""
    
    dates = pd.date_range('2024-01-01', periods=50, freq='D')
    base_price = 100
    
    scenarios = {}
    
    # Neutral scenario
    scenarios["Neutral"] = pd.DataFrame({
        'date': dates,
        'open': [base_price] * 50,
        'high': [base_price * 1.02] * 50,
        'low': [base_price * 0.98] * 50,
        'close': [base_price] * 50,
        'volume': [2000000] * 50,
        'rsi': [50.0] * 50,
        'sma_20': [base_price] * 50,
        'sma_50': [base_price] * 50,
        'ema_20': [base_price] * 50,
        'macd': [0.0] * 50,
        'macd_signal': [0.0] * 50
    })
    
    # Oversold scenario
    oversold_df = scenarios["Neutral"].copy()
    oversold_df['rsi'] = [25.0] * 50
    oversold_df.loc[45:, 'close'] = [98, 97, 96, 95, 94]  # Recent decline
    scenarios["Oversold"] = oversold_df
    
    # Overbought scenario
    overbought_df = scenarios["Neutral"].copy()
    overbought_df['rsi'] = [75.0] * 50
    overbought_df.loc[45:, 'close'] = [102, 103, 104, 105, 106]  # Recent rise
    scenarios["Overbought"] = overbought_df
    
    # Uptrend scenario
    uptrend_df = scenarios["Neutral"].copy()
    uptrend_df['sma_20'] = [102] * 50
    uptrend_df['sma_50'] = [100] * 50
    uptrend_df['close'] = [103] * 50
    uptrend_df['macd'] = [0.5] * 50
    uptrend_df['macd_signal'] = [0.3] * 50
    scenarios["Uptrend"] = uptrend_df
    
    # Downtrend scenario
    downtrend_df = scenarios["Neutral"].copy()
    downtrend_df['sma_20'] = [98] * 50
    downtrend_df['sma_50'] = [100] * 50
    downtrend_df['close'] = [97] * 50
    downtrend_df['macd'] = [-0.5] * 50
    downtrend_df['macd_signal'] = [-0.3] * 50
    scenarios["Downtrend"] = downtrend_df
    
    return scenarios

def analyze_signal_distribution():
    """Analyze signal distribution across multiple scenarios"""
    
    # Generate 100 random scenarios
    buy_count = sell_count = hold_count = 0
    
    for i in range(100):
        # Create random scenario
        df = create_random_scenario(i)
        result = calculate_signal_from_dataframe(df, symbol="TQQQ")
        
        if result.signal == SignalType.BUY:
            buy_count += 1
        elif result.signal == SignalType.SELL:
            sell_count += 1
        else:
            hold_count += 1
    
    total = buy_count + sell_count + hold_count
    
    print(f"  Total Scenarios: {total}")
    print(f"  BUY Signals:   {buy_count:3d} ({buy_count/total*100:5.1f}%)")
    print(f"  SELL Signals:  {sell_count:3d} ({sell_count/total*100:5.1f}%)")
    print(f"  HOLD Signals:  {hold_count:3d} ({hold_count/total*100:5.1f}%)")
    
    # Check if we're meeting the target
    buy_rate = buy_count / total * 100
    if 25 <= buy_rate <= 45:
        print(f"  ✅ BUY rate {buy_rate:.1f}% is within target range (25-45%)")
    else:
        print(f"  ⚠️  BUY rate {buy_rate:.1f}% is outside target range (25-45%)")

def create_random_scenario(seed: int) -> pd.DataFrame:
    """Create random market scenario"""
    np.random.seed(seed)
    
    dates = pd.date_range('2024-01-01', periods=50, freq='D')
    base_price = 100
    
    # Random walk with trend
    price_changes = np.random.randn(50) * 2
    trend = np.random.choice([-1, 0, 1]) * 0.5
    price = base_price + np.cumsum(price_changes + trend)
    
    # Generate indicators
    rsi = 30 + np.random.rand(50) * 40
    sma_20 = price + np.random.randn(50) * 3
    sma_50 = price + np.random.randn(50) * 5
    ema_20 = price + np.random.randn(50) * 2
    macd = np.random.randn(50) * 1
    macd_signal = macd + np.random.randn(50) * 0.5
    
    return pd.DataFrame({
        'date': dates,
        'open': price * (1 + np.random.rand(50) * 0.01 - 0.005),
        'high': price * (1 + np.random.rand(50) * 0.02),
        'low': price * (1 - np.random.rand(50) * 0.02),
        'close': price,
        'volume': np.random.randint(1000000, 5000000, 50),
        'rsi': rsi,
        'sma_20': sma_20,
        'sma_50': sma_50,
        'ema_20': ema_20,
        'macd': macd,
        'macd_signal': macd_signal
    })

if __name__ == "__main__":
    demonstrate_dry_approach()
