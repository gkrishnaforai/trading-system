#!/usr/bin/env python3
"""
Core Signal Calculation Logic - DRY and Testable
Centralized signal generation logic that can be reused across engines
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from enum import Enum
import pandas as pd

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
    ema_20: float
    current_price: float
    recent_change: float  # % change over last 3 days
    macd: float
    macd_signal: float
    volatility: float  # Daily volatility %
    vix_level: float = 20.0  # VIX level for fear/greed analysis
    volatility_trend: str = "stable"  # 'rising', 'falling', 'stable'
    
    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> 'MarketConditions':
        """Create MarketConditions from DataFrame"""
        if df.empty:
            raise ValueError("Empty DataFrame provided")
        
        current_price = df['close'].iloc[-1]
        recent_data = df.tail(3)
        recent_change = (current_price - recent_data['close'].iloc[0]) / recent_data['close'].iloc[0]
        
        return cls(
            rsi=df['rsi'].iloc[-1] if 'rsi' in df.columns else df['rsi_14'].iloc[-1] if 'rsi_14' in df.columns else 50,
            sma_20=df['sma_20'].iloc[-1] if 'sma_20' in df.columns else current_price,
            sma_50=df['sma_50'].iloc[-1] if 'sma_50' in df.columns else current_price,
            ema_20=df['ema_20'].iloc[-1] if 'ema_20' in df.columns else current_price,
            current_price=current_price,
            recent_change=recent_change,
            macd=df['macd'].iloc[-1] if 'macd' in df.columns else 0,
            macd_signal=df['macd_signal'].iloc[-1] if 'macd_signal' in df.columns else 0,
            volatility=df['close'].pct_change().tail(20).std() * 100 if len(df) > 20 else 2.0
        )

@dataclass
class SignalConfig:
    """Configuration for signal calculation"""
    # RSI thresholds
    rsi_oversold: float = 30
    rsi_overbought: float = 70
    rsi_moderately_oversold: float = 40
    rsi_mildly_oversold: float = 45
    
    # Volatility thresholds
    max_volatility: float = 6.0  # Max daily volatility %
    
    # Confidence adjustments
    oversold_boost: float = 0.1
    trend_boost: float = 0.1
    confluence_boost: float = 0.05

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
                        regime: Optional[str] = None,
                        symbol: Optional[str] = None) -> SignalResult:
        """
        Calculate signal based on market conditions
        
        Args:
            conditions: Market conditions data
            regime: Market regime (optional)
            symbol: Symbol being analyzed (optional)
            
        Returns:
            SignalResult with signal, confidence, and reasoning
        """
        # Apply symbol-specific adjustments
        adjusted_config = self._apply_symbol_adjustments(symbol)
        
        # Calculate base signal
        signal, confidence, reasoning = self._calculate_base_signal(
            conditions, adjusted_config
        )
        
        # Apply regime-specific logic
        if regime:
            signal, confidence, reasoning = self._apply_regime_logic(
                signal, confidence, reasoning, conditions, regime, adjusted_config
            )
        
        # Apply final confidence adjustments
        confidence = self._adjust_confidence(
            confidence, conditions, signal, adjusted_config
        )
        
        # Create metadata
        metadata = self._create_metadata(conditions, signal, confidence)
        
        return SignalResult(
            signal=signal,
            confidence=confidence,
            reasoning=reasoning,
            metadata=metadata
        )
    
    def _apply_symbol_adjustments(self, symbol: Optional[str]) -> SignalConfig:
        """Apply symbol-specific configuration adjustments"""
        config = SignalConfig(
            rsi_oversold=self.config.rsi_oversold,
            rsi_overbought=self.config.rsi_overbought,
            rsi_moderately_oversold=self.config.rsi_moderately_oversold,
            rsi_mildly_oversold=self.config.rsi_mildly_oversold,
            max_volatility=self.config.max_volatility,
            oversold_boost=self.config.oversold_boost,
            trend_boost=self.config.trend_boost,
            confluence_boost=self.config.confluence_boost
        )
        
        # TQQQ-specific aggressive adjustments
        if symbol == "TQQQ":
            config.rsi_oversold = 55  # Much more aggressive
            config.rsi_moderately_oversold = 35
            config.rsi_mildly_oversold = 50
            config.max_volatility = 10.0  # Allow higher volatility
            config.oversold_boost = 0.15  # Higher boost for oversold
        
        return config
    
    def _calculate_base_signal(self, conditions: MarketConditions, 
                             config: SignalConfig) -> Tuple[SignalType, float, List[str]]:
        """Calculate base signal without regime consideration"""
        reasoning = []
        confidence = 0.5
        
        # Check volatility filter
        if conditions.volatility > config.max_volatility:
            return SignalType.HOLD, 0.1, [
                f"HOLD: Volatility too high: {conditions.volatility:.1f}% > {config.max_volatility:.1f}%"
            ]
        
        # Determine oversold/overbought conditions
        is_oversold = conditions.rsi < config.rsi_oversold
        is_moderately_oversold = conditions.rsi < config.rsi_moderately_oversold
        is_mildly_oversold = conditions.rsi < config.rsi_mildly_oversold
        is_overbought = conditions.rsi > config.rsi_overbought
        
        # Determine trend
        is_uptrend = conditions.sma_20 > conditions.sma_50 and conditions.current_price > conditions.sma_20
        is_downtrend = conditions.sma_20 < conditions.sma_50 and conditions.current_price < conditions.sma_20
        is_recently_down = conditions.recent_change < -0.02
        is_recently_up = conditions.recent_change > 0.02
        
        # MACD confirmation
        macd_bullish = conditions.macd > conditions.macd_signal
        macd_bearish = conditions.macd < conditions.macd_signal
        
        # Base signal logic
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
        
        return signal, confidence, reasoning
    
    def _apply_regime_logic(self, signal: SignalType, confidence: float, 
                          reasoning: List[str], conditions: MarketConditions,
                          regime: str, config: SignalConfig) -> Tuple[SignalType, float, List[str]]:
        """Apply regime-specific signal adjustments"""
        
        if regime == "TRENDING_UP":
            # More aggressive BUY signals in uptrend
            if signal == SignalType.BUY:
                confidence = min(0.8, confidence + 0.1)
                reasoning.append("Uptrend regime boost")
            elif signal == SignalType.SELL:
                confidence = max(0.3, confidence - 0.1)
                reasoning.append("Uptrend regime - cautious on SELL")
                
        elif regime == "TRENDING_DOWN":
            # More aggressive SELL signals in downtrend
            if signal == SignalType.SELL:
                confidence = min(0.8, confidence + 0.1)
                reasoning.append("Downtrend regime boost")
            elif signal == SignalType.BUY:
                confidence = max(0.3, confidence - 0.1)
                reasoning.append("Downtrend regime - cautious on BUY")
                
        elif regime == "RANGE_BOUND":
            # Mean reversion focus in range-bound
            if conditions.rsi < config.rsi_oversold:
                signal = SignalType.BUY
                confidence = 0.6
                reasoning.append("Range-bound oversold - mean reversion")
            elif conditions.rsi > config.rsi_overbought:
                signal = SignalType.SELL
                confidence = 0.6
                reasoning.append("Range-bound overbought - mean reversion")
            else:
                signal = SignalType.HOLD
                confidence = 0.2
                reasoning.append("Range-bound - wait for extremes")
        
        return signal, confidence, reasoning
    
    def _adjust_confidence(self, confidence: float, conditions: MarketConditions,
                         signal: SignalType, config: SignalConfig) -> float:
        """Apply final confidence adjustments"""
        
        # Oversold boost for BUY signals
        if signal == SignalType.BUY and conditions.rsi < config.rsi_oversold:
            confidence = min(0.9, confidence + config.oversold_boost)
        
        # Trend boost
        is_uptrend = conditions.sma_20 > conditions.sma_50 and conditions.current_price > conditions.sma_20
        if signal == SignalType.BUY and is_uptrend:
            confidence = min(0.9, confidence + config.trend_boost)
        
        # Confluence boost (multiple indicators aligned)
        macd_bullish = conditions.macd > conditions.macd_signal
        if signal == SignalType.BUY and is_uptrend and macd_bullish:
            confidence = min(0.9, confidence + config.confluence_boost)
        
        return max(0.1, min(0.9, confidence))  # Clamp between 0.1 and 0.9
    
    def _create_metadata(self, conditions: MarketConditions, 
                        signal: SignalType, confidence: float) -> Dict[str, float]:
        """Create metadata for the signal"""
        return {
            "rsi": conditions.rsi,
            "sma_20": conditions.sma_20,
            "sma_50": conditions.sma_50,
            "current_price": conditions.current_price,
            "recent_change_pct": conditions.recent_change * 100,
            "volatility_pct": conditions.volatility,
            "macd": conditions.macd,
            "macd_signal": conditions.macd_signal,
            "signal_strength": confidence
        }

# Testable interface
def calculate_signal_from_dataframe(df: pd.DataFrame, 
                                  regime: Optional[str] = None,
                                  symbol: Optional[str] = None,
                                  config: Optional[SignalConfig] = None) -> SignalResult:
    """
    Convenience function to calculate signal from DataFrame
    
    Args:
        df: DataFrame with OHLCV and indicator data
        regime: Market regime (optional)
        symbol: Symbol being analyzed (optional)
        config: Signal configuration (optional)
    
    Returns:
        SignalResult with calculated signal
    """
    calculator = SignalCalculator(config)
    conditions = MarketConditions.from_dataframe(df)
    return calculator.calculate_signal(conditions, regime, symbol)

# Example usage and testing
if __name__ == "__main__":
    # Example test case
    import numpy as np
    
    # Create sample data
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    np.random.seed(42)
    
    # Generate realistic price data
    price = 100 + np.cumsum(np.random.randn(100) * 2)
    rsi = 30 + np.random.rand(100) * 40  # RSI between 30-70
    
    df = pd.DataFrame({
        'date': dates,
        'open': price * (1 + np.random.rand(100) * 0.01 - 0.005),
        'high': price * (1 + np.random.rand(100) * 0.02),
        'low': price * (1 - np.random.rand(100) * 0.02),
        'close': price,
        'volume': np.random.randint(1000000, 5000000, 100),
        'rsi': rsi,
        'sma_20': price + np.random.randn(100) * 5,
        'sma_50': price + np.random.randn(100) * 8,
        'ema_20': price + np.random.randn(100) * 3,
        'macd': np.random.randn(100) * 2,
        'macd_signal': np.random.randn(100) * 2
    })
    
    # Test signal calculation
    result = calculate_signal_from_dataframe(
        df, 
        regime="TRENDING_UP", 
        symbol="TQQQ"
    )
    
    print(f"Signal: {result.signal.value}")
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Reasoning: {' | '.join(result.reasoning)}")
    print(f"Metadata: {result.metadata}")
