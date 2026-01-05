#!/usr/bin/env python3
"""
Configuration Optimizer for 30-40% BUY Rate Target
Systematically tests multiple parameter combinations to find optimal settings
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
import json

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

@dataclass
class OptimizationResult:
    """Result of configuration optimization"""
    config: SignalConfig
    buy_rate: float
    sell_rate: float
    hold_rate: float
    target_score: float  # How close to target (lower is better)
    status: str

class ConfigurableSignalCalculator:
    """Configurable signal calculator for optimization"""
    
    def __init__(self, config: SignalConfig):
        self.config = config
    
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
        
        # Signal logic
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
            signal = SignalType.BUY
            confidence = 0.6
            reasoning.extend([
                "Oversold stabilization",
                f"RSI oversold: {conditions.rsi:.1f}",
                "Bottoming pattern detected",
                "Mean reversion entry"
            ])
        elif is_moderately_oversold and not is_downtrend:
            signal = SignalType.BUY
            confidence = 0.5
            reasoning.extend([
                "Moderately oversold buying opportunity",
                f"RSI moderately oversold: {conditions.rsi:.1f}",
                "Support level likely",
                "Reversal potential"
            ])
        elif is_mildly_oversold and is_uptrend:
            signal = SignalType.BUY
            confidence = 0.4
            reasoning.extend([
                "Mildly oversold in uptrend",
                f"RSI mildly oversold: {conditions.rsi:.1f}",
                "Uptrend support",
                "Conservative entry"
            ])
        elif is_mildly_oversold and macd_bullish:
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
            # Apply TQQQ-specific adjustments
            config.rsi_oversold = self.config.rsi_oversold
            config.rsi_moderately_oversold = self.config.rsi_moderately_oversold
            config.rsi_mildly_oversold = self.config.rsi_mildly_oversold
            config.max_volatility = self.config.max_volatility
            config.oversold_boost = self.config.oversold_boost
            config.trend_boost = self.config.trend_boost
        
        return config

class ConfigurationOptimizer:
    """Optimizes signal configuration to hit target BUY rate"""
    
    def __init__(self):
        self.target_buy_rate_min = 30.0
        self.target_buy_rate_max = 40.0
        self.results = []
    
    def get_2025_data_from_db(self):
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
    
    def calculate_market_conditions(self, df: pd.DataFrame, index: int) -> MarketConditions:
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
    
    def test_configuration(self, config: SignalConfig, df: pd.DataFrame) -> OptimizationResult:
        """Test a single configuration and return results"""
        
        calculator = ConfigurableSignalCalculator(config)
        
        buy_count = sell_count = hold_count = 0
        
        # Test every 5th day to avoid too many calculations
        for i in range(2, len(df), 5):
            try:
                conditions = self.calculate_market_conditions(df, i)
                result = calculator.calculate_signal(conditions, symbol="TQQQ")
                
                if result.signal == SignalType.BUY:
                    buy_count += 1
                elif result.signal == SignalType.SELL:
                    sell_count += 1
                else:
                    hold_count += 1
                    
            except Exception as e:
                continue  # Skip errors
        
        total = buy_count + sell_count + hold_count
        buy_rate = (buy_count / total * 100) if total > 0 else 0
        sell_rate = (sell_count / total * 100) if total > 0 else 0
        hold_rate = (hold_count / total * 100) if total > 0 else 0
        
        # Calculate target score (how close to target range)
        if self.target_buy_rate_min <= buy_rate <= self.target_buy_rate_max:
            target_score = 0  # Perfect
            status = "PERFECT"
        elif buy_rate < self.target_buy_rate_min:
            target_score = self.target_buy_rate_min - buy_rate  # How far below target
            status = "TOO_LOW"
        else:
            target_score = buy_rate - self.target_buy_rate_max  # How far above target
            status = "TOO_HIGH"
        
        return OptimizationResult(
            config=config,
            buy_rate=buy_rate,
            sell_rate=sell_rate,
            hold_rate=hold_rate,
            target_score=target_score,
            status=status
        )
    
    def generate_configurations(self) -> List[SignalConfig]:
        """Generate multiple configuration combinations to test"""
        
        configurations = []
        
        # Based on our previous testing, we know:
        # - RSI 45 gave 9.5% (too low)
        # - RSI 48 gave ~? (need to test)
        # - RSI 52 gave 50% (too high)
        
        # Let's test RSI oversold values from 45 to 52
        rsi_oversold_values = [45, 46, 47, 48, 49, 50, 51, 52]
        
        # Test different moderate oversold values
        rsi_moderate_values = [35, 36, 37, 38, 39, 40]
        
        # Test different mild oversold values
        rsi_mild_values = [42, 43, 44, 45, 46, 47]
        
        # Test different volatility thresholds
        volatility_values = [8.0, 8.5, 9.0, 9.5, 10.0]
        
        # Generate combinations (focus on most promising ranges)
        for rsi_oversold in rsi_oversold_values:
            for rsi_moderate in rsi_moderate_values:
                for rsi_mild in rsi_mild_values:
                    # Ensure proper hierarchy: moderate < mild < oversold
                    if rsi_moderate < rsi_mild < rsi_oversold:
                        for volatility in volatility_values:
                            config = SignalConfig(
                                rsi_oversold=rsi_oversold,
                                rsi_moderately_oversold=rsi_moderate,
                                rsi_mildly_oversold=rsi_mild,
                                max_volatility=volatility,
                                oversold_boost=0.12,
                                trend_boost=0.1
                            )
                            configurations.append(config)
        
        print(f"🔧 Generated {len(configurations)} configuration combinations")
        return configurations
    
    def optimize(self):
        """Run optimization to find best configuration"""
        
        print("🎯 Configuration Optimizer for 30-40% BUY Rate Target")
        print("=" * 60)
        
        # Load data
        df = self.get_2025_data_from_db()
        if df is None:
            return
        
        # Generate configurations
        configurations = self.generate_configurations()
        
        print(f"\n🔍 Testing Configurations...")
        print("-" * 50)
        
        best_results = []
        perfect_results = []
        
        # Test each configuration
        for i, config in enumerate(configurations):
            result = self.test_configuration(config, df)
            self.results.append(result)
            
            # Track best results
            if result.status == "PERFECT":
                perfect_results.append(result)
            elif result.target_score < 10:  # Within 10% of target
                best_results.append(result)
            
            # Progress update
            if (i + 1) % 50 == 0:
                print(f"  Tested {i + 1}/{len(configurations)} configurations...")
        
        # Sort results by target score
        self.results.sort(key=lambda x: x.target_score)
        
        print(f"\n📊 Optimization Results:")
        print("-" * 50)
        print(f"  Total configurations tested: {len(configurations)}")
        print(f"  Perfect matches (30-40%): {len(perfect_results)}")
        print(f"  Close matches (±10%): {len(best_results)}")
        
        # Show top 5 results
        print(f"\n🏆 Top 5 Configuration Results:")
        print("-" * 50)
        
        for i, result in enumerate(self.results[:5]):
            print(f"  {i+1}. BUY: {result.buy_rate:.1f}% | Status: {result.status}")
            print(f"     RSI Oversold: {result.config.rsi_oversold}, Moderate: {result.config.rsi_moderately_oversold}, Mild: {result.config.rsi_mildly_oversold}")
            print(f"     Max Volatility: {result.config.max_volatility:.1f}%")
            print(f"     Target Score: {result.target_score:.1f}")
            print()
        
        # Show perfect matches if any
        if perfect_results:
            print(f"✅ Perfect Matches (30-40% BUY Rate):")
            print("-" * 50)
            for i, result in enumerate(perfect_results[:3]):
                print(f"  {i+1}. BUY: {result.buy_rate:.1f}% | SELL: {result.sell_rate:.1f}% | HOLD: {result.hold_rate:.1f}%")
                print(f"     RSI Oversold: {result.config.rsi_oversold}")
                print(f"     RSI Moderate: {result.config.rsi_moderately_oversold}")
                print(f"     RSI Mild: {result.config.rsi_mildly_oversold}")
                print(f"     Max Volatility: {result.config.max_volatility:.1f}%")
                print()
        
        # Generate final recommendation
        self.generate_recommendation()
    
    def generate_recommendation(self):
        """Generate final recommendation based on optimization results"""
        
        print(f"🎯 FINAL OPTIMIZATION RECOMMENDATION:")
        print("=" * 60)
        
        # Find best result
        best_result = self.results[0] if self.results else None
        
        if not best_result:
            print("❌ No results available for recommendation")
            return
        
        # Check if we have perfect matches
        perfect_matches = [r for r in self.results if r.status == "PERFECT"]
        
        if perfect_matches:
            # Choose the perfect match with highest BUY rate (more aggressive)
            best_perfect = max(perfect_matches, key=lambda x: x.buy_rate)
            
            print(f"✅ RECOMMENDED CONFIGURATION:")
            print("-" * 50)
            print(f"  Status: PERFECT MATCH")
            print(f"  BUY Rate: {best_perfect.buy_rate:.1f}% (within target 30-40%)")
            print(f"  SELL Rate: {best_perfect.sell_rate:.1f}%")
            print(f"  HOLD Rate: {best_perfect.hold_rate:.1f}%")
            print()
            print(f"  Configuration Parameters:")
            print(f"  • RSI Oversold: {best_perfect.config.rsi_oversold}")
            print(f"  • RSI Moderately Oversold: {best_perfect.config.rsi_moderately_oversold}")
            print(f"  • RSI Mildly Oversold: {best_perfect.config.rsi_mildly_oversold}")
            print(f"  • Max Volatility: {best_perfect.config.max_volatility:.1f}%")
            print(f"  • Oversold Boost: {best_perfect.config.oversold_boost}")
            print(f"  • Trend Boost: {best_perfect.config.trend_boost}")
            
            print(f"\n🚀 DEPLOYMENT STATUS: READY")
            print(f"  ✅ Target BUY rate achieved")
            print(f"  ✅ Configuration optimized")
            print(f"  ✅ Ready for production deployment")
            
        else:
            # No perfect matches, recommend closest
            print(f"⚠️  RECOMMENDED CONFIGURATION:")
            print("-" * 50)
            print(f"  Status: CLOSEST MATCH")
            print(f"  BUY Rate: {best_result.buy_rate:.1f}% (target: 30-40%)")
            print(f"  Distance from target: {best_result.target_score:.1f}%")
            print(f"  SELL Rate: {best_result.sell_rate:.1f}%")
            print(f"  HOLD Rate: {best_result.hold_rate:.1f}%")
            print()
            print(f"  Configuration Parameters:")
            print(f"  • RSI Oversold: {best_result.config.rsi_oversold}")
            print(f"  • RSI Moderately Oversold: {best_result.config.rsi_moderately_oversold}")
            print(f"  • RSI Mildly Oversold: {best_result.config.rsi_mildly_oversold}")
            print(f"  • Max Volatility: {best_result.config.max_volatility:.1f}%")
            
            if best_result.status == "TOO_LOW":
                print(f"\n🔧 SUGGESTED ADJUSTMENTS:")
                print(f"  • Decrease RSI oversold threshold (make more aggressive)")
                print(f"  • Increase volatility tolerance")
                print(f"  • Add more BUY conditions")
            else:
                print(f"\n🔧 SUGGESTED ADJUSTMENTS:")
                print(f"  • Increase RSI oversold threshold (make more conservative)")
                print(f"  • Decrease volatility tolerance")
                print(f"  • Remove some BUY conditions")
        
        print(f"\n📊 OPTIMIZATION SUMMARY:")
        print("-" * 50)
        print(f"  • Configurations tested: {len(self.results)}")
        print(f"  • Perfect matches: {len(perfect_matches)}")
        print(f"  • Best BUY rate: {max(r.buy_rate for r in self.results):.1f}%")
        print(f"  • Worst BUY rate: {min(r.buy_rate for r in self.results):.1f}%")
        print(f"  • Average BUY rate: {np.mean([r.buy_rate for r in self.results]):.1f}%")
        
        print(f"\n✅ Configuration Optimization Complete!")

if __name__ == "__main__":
    optimizer = ConfigurationOptimizer()
    optimizer.optimize()
