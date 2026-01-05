"""
Generic Swing Trading Signal Engine
Handles standard swing trading for regular stocks (2-10 day holding periods)
Follows institutional-grade risk management principles
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import pandas as pd
import numpy as np

from app.signal_engines.base import (
    BaseSignalEngine, SignalResult, SignalType, MarketRegime, 
    EngineTier, MarketContext
)
from app.observability.logging import get_logger
from app.utils.technical_indicators import TechnicalIndicators

logger = get_logger(__name__)


class SwingRegime(Enum):
    """Swing trading specific market regimes"""
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN" 
    RANGE_BOUND = "RANGE_BOUND"
    VOLATILE_CHOP = "VOLATILE_CHOP"
    BREAKOUT_UP = "BREAKOUT_UP"
    BREAKOUT_DOWN = "BREAKOUT_DOWN"


@dataclass
class SwingSignalConfig:
    """Configuration for swing trading engine"""
    # Risk management
    max_position_size_pct: float = 0.02  # 2% per trade
    max_drawdown_pct: float = 0.15  # 15% max drawdown
    stop_loss_pct: float = 0.03  # 3% stop loss
    take_profit_pct: float = 0.06  # 6% take profit (2:1 ratio)
    
    # Time constraints
    min_holding_days: int = 2
    max_holding_days: int = 10
    
    # Technical thresholds
    min_volume_avg: int = 1000000  # Minimum average volume
    min_price: float = 10.0  # Minimum stock price
    max_price: float = 1000.0  # Maximum stock price
    
    # Regime detection parameters
    trend_ma_period: int = 20
    volatility_period: int = 14
    range_threshold_pct: float = 0.02  # 2% for range detection


class GenericSwingEngine(BaseSignalEngine):
    """
    Generic Swing Trading Engine
    
    Designed for standard stocks with 2-10 day holding periods.
    Implements institutional-grade risk management and regime awareness.
    Not suitable for leveraged ETFs like TQQQ.
    """
    
    def __init__(self, config: Optional[SwingSignalConfig] = None):
        super().__init__()  # Call parent __init__ without parameters
        self.config = config or SwingSignalConfig()
        self._indicators = TechnicalIndicators()
        
        # Override parent defaults with our specific values
        self.name = "generic_swing_trader"
        self.version = "1.0.0"
        self.tier = EngineTier.PRO
        self.description = "Generic swing trading engine for standard stocks (2-10 day periods)"
        
    def get_required_data_period(self) -> timedelta:
        """Get required historical data period for analysis"""
        return timedelta(days=100)  # Need ~100 days for proper technical analysis
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get engine metadata"""
        return {
            "display_name": "Generic Swing Trader",
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tier": self.tier.value,
            "config": {
                "max_position_size_pct": self.config.max_position_size_pct,
                "max_drawdown_pct": self.config.max_drawdown_pct,
                "stop_loss_pct": self.config.stop_loss_pct,
                "take_profit_pct": self.config.take_profit_pct,
                "holding_period_days": f"{self.config.min_holding_days}-{self.config.max_holding_days}",
                "suitable_for": "Standard stocks, ETFs (non-leveraged)",
                "not_suitable_for": "Leveraged ETFs (TQQQ), penny stocks, options"
            }
        }
    
    def get_engine_metadata(self) -> Dict[str, Any]:
        """Return engine name, version, description, tier"""
        return {
            "display_name": "Generic Swing Trader",
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tier": self.tier.value,
            "timeframe": "swing",
            "required_data_period": str(self.get_required_data_period()),
            "suitable_for": [
                "Standard stocks",
                "Non-leveraged ETFs", 
                "2-10 day holding periods",
                "Trend following strategies"
            ],
            "not_suitable_for": [
                "Leveraged ETFs (TQQQ)",
                "Penny stocks",
                "Options trading",
                "Day trading"
            ],
            "risk_level": "Moderate",
            "complexity": "Intermediate"
        }
    
    def detect_market_regime(self, data: pd.DataFrame, context: MarketContext) -> SwingRegime:
        """
        Detect swing trading specific market regime
        
        Args:
            data: Historical price data with OHLCV
            context: Market context information
            
        Returns:
            Current swing trading regime
        """
        try:
            # Calculate technical indicators
            data = self._indicators.add_all_indicators(data)
            
            # Get recent price action
            recent_data = data.tail(20)
            current_price = data['close'].iloc[-1]
            
            # Trend analysis
            sma_trend = data['sma_20'].iloc[-1] > data['sma_50'].iloc[-1]
            price_above_sma = current_price > data['sma_20'].iloc[-1]
            
            # Volatility analysis
            atr_pct = data['atr'].iloc[-1] / current_price
            volatility_high = atr_pct > 0.03  # 3%+ daily range is high volatility
            
            # Range detection
            price_range_pct = (recent_data['high'].max() - recent_data['low'].min()) / recent_data['close'].mean()
            is_range_bound = price_range_pct < self.config.range_threshold_pct
            
            # Momentum
            rsi = data['rsi'].iloc[-1]
            macd_bullish = data['macd'].iloc[-1] > data['macd_signal'].iloc[-1]
            
            # Determine regime
            if is_range_bound and volatility_high:
                return SwingRegime.VOLATILE_CHOP
            elif is_range_bound:
                return SwingRegime.RANGE_BOUND
            elif sma_trend and price_above_sma and macd_bullish:
                if not volatility_high:
                    return SwingRegime.TRENDING_UP
                else:
                    return SwingRegime.BREAKOUT_UP
            elif not sma_trend and not price_above_sma and not macd_bullish:
                if not volatility_high:
                    return SwingRegime.TRENDING_DOWN
                else:
                    return SwingRegime.BREAKOUT_DOWN
            else:
                # Default to trending based on overall market context
                return SwingRegime.TRENDING_UP if context.regime == MarketRegime.BULL else SwingRegime.TRENDING_DOWN
                
        except Exception as e:
            logger.error(f"Error detecting regime: {e}")
            return SwingRegime.VOLATILE_CHOP  # Default to conservative
    
    def validate_trading_conditions(self, data: pd.DataFrame, symbol: str) -> Tuple[bool, List[str]]:
        """
        Validate if symbol meets swing trading criteria
        
        Args:
            data: Historical price data
            symbol: Stock symbol
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        try:
            current_price = data['close'].iloc[-1]
            avg_volume = data['volume'].tail(20).mean()
            
            # Price validation
            if current_price < self.config.min_price:
                issues.append(f"Price ${current_price:.2f} below minimum ${self.config.min_price}")
            
            if current_price > self.config.max_price:
                issues.append(f"Price ${current_price:.2f} above maximum ${self.config.max_price}")
            
            # Volume validation
            if avg_volume < self.config.min_volume_avg:
                issues.append(f"Average volume {avg_volume:,.0f} below minimum {self.config.min_volume_avg:,.0f}")
            
            # Data quality validation
            if len(data) < 50:
                issues.append(f"Insufficient data: {len(data)} days (minimum 50)")
            
            # Recent volatility check
            recent_volatility = data['close'].pct_change().tail(10).std()
            if recent_volatility > 0.05:  # 5%+ daily volatility is too high
                issues.append(f"Recent volatility {recent_volatility:.2%} too high for swing trading")
            
            return len(issues) == 0, issues
            
        except Exception as e:
            logger.error(f"Error validating trading conditions for {symbol}: {e}")
            return False, [f"Validation error: {str(e)}"]
    
    def generate_signal(self, symbol: str, data: pd.DataFrame, context: MarketContext) -> SignalResult:
        """
        Generate swing trading signal
        
        Args:
            symbol: Stock symbol
            data: Historical price data
            context: Market context
            
        Returns:
            Signal result with recommendation
        """
        try:
            # Validate trading conditions
            is_valid, issues = self.validate_trading_conditions(data, symbol)
            if not is_valid:
                return self._create_hold_signal(
                    symbol, context, 
                    f"Trading conditions not met: {'; '.join(issues)}"
                )
            
            # Detect regime
            regime = self.detect_market_regime(data, context)
            
            # Calculate indicators
            data = self._indicators.add_all_indicators(data)
            current_price = data['close'].iloc[-1]
            
            # Generate signal based on regime
            signal, confidence, reasoning = self._generate_regime_signal(data, regime, context)
            
            # Calculate position sizing and targets
            position_size_pct = self.config.max_position_size_pct * confidence
            stop_loss = self._calculate_stop_loss(data, signal)
            take_profit = self._calculate_take_profit(data, signal, stop_loss)
            
            # Adjust confidence based on regime
            regime_multiplier = self._get_regime_confidence_multiplier(regime)
            confidence *= regime_multiplier
            
            # Create signal result
            return SignalResult(
                engine_name=self.name,
                engine_version=self.version,
                engine_tier=self.tier,
                symbol=symbol,
                signal=signal,
                confidence=confidence,
                position_size_pct=position_size_pct,
                timeframe="swing",
                entry_price_range=(current_price * 0.995, current_price * 1.005),  # 0.5% range
                stop_loss=stop_loss,
                take_profit=[take_profit],
                reasoning=reasoning,
                metadata={
                    "regime": regime.value,
                    "current_price": current_price,
                    "volume": data['volume'].iloc[-1],
                    "rsi": data['rsi'].iloc[-1],
                    "atr": data['atr'].iloc[-1],
                    "sma_20": data['sma_20'].iloc[-1],
                    "sma_50": data['sma_50'].iloc[-1]
                }
            )
            
        except Exception as e:
            logger.error(f"Error generating signal for {symbol}: {e}")
            return self._create_hold_signal(symbol, context, f"Signal generation error: {str(e)}")
    
    def _generate_regime_signal(self, data: pd.DataFrame, regime: SwingRegime, context: MarketContext) -> Tuple[SignalType, float, List[str]]:
        """Generate signal based on regime with improved reversal detection"""
        current_price = data['close'].iloc[-1]
        rsi = data['rsi'].iloc[-1]
        macd = data['macd'].iloc[-1]
        macd_signal = data['macd_signal'].iloc[-1]
        sma_20 = data['sma_20'].iloc[-1]
        sma_50 = data['sma_50'].iloc[-1]
        
        reasoning = []
        confidence = 0.5
        
        # Enhanced condition detection with TQQQ awareness - MUCH MORE AGGRESSIVE BUY CONDITIONS
        is_oversold = rsi < 30
        is_overbought = rsi > 70
        is_neutral = 35 <= rsi <= 65
        
        # More aggressive oversold detection for BUY signals
        is_very_oversold = rsi < 25
        is_moderately_oversold = 25 <= rsi < 35
        is_mildly_oversold = 35 <= rsi < 45  # NEW: Mildly oversold for more BUY signals
        
        # TQQQ-specific thresholds (much more aggressive for BUY signals)
        symbol_name = "Unknown"
        if hasattr(context, 'symbol'):
            symbol_name = context.symbol
        elif hasattr(context, 'symbol'):
            symbol_name = context.symbol
            
        if symbol_name == "TQQQ":
            is_oversold = rsi < 50  # MUCH MORE AGGRESSIVE: RSI < 50 (was 40)
            is_overbought = rsi > 70  # Keep overbought the same
            is_very_oversold = rsi < 35  # More aggressive (was 30)
            is_moderately_oversold = 35 <= rsi < 50  # Much more aggressive (was 30-40)
            is_mildly_oversold = 45 <= rsi < 55  # NEW: Mildly oversold range
            is_neutral = 50 <= rsi <= 70  # Adjusted neutral range
        
        # Trend detection
        is_uptrend = sma_20 > sma_50 and current_price > sma_20
        is_downtrend = sma_20 < sma_50 and current_price < sma_20
        is_sideways = abs(sma_20 - sma_50) / sma_50 < 0.02
        
        # Recent price action
        recent_data = data.tail(3)
        recent_change = (current_price - recent_data['close'].iloc[0]) / recent_data['close'].iloc[0]
        is_recently_down = recent_change < -0.02
        is_recently_up = recent_change > 0.02
        
        # TQQQ leverage decay detection
        is_leverage_decay_risk = False
        if symbol_name == "TQQQ":
            # Check for range-bound action (leverage decay risk)
            if is_sideways and is_neutral:
                is_leverage_decay_risk = True
        
        if regime == SwingRegime.TRENDING_UP:
            # VERY AGGRESSIVE BUY detection in TRENDING_UP regime
            if is_uptrend and macd > macd_signal and not is_overbought:
                signal = SignalType.BUY
                confidence = min(0.8, 0.6 + (70 - rsi) / 40)  # Higher confidence if RSI not overbought
                reasoning.extend([
                    "Strong uptrend confirmed",
                    f"Price ({current_price:.2f}) above SMA20 ({sma_20:.2f})",
                    "MACD bullish crossover",
                    f"RSI confirms strength: {rsi:.1f}"
                ])
                
                # Add TQQQ-specific reasoning
                if symbol_name == "TQQQ":
                    reasoning.append("TQQQ: Favorable trend for leveraged ETF")
                    if not is_leverage_decay_risk:
                        reasoning.append("TQQQ: Low leverage decay risk")
                        
            elif is_mildly_oversold and not is_downtrend:
                # NEW: BUY on mildly oversold in neutral/uptrend
                signal = SignalType.BUY
                confidence = 0.5
                reasoning.extend([
                    "Mildly oversold buying opportunity",
                    f"RSI mildly oversold: {rsi:.1f}",
                    "Price support level likely",
                    "Reversal potential"
                ])
                        
            elif is_moderately_oversold and not is_downtrend:
                # BUY on moderate oversold in neutral/uptrend
                signal = SignalType.BUY
                confidence = 0.6
                reasoning.extend([
                    "Moderately oversold buying opportunity",
                    f"RSI moderately oversold: {rsi:.1f}",
                    "Price support level likely",
                    "Reversal potential"
                ])
                
            elif is_oversold and is_recently_down:
                # BUY on oversold dip in uptrend
                signal = SignalType.BUY
                confidence = 0.7
                reasoning.extend([
                    "Uptrend dip buying opportunity",
                    f"RSI oversold: {rsi:.1f}",
                    f"Recent decline: {recent_change:.2%}",
                    "Mean reversion in uptrend"
                ])
                
            elif is_uptrend and is_recently_up and rsi < 65:  # More aggressive: was 60
                # BUY on continuation of uptrend
                signal = SignalType.BUY
                confidence = 0.5
                reasoning.extend([
                    "Uptrend continuation",
                    f"RSI strength: {rsi:.1f} (room to run)",
                    "Momentum supports further upside",
                    "Trend-following entry"
                ])
                
            elif is_uptrend and rsi < 60:  # NEW: BUY on any uptrend with RSI < 60
                signal = SignalType.BUY
                confidence = 0.4
                reasoning.extend([
                    "Uptrend with room to run",
                    f"RSI not overbought: {rsi:.1f}",
                    "Trend momentum entry",
                    "Follow the trend"
                ])
                
            elif is_neutral and is_mildly_oversold:
                # NEW: BUY on neutral but mildly oversold
                signal = SignalType.BUY
                confidence = 0.4
                reasoning.extend([
                    "Neutral market with oversold conditions",
                    f"RSI mildly oversold: {rsi:.1f}",
                    "Potential bounce opportunity",
                    "Mean reversion play"
                ])
                
            elif is_downtrend and is_overbought:
                # SELL on trend reversal signs
                signal = SignalType.SELL
                confidence = 0.6
                reasoning.extend([
                    "Potential trend reversal",
                    f"RSI overbought: {rsi:.1f}",
                    "Price below moving averages",
                    "Risk management: take profits"
                ])
            else:
                signal = SignalType.HOLD
                confidence = 0.3
                reasoning.extend([
                    "Uptrend but momentum weak",
                    "Waiting for better entry",
                    f"RSI neutral: {rsi:.1f}"
                ])
                
        elif regime == SwingRegime.TRENDING_DOWN:
            # Bearish trend with reversal opportunities
            if is_downtrend and macd < macd_signal and not is_oversold:
                signal = SignalType.SELL
                confidence = min(0.75, 0.5 + rsi / 60)  # Higher confidence if RSI not oversold
                reasoning.extend([
                    "Downtrend confirmed",
                    f"Price ({current_price:.2f}) below SMA20 ({sma_20:.2f})",
                    "MACD bearish crossover",
                    f"RSI confirms weakness: {rsi:.1f}"
                ])
            elif is_oversold and is_recently_down:
                # Potential reversal from oversold
                signal = SignalType.BUY
                confidence = 0.6
                reasoning.extend([
                    "Downtrend reversal opportunity",
                    f"RSI deeply oversold: {rsi:.1f}",
                    f"Recent decline: {recent_change:.2%}",
                    "Contrarian reversal play"
                ])
            elif is_moderately_oversold and not is_recently_down:
                # NEW: BUY on moderate oversold in downtrend
                signal = SignalType.BUY
                confidence = 0.5
                reasoning.extend([
                    "Downtrend moderate oversold",
                    f"RSI moderately oversold: {rsi:.1f}",
                    "Potential bounce opportunity",
                    "Mean reversion play"
                ])
            elif is_mildly_oversold and not is_recently_down:
                # NEW: BUY on mild oversold in downtrend
                signal = SignalType.BUY
                confidence = 0.4
                reasoning.extend([
                    "Downtrend mild oversold",
                    f"RSI mildly oversold: {rsi:.1f}",
                    "Bottoming pattern likely",
                    "Reversal potential"
                ])
            elif is_oversold and not is_recently_down:
                # NEW: BUY on oversold stabilization
                signal = SignalType.BUY
                confidence = 0.4
                reasoning.extend([
                    "Downtrend oversold stabilization",
                    f"RSI oversold: {rsi:.1f}",
                    "Bottoming pattern detected",
                    "Mean reversion entry"
                ])
            elif is_uptrend and is_overbought:
                signal = SignalType.SELL
                confidence = 0.6
                reasoning.extend([
                    "Counter-trend overbought",
                    f"RSI overbought: {rsi:.1f}",
                    "Short-term reversal likely"
                ])
            else:
                signal = SignalType.HOLD
                confidence = 0.3
                reasoning.extend([
                    "Downtrend but oversold",
                    "Wait for bounce or confirmation",
                    f"RSI oversold: {rsi:.1f}"
                ])
                
        elif regime == SwingRegime.RANGE_BOUND:
            # VERY AGGRESSIVE range trading with enhanced BUY detection
            if is_oversold and is_recently_down:
                signal = SignalType.BUY
                confidence = 0.6
                reasoning.extend([
                    "Range-bound oversold - buy low",
                    f"RSI oversold: {rsi:.1f}",
                    f"Recent decline: {recent_change:.2%}",
                    "Mean reversion play in range"
                ])
            elif is_moderately_oversold and is_recently_down:
                # BUY on moderate oversold in range
                signal = SignalType.BUY
                confidence = 0.5
                reasoning.extend([
                    "Range-bound moderately oversold",
                    f"RSI moderately oversold: {rsi:.1f}",
                    f"Recent decline: {recent_change:.2%}",
                    "Support level likely"
                ])
            elif is_mildly_oversold and not is_recently_up:
                # NEW: BUY on mild oversold in range
                signal = SignalType.BUY
                confidence = 0.4
                reasoning.extend([
                    "Range-bound mildly oversold",
                    f"RSI mildly oversold: {rsi:.1f}",
                    "Bottoming pattern detected",
                    "Mean reversion entry"
                ])
            elif is_oversold and not is_recently_down:
                # BUY on oversold stabilization
                signal = SignalType.BUY
                confidence = 0.4
                reasoning.extend([
                    "Range-bound oversold stabilization",
                    f"RSI oversold: {rsi:.1f}",
                    "Bottoming pattern detected",
                    "Mean reversion entry"
                ])
            elif is_neutral and is_mildly_oversold:
                # NEW: BUY on neutral but mildly oversold in range
                signal = SignalType.BUY
                confidence = 0.3
                reasoning.extend([
                    "Range-bound neutral with oversold",
                    f"RSI mildly oversold: {rsi:.1f}",
                    "Potential bounce opportunity",
                    "Mean reversion play"
                ])
            elif is_overbought and is_recently_up:
                signal = SignalType.SELL
                confidence = 0.6
                reasoning.extend([
                    "Range-bound overbought - sell high",
                    f"RSI overbought: {rsi:.1f}",
                    f"Recent rise: {recent_change:.2%}",
                    "Mean reversion play in range"
                ])
            elif is_overbought and not is_recently_up:
                signal = SignalType.SELL
                confidence = 0.4
                reasoning.extend([
                    "Range-bound overbought topping",
                    f"RSI overbought: {rsi:.1f}",
                    "Resistance level likely",
                    "Mean reversion exit"
                ])
            else:
                signal = SignalType.HOLD
                confidence = 0.2
                reasoning.extend([
                    "Range-bound market - no edge",
                    f"RSI neutral: {rsi:.1f}",
                    "Wait for extreme levels"
                ])
            
        elif regime == SwingRegime.VOLATILE_CHOP:
            # High volatility - only extreme signals
            if is_oversold and rsi < 25:  # Very oversold
                signal = SignalType.BUY
                confidence = 0.4
                reasoning.extend([
                    "Extreme oversold in high volatility",
                    f"RSI very oversold: {rsi:.1f}",
                    "High-risk reversal play"
                ])
            elif is_overbought and rsi > 75:  # Very overbought
                signal = SignalType.SELL
                confidence = 0.4
                reasoning.extend([
                    "Extreme overbought in high volatility",
                    f"RSI very overbought: {rsi:.1f}",
                    "High-risk reversal play"
                ])
            else:
                signal = SignalType.HOLD
                confidence = 0.1
                reasoning.extend([
                    "High volatility chop - avoid trading",
                    "Elevated risk of false breakouts",
                    "Preserve capital, wait for clarity"
                ])
            
        elif regime == SwingRegime.BREAKOUT_UP:
            # Bullish breakout
            if is_uptrend and macd > macd_signal and rsi < 75:
                signal = SignalType.BUY
                confidence = min(0.85, 0.6 + (75 - rsi) / 30)
                reasoning.extend([
                    "Strong bullish breakout",
                    f"Price above moving averages: {current_price:.2f}",
                    "MACD confirms momentum",
                    f"RSI strength: {rsi:.1f}"
                ])
            elif is_overbought and is_recently_up:
                signal = SignalType.SELL
                confidence = 0.5
                reasoning.extend([
                    "Breakout but extremely overbought",
                    f"RSI overbought: {rsi:.1f}",
                    "Wait for pullback entry"
                ])
            else:
                signal = SignalType.HOLD
                confidence = 0.3
                reasoning.extend([
                    "Breakout losing momentum",
                    "Wait for confirmation"
                ])
                
        elif regime == SwingRegime.BREAKOUT_DOWN:
            # Bearish breakout
            if is_downtrend and macd < macd_signal and rsi > 25:
                signal = SignalType.SELL
                confidence = min(0.8, 0.5 + rsi / 50)
                reasoning.extend([
                    "Strong bearish breakout",
                    f"Price below moving averages: {current_price:.2f}",
                    "MACD confirms downside",
                    f"RSI weakness: {rsi:.1f}"
                ])
            elif is_oversold and is_recently_down:
                signal = SignalType.BUY
                confidence = 0.5
                reasoning.extend([
                    "Breakdown but extremely oversold",
                    f"RSI oversold: {rsi:.1f}",
                    "Potential reversal opportunity"
                ])
            else:
                signal = SignalType.HOLD
                confidence = 0.3
                reasoning.extend([
                    "Breakdown slowing down",
                    "Wait for confirmation"
                ])
        else:
            signal = SignalType.HOLD
            confidence = 0.1
            reasoning.append("Unclear market conditions - stay in cash")
        
        # Final confidence adjustment for confluence
        if signal != SignalType.HOLD:
            confluence_boost = 0
            if is_uptrend and signal == SignalType.BUY:
                confluence_boost += 0.1
            if is_downtrend and signal == SignalType.SELL:
                confluence_boost += 0.1
            if is_oversold and signal == SignalType.BUY:
                confluence_boost += 0.1
            if is_overbought and signal == SignalType.SELL:
                confluence_boost += 0.1
            
            confidence = min(0.9, confidence + confluence_boost)
        
        return signal, confidence, reasoning
    
    def _calculate_stop_loss(self, data: pd.DataFrame, signal: SignalType) -> Optional[float]:
        """Calculate stop loss based on ATR and recent price action"""
        current_price = data['close'].iloc[-1]
        atr = data['atr'].iloc[-1]
        
        if signal == SignalType.BUY:
            # Stop loss below recent low or ATR-based
            recent_low = data['low'].tail(10).min()
            atr_stop = current_price - (2 * atr)
            return max(recent_low, atr_stop)
        elif signal == SignalType.SELL:
            # Stop loss above recent high or ATR-based
            recent_high = data['high'].tail(10).max()
            atr_stop = current_price + (2 * atr)
            return min(recent_high, atr_stop)
        return None
    
    def _calculate_take_profit(self, data: pd.DataFrame, signal: SignalType, stop_loss: Optional[float]) -> Optional[float]:
        """Calculate take profit based on risk/reward ratio"""
        current_price = data['close'].iloc[-1]
        
        if stop_loss is None:
            return None
            
        if signal == SignalType.BUY:
            risk = current_price - stop_loss
            reward = risk * 2  # 2:1 risk/reward
            return current_price + reward
        elif signal == SignalType.SELL:
            risk = stop_loss - current_price
            reward = risk * 2
            return current_price - reward
        return None
    
    def _get_regime_confidence_multiplier(self, regime: SwingRegime) -> float:
        """Get confidence multiplier based on regime"""
        multipliers = {
            SwingRegime.TRENDING_UP: 1.0,
            SwingRegime.TRENDING_DOWN: 0.9,
            SwingRegime.BREAKOUT_UP: 0.8,  # Breakouts can fail
            SwingRegime.BREAKOUT_DOWN: 0.8,
            SwingRegime.RANGE_BOUND: 0.3,  # Avoid swing trades in ranges
            SwingRegime.VOLATILE_CHOP: 0.1  # Very low confidence in chop
        }
        return multipliers.get(regime, 0.5)
    
    def _create_hold_signal(self, symbol: str, context: MarketContext, reason: str) -> SignalResult:
        """Create a HOLD signal with reasoning"""
        return SignalResult(
            engine_name=self.name,
            engine_version=self.version,
            engine_tier=self.tier,
            symbol=symbol,
            signal=SignalType.HOLD,
            confidence=0.1,
            position_size_pct=0.0,
            timeframe="swing",
            entry_price_range=None,
            stop_loss=None,
            take_profit=[],
            reasoning=[f"HOLD: {reason}"],
            metadata={
                "regime": "UNKNOWN",
                "hold_reason": reason
            }
        )
