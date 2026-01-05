#!/usr/bin/env python3
"""
Simple Demo of DRY and Testable Signal Calculation Core
Shows the core logic independently
"""

import pandas as pd
import numpy as np
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

@dataclass
class MarketConditions:
    """Market conditions for signal calculation"""
    rsi: float
    sma_20: float
    sma_50: float
    current_price: float
    recent_change: float
    macd: float
    macd_signal: float
    volatility: float

@dataclass
class SignalConfig:
    """Configuration for signal calculation"""
    rsi_oversold: float = 30
    rsi_overbought: float = 70
    rsi_moderately_oversold: float = 40
    rsi_mildly_oversold: float = 45
    max_volatility: float = 6.0
    oversold_boost: float = 0.1
    trend_boost: float = 0.1

@dataclass
class SignalResult:
    """Result of signal calculation"""
    signal: SignalType
    confidence: float
    reasoning: List[str]
    metadata: Dict[str, float]

class SignalCalculator:
    """Core signal calculation logic - DRY and testable"""
    
    def __init__(self, config: Optional[SignalConfig] = None):
        self.config = config or SignalConfig()
    
    def calculate_signal(self, conditions: MarketConditions, 
                        symbol: Optional[str] = None) -> SignalResult:
        """Calculate signal based on market conditions"""
        
        # Apply symbol-specific adjustments
        config = self._apply_symbol_adjustments(symbol)
        
        # Check volatility filter
        if conditions.volatility > config.max_volatility:
            return SignalResult(
                signal=SignalType.HOLD,
                confidence=0.1,
                reasoning=[f"HOLD: Volatility too high: {conditions.volatility:.1f}%"],
                metadata={}
            )
        
        # Determine conditions
        is_oversold = conditions.rsi < config.rsi_oversold
        is_moderately_oversold = conditions.rsi < config.rsi_moderately_oversold
        is_mildly_oversold = conditions.rsi < config.rsi_mildly_oversold
        is_overbought = conditions.rsi > config.rsi_overbought
        
        is_uptrend = conditions.sma_20 > conditions.sma_50 and conditions.current_price > conditions.sma_20
        is_downtrend = conditions.sma_20 < conditions.sma_50 and conditions.current_price < conditions.sma_20
        is_recently_down = conditions.recent_change < -0.02
        is_recently_up = conditions.recent_change > 0.02
        
        macd_bullish = conditions.macd > conditions.macd_signal
        macd_bearish = conditions.macd < conditions.macd_signal
        
        reasoning = []
        confidence = 0.5
        
        # Core signal logic
        if is_oversold and is_recently_down:
            signal = SignalType.BUY
            confidence = 0.7
            reasoning.extend([
                "Strong oversold buying opportunity",
                f"RSI oversold: {conditions.rsi:.1f}",
                f"Recent decline: {conditions.recent_change:.2%}",
                "Mean reversion play"
            ])
        elif is_moderately_oversold and not is_downtrend:
            signal = SignalType.BUY
            confidence = 0.6
            reasoning.extend([
                "Moderately oversold buying opportunity",
                f"RSI moderately oversold: {conditions.rsi:.1f}",
                "Support level likely",
                "Reversal potential"
            ])
        elif is_mildly_oversold and not is_downtrend:
            signal = SignalType.BUY
            confidence = 0.4
            reasoning.extend([
                "Mildly oversold buying opportunity",
                f"RSI mildly oversold: {conditions.rsi:.1f}",
                "Bottoming pattern detected",
                "Mean reversion entry"
            ])
        elif is_overbought and is_recently_up:
            signal = SignalType.SELL
            confidence = 0.6
            reasoning.extend([
                "Overbought selling opportunity",
                f"RSI overbought: {conditions.rsi:.1f}",
                f"Recent rise: {conditions.recent_change:.2%}",
                "Mean reversion play"
            ])
        elif is_uptrend and macd_bullish and not is_overbought:
            signal = SignalType.BUY
            confidence = 0.5
            reasoning.extend([
                "Uptrend continuation",
                f"RSI strength: {conditions.rsi:.1f}",
                "MACD bullish confirmation",
                "Trend-following entry"
            ])
        elif is_downtrend and macd_bearish and not is_oversold:
            signal = SignalType.SELL
            confidence = 0.5
            reasoning.extend([
                "Downtrend continuation",
                f"RSI weakness: {conditions.rsi:.1f}",
                "MACD bearish confirmation",
                "Trend-following exit"
            ])
        else:
            signal = SignalType.HOLD
            confidence = 0.2
            reasoning.extend([
                "No clear signal",
                f"RSI neutral: {conditions.rsi:.1f}",
                "Wait for better setup"
            ])
        
        # Apply confidence adjustments
        if signal == SignalType.BUY and conditions.rsi < config.rsi_oversold:
            confidence = min(0.9, confidence + config.oversold_boost)
        
        if signal == SignalType.BUY and is_uptrend:
            confidence = min(0.9, confidence + config.trend_boost)
        
        confidence = max(0.1, min(0.9, confidence))
        
        metadata = {
            "rsi": conditions.rsi,
            "current_price": conditions.current_price,
            "signal_strength": confidence
        }
        
        return SignalResult(signal=signal, confidence=confidence, reasoning=reasoning, metadata=metadata)
    
    def _apply_symbol_adjustments(self, symbol: Optional[str]) -> SignalConfig:
        """Apply symbol-specific adjustments"""
        config = SignalConfig(
            rsi_oversold=self.config.rsi_oversold,
            rsi_overbought=self.config.rsi_overbought,
            rsi_moderately_oversold=self.config.rsi_moderately_oversold,
            rsi_mildly_oversold=self.config.rsi_mildly_oversold,
            max_volatility=self.config.max_volatility,
            oversold_boost=self.config.oversold_boost,
            trend_boost=self.config.trend_boost
        )
        
        if symbol == "TQQQ":
            config.rsi_oversold = 55  # Much more aggressive
            config.rsi_moderately_oversold = 35
            config.rsi_mildly_oversold = 50
            config.max_volatility = 10.0
            config.oversold_boost = 0.15
        
        return config

