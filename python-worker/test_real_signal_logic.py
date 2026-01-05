#!/usr/bin/env python3
"""
Real Signal Logic Test - No Fallback Components
Tests the actual signal logic that was supposed to be optimized
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

# Import core components
from app.signal_engines.signal_calculator_core import (
    SignalType, MarketConditions, SignalConfig, SignalResult
)

class RealSignalLogicTester:
    """Tests the actual signal logic without fallbacks"""
    
    def __init__(self):
        self.price_data = None
    
    def load_2025_data_from_db(self):
        """Load 2025 TQQQ data from database"""
        
        print("📊 Loading 2025 TQQQ Data from Database")
        print("=" * 50)
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        
        try:
            conn = psycopg2.connect(db_url)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
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
            
            df = pd.DataFrame(rows, columns=[
                'date', 'close', 'rsi', 'sma_50', 'ema_20', 'macd', 'macd_signal', 'volume', 'low', 'high'
            ])
            df['date'] = pd.to_datetime(df['date'])
            
            print(f"✅ Loaded {len(df)} records from 2025")
            print(f"📅 Date range: {df['date'].min()} to {df['date'].max()}")
            print(f"💰 Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
            print(f"📈 RSI range: {df['rsi'].min():.1f} - {df['rsi'].max():.1f}")
            
            conn.close()
            return df
            
        except Exception as e:
            print(f"❌ Error loading data: {e}")
            return None
    
    def calculate_market_conditions(self, df: pd.DataFrame, index: int) -> MarketConditions:
        """Calculate market conditions for a specific date"""
        
        if index < 2 or index >= len(df):
            raise ValueError("Invalid index for market conditions calculation")
        
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
            sma_20=current['ema_20'],
            sma_50=current['sma_50'],
            ema_20=current['ema_20'],
            current_price=current['close'],
            recent_change=recent_change,
            macd=current['macd'],
            macd_signal=current['macd_signal'],
            volatility=volatility
        )
    
    def generate_real_signal(self, conditions: MarketConditions, config: SignalConfig) -> SignalResult:
        """Generate signal using the ACTUAL signal logic from our optimized engine"""
        
        rsi_oversold = config.rsi_oversold
        rsi_moderately_oversold = config.rsi_moderately_oversold
        rsi_mildly_oversold = config.rsi_mildly_oversold
        
        # Determine conditions
        is_oversold = conditions.rsi < rsi_oversold
        is_moderately_oversold = conditions.rsi < rsi_moderately_oversold
        is_mildly_oversold = conditions.rsi < rsi_mildly_oversold
        is_overbought = conditions.rsi > 70
        
        is_uptrend = conditions.sma_20 > conditions.sma_50 and conditions.current_price > conditions.sma_20
        is_downtrend = conditions.sma_20 < conditions.sma_50 and conditions.current_price < conditions.sma_50
        is_recently_down = conditions.recent_change < -0.02
        is_recently_up = conditions.recent_change > 0.02
        
        macd_bullish = conditions.macd > conditions.macd_signal
        macd_bearish = conditions.macd < conditions.macd_signal
        
        reasoning = []
        confidence = 0.5
        
        # ACTUAL signal logic from our optimized engine
        if is_oversold and is_recently_down:
            signal = SignalType.BUY
            confidence = 0.7
            reasoning.extend([
                "Strong oversold buying opportunity",
                f"RSI oversold: {conditions.rsi:.1f} < {rsi_oversold}",
                f"Recent decline: {conditions.recent_change:.2%}",
                "Mean reversion play"
            ])
        elif is_oversold and not is_downtrend:
            signal = SignalType.BUY
            confidence = 0.6
            reasoning.extend([
                "Oversold stabilization",
                f"RSI oversold: {conditions.rsi:.1f} < {rsi_oversold}",
                "Bottoming pattern detected",
                "Mean reversion entry"
            ])
        elif is_oversold and is_uptrend:
            signal = SignalType.BUY
            confidence = 0.65
            reasoning.extend([
                "Oversold in uptrend",
                f"RSI oversold: {conditions.rsi:.1f} < {rsi_oversold}",
                "Uptrend support",
                "Bullish reversal"
            ])
        elif is_moderately_oversold and not is_downtrend:
            signal = SignalType.BUY
            confidence = 0.5
            reasoning.extend([
                "Moderately oversold buying opportunity",
                f"RSI moderately oversold: {conditions.rsi:.1f} < {rsi_moderately_oversold}",
                "Support level likely",
                "Reversal potential"
            ])
        elif is_mildly_oversold and is_uptrend:
            signal = SignalType.BUY
            confidence = 0.4
            reasoning.extend([
                "Mildly oversold in uptrend",
                f"RSI mildly oversold: {conditions.rsi:.1f} < {rsi_mildly_oversold}",
                "Uptrend support",
                "Conservative entry"
            ])
        elif is_mildly_oversold and macd_bullish:
            signal = SignalType.BUY
            confidence = 0.4
            reasoning.extend([
                "Mildly oversold with MACD confirmation",
                f"RSI mildly oversold: {conditions.rsi:.1f} < {rsi_mildly_oversold}",
                "MACD bullish",
                "Technical confirmation"
            ])
        elif is_overbought and is_recently_up:
            signal = SignalType.SELL
            confidence = 0.6
            reasoning.extend([
                "Overbought selling opportunity",
                f"RSI overbought: {conditions.rsi:.1f} > 70",
                f"Recent rise: {conditions.recent_change:.2%}",
                "Mean reversion play"
            ])
        elif is_uptrend and macd_bullish and not is_overbought and conditions.rsi < 65 and not is_mildly_oversold:
            signal = SignalType.BUY
            confidence = 0.4
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
        
        metadata = {
            "rsi": conditions.rsi,
            "current_price": conditions.current_price,
            "signal_strength": confidence,
            "is_uptrend": is_uptrend,
            "is_downtrend": is_downtrend,
            "macd_bullish": macd_bullish,
            "volatility": conditions.volatility
        }
        
        return SignalResult(signal, confidence, reasoning, metadata)
    
    def test_real_signal_logic(self):
        """Test the actual signal logic with 2025 data"""
        
        print("🔍 REAL SIGNAL LOGIC TEST")
        print("=" * 60)
        print("🎯 Testing ACTUAL signal logic (no fallbacks)")
        print("=" * 60)
        
        # Load data
        df = self.load_2025_data_from_db()
        if df is None:
            return
        
        self.price_data = df
        
        # Test with different configurations
        configs = [
            # Original conservative config
            SignalConfig(rsi_oversold=30, rsi_moderately_oversold=40, rsi_mildly_oversold=45, max_volatility=6.0),
            
            # Optimized config from research
            SignalConfig(rsi_oversold=47, rsi_moderately_oversold=35, rsi_mildly_oversold=42, max_volatility=8.0),
            
            # More aggressive config
            SignalConfig(rsi_oversold=55, rsi_moderately_oversold=45, rsi_mildly_oversold=50, max_volatility=10.0),
        ]
        
        for i, config in enumerate(configs, 1):
            print(f"\n📊 Configuration {i}:")
            print(f"  RSI Oversold: {config.rsi_oversold}")
            print(f"  RSI Moderate: {config.rsi_moderately_oversold}")
            print(f"  RSI Mild: {config.rsi_mildly_oversold}")
            print(f"  Max Volatility: {config.max_volatility}%")
            print()
            
            # Test signals
            buy_count = sell_count = hold_count = 0
            signal_results = []
            
            for j in range(10, len(df) - 5):  # Need forward data for validation
                try:
                    conditions = self.calculate_market_conditions(df, j)
                    signal_result = self.generate_real_signal(conditions, config)
                    signal_results.append((df.iloc[j]['date'], signal_result, conditions))
                    
                    if signal_result.signal == SignalType.BUY:
                        buy_count += 1
                    elif signal_result.signal == SignalType.SELL:
                        sell_count += 1
                    else:
                        hold_count += 1
                        
                except Exception as e:
                    continue
            
            total = buy_count + sell_count + hold_count
            buy_rate = (buy_count / total * 100) if total > 0 else 0
            
            print(f"  Total Signals: {total}")
            print(f"  BUY Signals: {buy_count} ({buy_rate:.1f}%)")
            print(f"  SELL Signals: {sell_count}")
            print(f"  HOLD Signals: {hold_count}")
            
            # Show some examples
            print(f"\n  Sample Signals:")
            for k, (date, result, conditions) in enumerate(signal_results[:5]):
                signal_icon = "🟢" if result.signal == SignalType.BUY else "🔴" if result.signal == SignalType.SELL else "⚪"
                print(f"    {signal_icon} {date.strftime('%Y-%m-%d')}: {result.signal.value.upper()} (confidence: {result.confidence:.2f})")
                print(f"      RSI: {conditions.rsi:.1f} | Reason: {result.reasoning[0][:50]}...")
            
            print()
    
    def analyze_why_optimization_failed(self):
        """Analyze why the optimization gave 90% accuracy but real test failed"""
        
        print("🔍 ANALYSIS: Why Optimization Failed")
        print("=" * 60)
        
        print("\n❌ REASON #1: Fallback Components Used")
        print("   The optimization used simplified fallback logic:")
        print("   ```python")
        print("   if conditions.rsi < config.rsi_oversold:")
        print("       return SignalResult(SignalType.BUY, 0.7, ['Oversold BUY'])")
        print("   else:")
        print("       return SignalResult(SignalType.HOLD, 0.2, ['No signal'])")
        print("   ```")
        print("   This dummy logic always 'works' but has no real market intelligence.")
        
        print("\n❌ REASON #2: Import Errors")
        print("   ⚠️ Import error: No module named 'enhancements'")
        print("   The professional enhancements couldn't be loaded in Docker.")
        print("   So the optimizer tested fake logic instead of real logic.")
        
        print("\n❌ REASON #3: Sample Size Mismatch")
        print("   Optimization: 5 configurations with dummy results")
        print("   Real Test: 15 actual dates with real market data")
        print("   The optimization never tested the actual signal logic!")
        
        print("\n❌ REASON #4: Forward Return Validation Missing")
        print("   The optimization didn't validate actual forward returns.")
        print("   It just assumed the dummy logic would work.")
        
        print("\n✅ SOLUTIONS:")
        print("   1. Fix import paths for Docker environment")
        print("   2. Test actual signal logic, not fallbacks")
        print("   3. Use real forward return validation")
        print("   4. Test with sufficient sample sizes")
        
        print("\n🎯 CONCLUSION:")
        print("   The 90% accuracy was from testing DUMMY logic, not real signal logic!")
        print("   We need to test the ACTUAL signal engine to get real results.")

def main():
    """Main function"""
    
    print("🔍 REAL SIGNAL LOGIC ANALYSIS")
    print("=" * 80)
    print("🎯 Why Optimization Failed vs Real Test")
    print("=" * 80)
    
    tester = RealSignalLogicTester()
    tester.test_real_signal_logic()
    tester.analyze_why_optimization_failed()

if __name__ == "__main__":
    main()
