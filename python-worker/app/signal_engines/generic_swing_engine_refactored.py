#!/usr/bin/env python3
"""
Refactored Generic Swing Engine using Core Signal Calculator
DRY implementation that uses the centralized signal calculation logic
"""

from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np
from enum import Enum

from app.signal_engines.signal_calculator_core import (
    SignalCalculator, SignalConfig, SignalType, SignalResult,
    calculate_signal_from_dataframe, MarketConditions
)
from app.signal_engines.base import SignalEngine, Signal, MarketContext

class SwingRegime(Enum):
    """Market regimes for swing trading"""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGE_BOUND = "range_bound"
    VOLATILE_CHOP = "volatile_chop"

class RefactoredGenericSwingEngine(SignalEngine):
    """
    Refactored Generic Swing Engine using Core Signal Calculator
    DRY implementation with centralized signal logic
    """
    
    def __init__(self, name: str = "generic_swing_refactored"):
        super().__init__(name)
        self.signal_calculator = SignalCalculator()
    
    def generate_signal(self, symbol: str, data: pd.DataFrame, 
                       context: MarketContext) -> Signal:
        """
        Generate signal using core signal calculator
        
        Args:
            symbol: Trading symbol
            data: Historical price data with indicators
            context: Market context information
            
        Returns:
            Signal object with recommendation
        """
        try:
            # Validate input data
            if data.empty or len(data) < 20:
                return self._create_hold_signal(
                    symbol, context, 
                    "Insufficient data for signal generation"
                )
            
            # Detect market regime
            regime = self._detect_regime(data)
            
            # Calculate signal using core logic
            signal_result = calculate_signal_from_dataframe(
                data, 
                regime=regime.value, 
                symbol=symbol
            )
            
            # Convert to Signal object
            return self._create_signal_from_result(
                symbol, signal_result, context, regime
            )
            
        except Exception as e:
            return self._create_hold_signal(
                symbol, context, 
                f"Signal generation error: {str(e)}"
            )
    
    def _detect_regime(self, data: pd.DataFrame) -> SwingRegime:
        """
        Detect market regime from price data
        
        Args:
            data: Historical price data
            
        Returns:
            Detected market regime
        """
        try:
            # Get recent price data
            recent_data = data.tail(20)
            if len(recent_data) < 10:
                return SwingRegime.RANGE_BOUND
            
            # Calculate trend metrics
            sma_20 = recent_data['sma_20'].iloc[-1] if 'sma_20' in recent_data.columns else recent_data['close'].mean()
            sma_50 = recent_data['sma_50'].iloc[-1] if 'sma_50' in recent_data.columns else recent_data['close'].mean()
            current_price = recent_data['close'].iloc[-1]
            
            # Calculate volatility
            returns = recent_data['close'].pct_change().dropna()
            volatility = returns.std() * np.sqrt(252)  # Annualized volatility
            
            # Determine trend direction
            trend_slope = (sma_20 - sma_50) / sma_50
            price_position = (current_price - sma_50) / sma_50
            
            # Regime detection logic
            if abs(trend_slope) < 0.02 and volatility < 0.25:
                return SwingRegime.RANGE_BOUND
            elif trend_slope > 0.02 and price_position > 0.01:
                return SwingRegime.TRENDING_UP
            elif trend_slope < -0.02 and price_position < -0.01:
                return SwingRegime.TRENDING_DOWN
            elif volatility > 0.35:
                return SwingRegime.VOLATILE_CHOP
            else:
                return SwingRegime.RANGE_BOUND
                
        except Exception:
            return SwingRegime.RANGE_BOUND
    
    def _create_signal_from_result(self, symbol: str, result: SignalResult,
                                 context: MarketContext, regime: SwingRegime) -> Signal:
        """
        Convert SignalResult to Signal object
        
        Args:
            symbol: Trading symbol
            result: Signal calculation result
            context: Market context
            regime: Detected regime
            
        Returns:
            Signal object
        """
        # Calculate position sizing and risk management
        position_size_pct = self._calculate_position_size(result, regime)
        stop_loss, take_profit = self._calculate_risk_management(
            result.metadata['current_price'], result.signal
        )
        
        # Create signal
        signal = Signal(
            symbol=symbol,
            signal=result.signal.value,
            confidence=result.confidence,
            strategy=self.name,
            timestamp=context.timestamp,
            price_at_signal=result.metadata['current_price'],
            position_size_pct=position_size_pct,
            timeframe="swing",
            entry_price_range=(
                result.metadata['current_price'] * 0.998,
                result.metadata['current_price'] * 1.002
            ),
            stop_loss=stop_loss,
            take_profit=take_profit,
            reasoning=result.reasoning,
            metadata={
                "regime": regime.value,
                "market_conditions": result.metadata,
                "signal_strength": result.confidence
            }
        )
        
        return signal
    
    def _calculate_position_size(self, result: SignalResult, regime: SwingRegime) -> float:
        """
        Calculate position size based on signal confidence and regime
        
        Args:
            result: Signal calculation result
            regime: Market regime
            
        Returns:
            Position size as percentage (0-1)
        """
        base_size = result.confidence * 0.5  # Base size from confidence
        
        # Regime adjustments
        regime_multipliers = {
            SwingRegime.TRENDING_UP: 1.2,
            SwingRegime.TRENDING_DOWN: 1.1,
            SwingRegime.RANGE_BOUND: 0.8,
            SwingRegime.VOLATILE_CHOP: 0.5
        }
        
        regime_multiplier = regime_multipliers.get(regime, 1.0)
        adjusted_size = base_size * regime_multiplier
        
        # Signal type adjustments
        if result.signal == SignalType.BUY:
            adjusted_size *= 1.1  # Slightly larger for BUY signals
        elif result.signal == SignalType.HOLD:
            adjusted_size *= 0.1  # Minimal for HOLD
        
        # Clamp between 0.05 (5%) and 0.95 (95%)
        return max(0.05, min(0.95, adjusted_size))
    
    def _calculate_risk_management(self, current_price: float, 
                                 signal: SignalType) -> Tuple[Optional[float], List[float]]:
        """
        Calculate stop loss and take profit levels
        
        Args:
            current_price: Current price
            signal: Signal type
            
        Returns:
            Tuple of (stop_loss, take_profit_levels)
        """
        if signal == SignalType.HOLD:
            return None, []
        
        # Calculate ATR-based stop loss (using 2% as default ATR)
        atr_pct = 0.02  # Default ATR percentage
        
        if signal == SignalType.BUY:
            stop_loss = current_price * (1 - 2 * atr_pct)  # 2x ATR below
            risk = current_price - stop_loss
            take_profit = [
                current_price + (risk * 1.5),  # 1.5:1 reward
                current_price + (risk * 2.5),  # 2.5:1 reward
                current_price + (risk * 4.0)   # 4:1 reward
            ]
        else:  # SELL
            stop_loss = current_price * (1 + 2 * atr_pct)  # 2x ATR above
            risk = stop_loss - current_price
            take_profit = [
                current_price - (risk * 1.5),  # 1.5:1 reward
                current_price - (risk * 2.5),  # 2.5:1 reward
                current_price - (risk * 4.0)   # 4:1 reward
            ]
        
        return stop_loss, take_profit
    
    def _create_hold_signal(self, symbol: str, context: MarketContext, 
                           reason: str) -> Signal:
        """Create a HOLD signal"""
        return Signal(
            symbol=symbol,
            signal="hold",
            confidence=0.1,
            strategy=self.name,
            timestamp=context.timestamp,
            price_at_signal=0.0,
            position_size_pct=0.0,
            timeframe="swing",
            entry_price_range=(0.0, 0.0),
            stop_loss=None,
            take_profit=[],
            reasoning=[reason],
            metadata={"error": reason}
        )

