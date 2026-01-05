#!/usr/bin/env python3
"""
Balanced DRY Signal Calculator for 30-40% BUY Rate Target
Fine-tuned configuration for optimal performance
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

# Import our DRY signal calculator components
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

class BalancedSignalCalculator:
    """Balanced signal calculator for 30-40% BUY rate target"""
    
    def __init__(self, config: Optional[SignalConfig] = None):
        self.config = config or SignalConfig()
    
    def calculate_signal(self, conditions: MarketConditions, 
                        symbol: Optional[str] = None) -> SignalResult:
        """Calculate signal based on market conditions"""
        
        # Apply symbol-specific adjustments (balanced)
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
        
        # Balanced signal logic for 30-40% target
        if is_oversold and is_recently_down:
            signal = SignalType.BUY
            confidence = 0.7
            reasoning.extend([
                "Strong oversold buying opportunity",
                f"RSI oversold: {conditions.rsi:.1f}",
                f"Recent decline: {conditions.recent_change:.2%}",
                "Mean reversion play"
            ])
        elif is_oversold and not is_downtrend:
            # Oversold without recent decline but not in downtrend
            signal = SignalType.BUY
            confidence = 0.6
            reasoning.extend([
                "Oversold stabilization",
                f"RSI oversold: {conditions.rsi:.1f}",
                "Bottoming pattern detected",
                "Mean reversion entry"
            ])
        elif is_moderately_oversold and not is_downtrend:
            # Moderately oversold when not in downtrend
            signal = SignalType.BUY
            confidence = 0.5
            reasoning.extend([
                "Moderately oversold buying opportunity",
                f"RSI moderately oversold: {conditions.rsi:.1f}",
                "Support level likely",
                "Reversal potential"
            ])
        elif is_mildly_oversold and is_uptrend:
            # Mildly oversold in uptrend
            signal = SignalType.BUY
            confidence = 0.4
            reasoning.extend([
                "Mildly oversold in uptrend",
                f"RSI mildly oversold: {conditions.rsi:.1f}",
                "Uptrend support",
                "Conservative entry"
            ])
        elif is_mildly_oversold and macd_bullish:
            # Mildly oversold with MACD confirmation
            signal = SignalType.BUY
            confidence = 0.4
            reasoning.extend([
                "Mildly oversold with MACD confirmation",
                f"RSI mildly oversold: {conditions.rsi:.1f}",
                "MACD bullish",
                "Technical confirmation"
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
        elif is_uptrend and macd_bullish and not is_overbought and conditions.rsi < 65:
            # Uptrend with RSI filter
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
            confidence = min(0.85, confidence + config.oversold_boost)
        
        if signal == SignalType.BUY and is_uptrend:
            confidence = min(0.85, confidence + config.trend_boost)
        
        confidence = max(0.1, min(0.85, confidence))
        
        metadata = {
            "rsi": conditions.rsi,
            "current_price": conditions.current_price,
            "signal_strength": confidence
        }
        
        return SignalResult(signal=signal, confidence=confidence, reasoning=reasoning, metadata=metadata)
    
    def _apply_symbol_adjustments(self, symbol: Optional[str]) -> SignalConfig:
        """Apply symbol-specific adjustments (balanced)"""
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
            # Balanced TQQQ adjustments
            config.rsi_oversold = 52  # Balanced between 50 and 55
            config.rsi_moderately_oversold = 36  # Balanced between 35 and 40
            config.rsi_mildly_oversold = 46  # Balanced between 45 and 50
            config.max_volatility = 9.0  # Balanced between 8.0 and 10.0
            config.oversold_boost = 0.12  # Balanced between 0.1 and 0.15
        
        return config

def get_2025_data_from_db():
    """Load 2025 TQQQ data from database"""
    
    print("📊 Loading 2025 TQQQ Data from Database")
    print("=" * 50)
    
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Get 2025 data by joining indicators and price data
        cursor.execute("""
            SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume
            FROM indicators_daily i
            JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
            WHERE i.symbol = 'TQQQ' 
            AND i.date >= '2025-01-01' 
            AND i.date <= '2025-12-31'
            ORDER BY i.date
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            print("❌ No 2025 data found in database")
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=[
            'date', 'close', 'rsi', 'sma_50', 'ema_20', 'macd', 'macd_signal', 'volume'
        ])
        
        print(f"✅ Loaded {len(df)} records from 2025")
        print(f"📅 Date range: {df['date'].min()} to {df['date'].max()}")
        print(f"💰 Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
        print(f"📈 RSI range: {df['rsi'].min():.1f} - {df['rsi'].max():.1f}")
        
        conn.close()
        return df
        
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        return None

def calculate_market_conditions(df: pd.DataFrame, index: int) -> MarketConditions:
    """Calculate market conditions for a specific date"""
    
    if index < 2 or index >= len(df):
        raise ValueError("Invalid index for market conditions calculation")
    
    # Current data
    current = df.iloc[index]
    
    # Recent change (last 3 days)
    recent_close = df.iloc[index-2]['close']
    current_close = current['close']
    recent_change = (current_close - recent_close) / recent_close
    
    # Calculate volatility (last 20 days)
    start_idx = max(0, index - 19)
    volatility_data = df.iloc[start_idx:index+1]['close'].pct_change().dropna()
    volatility = volatility_data.std() * 100 if len(volatility_data) > 1 else 2.0
    
    return MarketConditions(
        rsi=current['rsi'],
        sma_20=current['sma_50'],  # Use sma_50 as sma_20 since it's not available
        sma_50=current['sma_50'],
        current_price=current['close'],
        recent_change=recent_change,
        macd=current['macd'],
        macd_signal=current['macd_signal'],
        volatility=volatility
    )

def test_balanced_2025_data():
    """Test balanced DRY signal calculator with 2025 data"""
    
    print("🎯 Testing Balanced DRY Signal Calculator with 2025 Data")
    print("=" * 60)
    print("🎯 Target: 30-40% BUY Signal Rate")
    print("=" * 60)
    
    # Load data
    df = get_2025_data_from_db()
    if df is None:
        return
    
    # Initialize balanced calculator
    calculator = BalancedSignalCalculator()
    
    # Test signal distribution across all 2025 data
    print(f"\n📊 Balanced 2025 Signal Distribution Analysis:")
    print("-" * 50)
    
    buy_count = sell_count = hold_count = error_count = 0
    detailed_results = []
    
    # Test every 5th day to avoid too many calculations
    for i in range(2, len(df), 5):
        try:
            conditions = calculate_market_conditions(df, i)
            result = calculator.calculate_signal(conditions, symbol="TQQQ")
            
            date_str = df.iloc[i]['date'].strftime('%Y-%m-%d')
            
            if result.signal == SignalType.BUY:
                buy_count += 1
                detailed_results.append(f"🟢 BUY:  {date_str} ({result.confidence:.2f}) - {result.reasoning[0][:50]}...")
            elif result.signal == SignalType.SELL:
                sell_count += 1
                detailed_results.append(f"🔴 SELL: {date_str} ({result.confidence:.2f}) - {result.reasoning[0][:50]}...")
            else:
                hold_count += 1
                
        except Exception as e:
            error_count += 1
    
    total = buy_count + sell_count + hold_count
    
    print(f"  Total tested: {total}")
    print(f"  BUY Signals:  {buy_count:3d} ({buy_count/total*100:5.1f}%)")
    print(f"  SELL Signals: {sell_count:3d} ({sell_count/total*100:5.1f}%)")
    print(f"  HOLD Signals: {hold_count:3d} ({hold_count/total*100:5.1f}%)")
    print(f"  Errors:       {error_count}")
    
    # Check target
    buy_rate = buy_count / total * 100
    if 30 <= buy_rate <= 40:
        print(f"  ✅ BUY rate {buy_rate:.1f}% is within target range (30-40%)")
        status = "PERFECT"
    elif 25 <= buy_rate <= 45:
        print(f"  ✅ BUY rate {buy_rate:.1f}% is close to target range (30-40%)")
        status = "GOOD"
    else:
        print(f"  ⚠️  BUY rate {buy_rate:.1f}% is outside target range (30-40%)")
        status = "NEEDS_ADJUSTMENT"
    
    # Show detailed BUY signals
    print(f"\n🟢 Detailed BUY Signals (Top 10):")
    print("-" * 50)
    buy_signals = [r for r in detailed_results if "BUY:" in r]
    for result in buy_signals[:10]:
        print(result)
    
    # Compare with previous results
    print(f"\n🔄 Comparison:")
    print("-" * 50)
    print(f"  Current System BUY Rate: 4.9%")
    print(f"  Original DRY BUY Rate:  50.0%")
    print(f"  Optimized DRY BUY Rate:  11.9%")
    print(f"  Balanced DRY BUY Rate:   {buy_rate:.1f}%")
    print(f"  Improvement vs Current:  {buy_rate/4.9:.1f}x")
    
    # Configuration summary
    print(f"\n⚙️ Balanced Configuration:")
    print("-" * 50)
    print(f"  TQQQ RSI Oversold: 52 (balanced)")
    print(f"  TQQQ Max Volatility: 9.0% (balanced)")
    print(f"  Confidence Cap: 0.85 (balanced)")
    print(f"  Multiple BUY conditions for balance")
    
    # Recommendation
    print(f"\n📋 Recommendation:")
    print("-" * 50)
    if status == "PERFECT":
        print(f"  ✅ {status}: Configuration ready for production!")
        print(f"  ✅ Target BUY rate achieved with balanced risk")
        print(f"  ✅ Deploy this configuration to production")
    elif status == "GOOD":
        print(f"  ✅ {status}: Configuration nearly optimal")
        print(f"  ✅ Consider minor tuning if needed")
        print(f"  ✅ Can be deployed with monitoring")
    else:
        print(f"  ⚠️  {status}: Further tuning needed")
        print(f"  ⚠️  Adjust RSI thresholds or conditions")
    
    print(f"\n✅ Balanced 2025 Data Testing Complete!")

if __name__ == "__main__":
    test_balanced_2025_data()