def create_market_conditions(rsi: float, sma_20: float, sma_50: float, 
                            current_price: float, recent_change: float,
                            macd: float = 0.0, macd_signal: float = 0.0,
                            volatility: float = 2.0) -> MarketConditions:
    """Create market conditions for testing"""
    return MarketConditions(
        rsi=rsi,
        sma_20=sma_20,
        sma_50=sma_50,
        current_price=current_price,
        recent_change=recent_change,
        macd=macd,
        macd_signal=macd_signal,
        volatility=volatility
    )

def demonstrate_dry_approach():
    """Demonstrate the DRY approach"""
    
    print("🎯 DRY and Testable Signal Calculation Demo")
    print("=" * 60)
    
    calculator = SignalCalculator()
    
    # Test scenarios
    scenarios = [
        ("Neutral", create_market_conditions(50, 100, 100, 100, 0.01)),
        ("Oversold", create_market_conditions(25, 100, 100, 100, -0.03)),
        ("Overbought", create_market_conditions(75, 100, 100, 100, 0.03)),
        ("Uptrend", create_market_conditions(45, 102, 100, 103, 0.01, 0.5, 0.3)),
        ("Downtrend", create_market_conditions(55, 98, 100, 97, -0.01, -0.5, -0.3)),
    ]
    
    print("\n📊 Testing Core Signal Calculator:")
    print("-" * 40)
    
    for name, conditions in scenarios:
        result = calculator.calculate_signal(conditions)
        print(f"{name:12}: {result.signal.value:4} ({result.confidence:.2f}) - {result.reasoning[0][:50]}...")
    
    print("\n🔧 Testing Symbol-Specific Adjustments:")
    print("-" * 40)
    
    test_conditions = create_market_conditions(50, 100, 100, 100, 0.01)
    
    generic_result = calculator.calculate_signal(test_conditions, symbol="GENERIC")
    tqqq_result = calculator.calculate_signal(test_conditions, symbol="TQQQ")
    
    print(f"Generic: {generic_result.signal.value:4} ({generic_result.confidence:.2f})")
    print(f"TQQQ   : {tqqq_result.signal.value:4} ({tqqq_result.confidence:.2f})")
    
    print("\n⚙️ Testing Different Configurations:")
    print("-" * 40)
    
    aggressive_config = SignalConfig(rsi_oversold=60, max_volatility=15.0, oversold_boost=0.25)
    conservative_config = SignalConfig(rsi_oversold=25, max_volatility=3.0, oversold_boost=0.05)
    
    aggressive_calc = SignalCalculator(aggressive_config)
    conservative_calc = SignalCalculator(conservative_config)
    
    test_conditions = create_market_conditions(45, 100, 100, 100, -0.02)
    
    aggressive_result = aggressive_calc.calculate_signal(test_conditions)
    conservative_result = conservative_calc.calculate_signal(test_conditions)
    
    print(f"Aggressive  : {aggressive_result.signal.value:4} ({aggressive_result.confidence:.2f})")
    print(f"Conservative: {conservative_result.signal.value:4} ({conservative_result.confidence:.2f})")
    
    print("\n📈 Signal Distribution Analysis:")
    print("-" * 40)
    
    # Test 100 random scenarios
    buy_count = sell_count = hold_count = 0
    
    for i in range(100):
        # Random conditions
        rsi = np.random.uniform(20, 80)
        sma_20 = np.random.uniform(95, 105)
        sma_50 = np.random.uniform(95, 105)
        current_price = np.random.uniform(95, 105)
        recent_change = np.random.uniform(-0.05, 0.05)
        macd = np.random.uniform(-1, 1)
        macd_signal = np.random.uniform(-1, 1)
        volatility = np.random.uniform(1, 10)
        
        conditions = create_market_conditions(
            rsi, sma_20, sma_50, current_price, recent_change, macd, macd_signal, volatility
        )
        
        result = calculator.calculate_signal(conditions, symbol="TQQQ")
        
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
    
    # Check target
    buy_rate = buy_count / total * 100
    if 25 <= buy_rate <= 45:
        print(f"  ✅ BUY rate {buy_rate:.1f}% is within target range (25-45%)")
    else:
        print(f"  ⚠️  BUY rate {buy_rate:.1f}% is outside target range (25-45%)")
    
    print("\n✅ Benefits of DRY Approach:")
    print("  • Single source of truth for signal logic")
    print("  • Easy to test with different parameters")
    print("  • Reusable across multiple engines")
    print("  • Consistent behavior across symbols")
    print("  • Simple to maintain and update")
    print("  • Configurable for different strategies")

if __name__ == "__main__":
    demonstrate_dry_approach()