# Factory function for easy instantiation
def create_generic_swing_engine() -> RefactoredGenericSwingEngine:
    """Create a generic swing engine instance"""
    return RefactoredGenericSwingEngine()

# Example usage
if __name__ == "__main__":
    # Example test
    engine = create_generic_swing_engine()
    
    # Create sample data
    dates = pd.date_range('2024-01-01', periods=50, freq='D')
    np.random.seed(42)
    
    df = pd.DataFrame({
        'date': dates,
        'open': [100] * 50,
        'high': [102] * 50,
        'low': [98] * 50,
        'close': [100] * 50,
        'volume': [2000000] * 50,
        'rsi': [45.0] * 50,  # Slightly oversold for TQQQ
        'sma_20': [101] * 50,
        'sma_50': [100] * 50,
        'ema_20': [100.5] * 50,
        'macd': [0.1] * 50,
        'macd_signal': [0.05] * 50
    })
    
    # Create context
    from datetime import datetime
    context = MarketContext(
        symbol="TQQQ",
        timestamp=datetime.now().isoformat(),
        current_price=100.0,
        volatility=0.02,
        trend="neutral"
    )
    
    # Generate signal
    signal = engine.generate_signal("TQQQ", df, context)
    
    print(f"Signal: {signal.signal}")
    print(f"Confidence: {signal.confidence:.2f}")
    print(f"Position Size: {signal.position_size_pct:.2%}")
    print(f"Reasoning: {' | '.join(signal.reasoning)}")
    print(f"Regime: {signal.metadata.get('regime', 'unknown')}")
