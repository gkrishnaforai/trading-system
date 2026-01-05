"""
Swing Regime Signal Engine
4-layer architecture for short-term swing trading signals
"""

# See ARCHITECTURE.md in this folder before modifying layers/thresholds.

from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from .base import (
    BaseSignalEngine, SignalResult, SignalType, SignalEngineError,
    InsufficientDataError, ModelPredictionError, MarketRegime
)
from .signal_engine_utils import SignalEngineUtils
from app.observability.logging import get_logger

logger = get_logger(__name__)


class SwingRegimeEngine(BaseSignalEngine):
    """
    Swing trading engine with 4-layer architecture:
    
    Layer 1: Market Regime Detection
    Layer 2: Direction & Confidence (ML model)
    Layer 3: Allocation Engine
    Layer 4: Reality Adjustments (leveraged ETF awareness)
    """
    
    def __init__(self):
        super().__init__()
        self.engine_name = "swing_regime"
        self.engine_version = "1.0.0"
        self.min_data_length = 50  # Need at least 50 days for swing analysis

        self._reality_cfg = {
            "vix_decay_threshold": 25.0,
            "vix_high_threshold": 30.0,
            "vix_chop_penalty_threshold": 20.0,
            "bb_squeeze_threshold": 0.008,
            "low_momentum_abs_5d": 0.01,
            "atr_pct_high_threshold": 0.03,
            "size_penalty_high_decay": 0.5,
            "size_penalty_chop": 0.6,
        }
    
    def generate_signal(
        self,
        symbol: str,
        market_data: pd.DataFrame,
        indicators: Dict[str, Any],
        fundamentals: Dict[str, Any],
        market_context
    ) -> SignalResult:
        """
        Generate swing trading signal using 4-layer architecture
        
        Args:
            symbol: Stock symbol
            market_data: Historical price data
            indicators: Technical indicators
            fundamentals: Fundamental data
            market_context: Market regime context
            
        Returns:
            SignalResult with swing trading analysis
        """
        try:
            indicators = SignalEngineUtils.ensure_indicator_price(indicators, market_data)

            # Validate inputs
            self.validate_inputs(symbol, market_data, indicators, fundamentals, market_context)
            
            # Check minimum data length
            if len(market_data) < self.min_data_length:
                raise InsufficientDataError(
                    f"Need at least {self.min_data_length} days of data, got {len(market_data)}",
                    self.engine_name, symbol
                )
            
            # Layer 1: Market Regime Detection (already done in market_context)
            regime_score, regime_reasoning = self._analyze_regime_for_swing(market_context)
            
            # Early exit for NO_TRADE regime
            if market_context.regime == MarketRegime.NO_TRADE:
                return self._create_signal_result(
                    symbol=symbol,
                    signal=SignalType.HOLD,
                    confidence=0.1,
                    reasoning=regime_reasoning + ["Market regime: NO_TRADE - avoiding swing trades"],
                    position_size_pct=0.0,
                    timeframe='swing'
                )
            
            # Layer 2: Direction & Confidence
            direction_score, confidence, direction_reasoning = self._calculate_direction_confidence(
                market_data, indicators, market_context
            )
            
            # Layer 3: Allocation Engine
            position_size, allocation_reasoning = self._determine_allocation(
                direction_score, confidence, market_context
            )
            
            # Layer 4: Reality Adjustments
            adjusted_position_size, reality_reasoning = self._apply_reality_adjustments(
                position_size, market_context, indicators, market_data
            )
            
            # Determine final signal
            signal = self._determine_signal(direction_score, confidence, market_context)
            
            # Calculate entry/exit levels
            entry_range, stop_loss, take_profit = self._calculate_swing_entry_exit(
                signal, market_data, indicators, confidence
            )
            
            # Combine all reasoning
            reasoning = regime_reasoning + direction_reasoning + allocation_reasoning + reality_reasoning

            market_monitor = SignalEngineUtils.compute_market_conditions_monitor(
                market_context=market_context,
                market_data=market_data,
                indicators=indicators,
            )
            
            return self._create_signal_result(
                symbol=symbol,
                signal=signal,
                confidence=confidence,
                reasoning=reasoning,
                position_size_pct=adjusted_position_size,
                entry_price_range=entry_range,
                stop_loss=stop_loss,
                take_profit=take_profit,
                timeframe='swing',
                metadata={
                    'regime_score': regime_score,
                    'direction_score': direction_score,
                    'original_position_size': position_size,
                    'adjusted_position_size': adjusted_position_size,
                    'hold_duration_days': self._estimate_hold_duration(market_context, confidence),
                    'market_conditions_monitor': market_monitor.to_dict(),
                }
            )
            
        except Exception as e:
            if isinstance(e, SignalEngineError):
                raise
            raise SignalEngineError(f"Failed to generate swing regime signal: {str(e)}", 
                                 self.engine_name, symbol)
    
    def _analyze_regime_for_swing(self, market_context) -> Tuple[float, List[str]]:
        """Analyze market regime specifically for swing trading"""
        reasoning = []
        score = 0.0
        
        # Regime scoring for swing trading
        if market_context.regime == MarketRegime.BULL:
            score = 1.0
            reasoning.append("Market regime: BULL (favorable for swing longs)")
        elif market_context.regime == MarketRegime.BEAR:
            score = -0.5
            reasoning.append("Market regime: BEAR (favorable for swing shorts)")
        elif market_context.regime == MarketRegime.HIGH_VOL_CHOP:
            score = -0.2
            reasoning.append("Market regime: HIGH_VOL_CHOP (reduced swing opportunities)")
        else:  # NO_TRADE
            score = -1.0
            reasoning.append("Market regime: NO_TRADE (avoid swing trading)")
        
        # VIX consideration for swing trading
        if market_context.vix < 15:
            score += 0.2
            reasoning.append(f"Low VIX ({market_context.vix:.1f}) - good for swing trading")
        elif market_context.vix > 30:
            score -= 0.3
            reasoning.append(f"High VIX ({market_context.vix:.1f}) - caution for swing trading")
        
        return score, reasoning
    
    def _calculate_direction_confidence(
        self, market_data: pd.DataFrame, indicators: Dict[str, Any], market_context
    ) -> Tuple[float, float, List[str]]:
        """
        Calculate direction probability using swing-specific features
        Simplified ML model using rule-based approach for now
        """
        reasoning = []
        score = 0.0
        
        # Feature 1: Short-term momentum (1d, 5d, 21d)
        momentum_score, momentum_reasoning = self._analyze_momentum(market_data)
        score += momentum_score * 0.3
        reasoning.extend(momentum_reasoning)
        
        # Feature 2: Volatility expansion
        vol_score, vol_reasoning = self._analyze_volatility_expansion(market_data, indicators)
        score += vol_score * 0.2
        reasoning.extend(vol_reasoning)
        
        # Feature 3: RSI/MACD regime-aware
        rsi_score, rsi_reasoning = self._analyze_rsi_macd(indicators, market_context)
        score += rsi_score * 0.3
        reasoning.extend(rsi_reasoning)
        
        # Feature 4: Price action (breakouts, pullbacks)
        price_score, price_reasoning = self._analyze_price_action(market_data)
        score += price_score * 0.2
        reasoning.extend(price_reasoning)
        
        # Convert score to confidence
        confidence = max(0.0, min(1.0, 0.5 + score))
        
        return score, confidence, reasoning
    
    def _analyze_momentum(self, market_data: pd.DataFrame) -> Tuple[float, List[str]]:
        """Analyze short-term momentum"""
        reasoning = []
        score = 0.0
        
        if len(market_data) < 21:
            return 0.0, ["Insufficient data for momentum analysis"]
        
        # Calculate returns
        closes = market_data['close'].astype(float).values
        returns_1d = (closes[-1] - closes[-2]) / closes[-2]
        returns_5d = (closes[-1] - closes[-6]) / closes[-6] if len(closes) > 5 else 0
        returns_21d = (closes[-1] - closes[-22]) / closes[-22] if len(closes) > 21 else 0
        
        # Score 1-day momentum
        if returns_1d > 0.02:  # > 2%
            score += 0.3
            reasoning.append(f"Strong 1-day momentum: +{returns_1d*100:.1f}%")
        elif returns_1d > 0.005:  # > 0.5%
            score += 0.1
            reasoning.append(f"Positive 1-day momentum: +{returns_1d*100:.1f}%")
        elif returns_1d < -0.02:  # < -2%
            score -= 0.3
            reasoning.append(f"Weak 1-day momentum: {returns_1d*100:.1f}%")
        
        # Score 5-day momentum
        if returns_5d > 0.05:  # > 5%
            score += 0.2
            reasoning.append(f"Strong 5-day momentum: +{returns_5d*100:.1f}%")
        elif returns_5d < -0.05:  # < -5%
            score -= 0.2
            reasoning.append(f"Weak 5-day momentum: {returns_5d*100:.1f}%")
        
        # Score 21-day momentum
        if returns_21d > 0.10:  # > 10%
            score += 0.1
            reasoning.append(f"Strong 21-day momentum: +{returns_21d*100:.1f}%")
        
        return score, reasoning
    
    def _analyze_volatility_expansion(
        self, market_data: pd.DataFrame, indicators: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """Analyze volatility expansion for breakout potential"""
        reasoning = []
        score = 0.0
        
        # Use ATR if available, otherwise calculate from price ranges
        atr = SignalEngineUtils.to_float(indicators.get('atr'))
        if atr is None and len(market_data) >= 14:
            # Calculate simple ATR
            highs = market_data['high'].astype(float)
            lows = market_data['low'].astype(float)
            closes = market_data['close'].astype(float)
            high_low = highs - lows
            high_close = abs(highs - closes.shift())
            low_close = abs(lows - closes.shift())
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = true_range.rolling(14).mean().iloc[-1]
        
        if atr is None:
            return 0.0, ["No volatility data available"]
        
        current_price = float(market_data.iloc[-1]['close'])
        atr_pct = float(atr) / float(current_price) if current_price > 0 else 0.0
        
        # Check for volatility expansion
        if len(market_data) >= 14:
            atr_14d_avg = atr_pct  # Already 14-day average
            if atr_14d_avg > 0.03:  # > 3% daily range
                score += 0.2
                reasoning.append(f"High volatility expansion: {atr_14d_avg*100:.1f}% daily range")
            elif atr_14d_avg < 0.01:  # < 1% daily range
                score -= 0.1
                reasoning.append(f"Low volatility: {atr_14d_avg*100:.1f}% daily range")
        
        # Check for Bollinger Band squeeze/expansion
        bb_width = SignalEngineUtils.to_float(indicators.get('bb_width'))
        if bb_width is not None:
            if bb_width > 0.02:  # Wide bands
                score += 0.1
                reasoning.append("Bollinger Bands expanded (high volatility)")
            elif bb_width < 0.01:  # Narrow bands
                score += 0.1
                reasoning.append("Bollinger Band squeeze (potential breakout)")
        
        return score, reasoning
    
    def _analyze_rsi_macd(self, indicators: Dict[str, Any], market_context) -> Tuple[float, List[str]]:
        """Analyze RSI and MACD with regime awareness"""
        reasoning = []
        score = 0.0
        
        rsi = indicators.get('rsi')
        if rsi:
            if market_context.regime == MarketRegime.BULL:
                # In bull market, favor less overbought conditions
                if 40 <= rsi <= 70:
                    score += 0.2
                    reasoning.append(f"RSI healthy for bull market: {rsi:.1f}")
                elif rsi > 80:
                    score -= 0.1
                    reasoning.append(f"RSI overbought: {rsi:.1f}")
            elif market_context.regime == MarketRegime.BEAR:
                # In bear market, favor oversold conditions
                if rsi < 30:
                    score += 0.2
                    reasoning.append(f"RSI oversold (bear market bounce): {rsi:.1f}")
                elif rsi > 60:
                    score -= 0.2
                    reasoning.append(f"RSI too high in bear market: {rsi:.1f}")
            else:  # CHOP/NEUTRAL
                if 30 <= rsi <= 70:
                    score += 0.1
                    reasoning.append(f"RSI neutral: {rsi:.1f}")
        
        # MACD analysis
        macd = indicators.get('macd')
        macd_signal = indicators.get('macd_signal')
        macd_hist = indicators.get('macd_hist')
        
        if macd and macd_signal:
            if macd > macd_signal:
                score += 0.1
                reasoning.append("MACD bullish (above signal)")
            else:
                score -= 0.1
                reasoning.append("MACD bearish (below signal)")
        
        if macd_hist:
            if macd_hist > 0 and macd_hist > indicators.get('macd_hist_prev', macd_hist):
                score += 0.1
                reasoning.append("MACD histogram expanding upward")
            elif macd_hist < 0 and macd_hist < indicators.get('macd_hist_prev', macd_hist):
                score -= 0.1
                reasoning.append("MACD histogram expanding downward")
        
        return score, reasoning
    
    def _analyze_price_action(self, market_data: pd.DataFrame) -> Tuple[float, List[str]]:
        """Analyze price action patterns for swing trading"""
        reasoning = []
        score = 0.0
        
        if len(market_data) < 10:
            return 0.0, ["Insufficient data for price action analysis"]
        
        recent_data = market_data.tail(10)
        current_price = float(recent_data.iloc[-1]['close'])
        
        # Check for breakout above recent resistance
        recent_high = float(recent_data['high'].astype(float).max())
        if current_price > recent_high * 0.98:
            score += 0.2
            reasoning.append("Near breakout above recent high")
        
        # Check for pullback to support
        recent_low = float(recent_data['low'].astype(float).min())
        if current_price < recent_low * 1.02:
            score += 0.1
            reasoning.append("Pullback to recent support")
        
        # Check for consolidation breakout
        if len(market_data) >= 20:
            consolidation = market_data.tail(20)
            consolidation_high = float(consolidation['high'].astype(float).max())
            consolidation_low = float(consolidation['low'].astype(float).min())
            consolidation_range = ((consolidation_high - consolidation_low) / consolidation_low) if consolidation_low > 0 else 0.0
            
            if consolidation_range < 0.05:  # Tight consolidation
                if current_price > consolidation_high:
                    score += 0.3
                    reasoning.append("Breakout from tight consolidation")
        
        return score, reasoning
    
    def _determine_allocation(
        self, direction_score: float, confidence: float, market_context
    ) -> Tuple[float, List[str]]:
        """Determine position size based on confidence and regime"""
        reasoning = []
        
        # Base position size for swing trading
        base_size = 0.10  # 10% base position
        
        # Scale by confidence
        confidence_multiplier = confidence / 0.65  # Normalize to 65% threshold
        
        # Regime-based exposure limits
        if market_context.regime == MarketRegime.BULL:
            max_exposure = 0.15  # Max 15% in bull
            regime_multiplier = 1.2
        elif market_context.regime == MarketRegime.BEAR:
            max_exposure = 0.10  # Max 10% in bear (shorts allowed)
            regime_multiplier = 0.8
        else:  # HIGH_VOL_CHOP
            max_exposure = 0.05  # Max 5% in choppy markets
            regime_multiplier = 0.5
        
        # Calculate position size
        position_size = base_size * confidence_multiplier * regime_multiplier
        position_size = max(0, min(max_exposure, position_size))
        
        reasoning.append(f"Position size: {position_size*100:.1f}% (confidence-scaled)")
        
        if market_context.regime == MarketRegime.HIGH_VOL_CHOP:
            reasoning.append("Reduced size due to choppy market")
        
        return position_size, reasoning
    
    def _apply_reality_adjustments(
        self, position_size: float, market_context, indicators: Dict[str, Any], market_data: pd.DataFrame
    ) -> Tuple[float, List[str]]:
        """Apply leveraged ETF reality adjustments"""
        reasoning = []
        adjusted_size = position_size
        
        # Volatility decay risk assessment
        decay_risk = 0.0
        
        # VIX-based decay risk
        if market_context.vix > self._reality_cfg["vix_decay_threshold"]:
            decay_risk += 0.3
            reasoning.append(f"High VIX ({market_context.vix:.1f}) - decay risk")
        
        # Realized volatility check
        if len(indicators) > 0:
            atr = SignalEngineUtils.to_float(indicators.get('atr'))
            current_price = SignalEngineUtils.to_float(indicators.get('price', 100))
            if atr is not None and current_price is not None and current_price > 0:
                vol_pct = float(atr) / float(current_price)
                if vol_pct > self._reality_cfg["atr_pct_high_threshold"]:
                    decay_risk += 0.2
                    reasoning.append(f"High realized volatility ({vol_pct*100:.1f}%)")
        
        # Apply adjustment
        if decay_risk > 0.5:
            adjusted_size = 0.0
            reasoning.append("Avoid leveraged ETFs (extreme decay risk)")
        elif decay_risk > 0.3:
            adjusted_size = position_size * self._reality_cfg["size_penalty_high_decay"]
            reasoning.append("Position size reduced by 50% (high decay risk)")
        
        # Chop / decay avoidance (no new APIs; uses existing inputs)
        bb_width = SignalEngineUtils.to_float(indicators.get("bb_width"))
        if bb_width is not None and bb_width < self._reality_cfg["bb_squeeze_threshold"]:
            adjusted_size *= self._reality_cfg["size_penalty_chop"]
            reasoning.append("Bollinger squeeze detected - reduced leveraged exposure")

        momentum_5d = SignalEngineUtils.compute_return(market_data, days=5)
        if (
            momentum_5d is not None
            and abs(momentum_5d) < self._reality_cfg["low_momentum_abs_5d"]
            and market_context.vix > self._reality_cfg["vix_chop_penalty_threshold"]
        ):
            adjusted_size *= self._reality_cfg["size_penalty_chop"]
            reasoning.append(
                f"High VIX + low momentum (5d={momentum_5d*100:.1f}%) - decay penalty applied"
            )

        # High VIX penalty for confidence
        if market_context.vix > self._reality_cfg["vix_high_threshold"]:
            reasoning.append("Signals penalized in high VIX environment")
        
        adjusted_size = max(0.0, float(adjusted_size))
        return adjusted_size, reasoning

    
    
    def _determine_signal(self, direction_score: float, confidence: float, market_context) -> SignalType:
        """Determine final signal"""
        
        # High confidence threshold for swing trading
        if confidence > 0.65 and direction_score > 0.1:
            return SignalType.BUY
        elif confidence > 0.65 and direction_score < -0.1:
            return SignalType.SELL
        else:
            return SignalType.HOLD
    
    def _calculate_swing_entry_exit(
        self, signal: SignalType, market_data: pd.DataFrame, indicators: Dict[str, Any], confidence: float
    ) -> Tuple:
        """Calculate entry, stop loss, and take profit for swing trading"""
        
        if len(market_data) == 0 or signal == SignalType.HOLD:
            return None, None, []
        
        current_price = market_data.iloc[-1]['close']
        
        # Tighter entry range for swing trading
        entry_width = 0.005 if confidence > 0.7 else 0.01  # 0.5-1%
        entry_range = (current_price * (1 - entry_width), current_price * (1 + entry_width))
        
        # Tighter stop loss for swing trading
        stop_distance = 0.03 if confidence > 0.7 else 0.05  # 3-5%
        if signal == SignalType.BUY:
            stop_loss = current_price * (1 - stop_distance)
        else:  # SELL
            stop_loss = current_price * (1 + stop_distance)
        
        # Take profit (2:1 or 3:1 risk/reward)
        profit_distance = stop_distance * 2 if confidence > 0.7 else stop_distance * 3
        if signal == SignalType.BUY:
            take_profit = [current_price * (1 + profit_distance)]
        else:  # SELL
            take_profit = [current_price * (1 - profit_distance)]
        
        return entry_range, stop_loss, take_profit
    
    def _estimate_hold_duration(self, market_context, confidence: float) -> int:
        """Estimate hold duration in days"""
        base_duration = 7  # 1 week base
        
        if confidence > 0.7:
            base_duration = 14  # 2 weeks for high confidence
        
        if market_context.regime == MarketRegime.HIGH_VOL_CHOP:
            base_duration = min(base_duration, 5)  # Shorter holds in chop
        
        return base_duration
    
    def get_engine_metadata(self) -> Dict[str, Any]:
        """Return engine metadata"""
        return {
            'name': self.engine_name,
            'display_name': 'Swing Regime Engine',
            'description': '4-layer architecture for short-term swing trading with regime awareness',
            'tier': 'ELITE',
            'timeframe': 'swing',
            'version': self.engine_version,
            'features': [
                'Market regime detection',
                'Direction confidence (ML features)',
                'Volatility expansion analysis',
                'Risk-adjusted position sizing',
                'Leveraged ETF decay awareness'
            ]
        }
    
    def get_required_indicators(self) -> list:
        """Return required indicators"""
        return [
            'price', 'volume', 'rsi', 'macd', 'macd_signal', 'macd_hist',
            'atr', 'bb_width', 'ema20', 'sma50', 'sma200'
        ]
    
    def get_required_fundamentals(self) -> list:
        """Return required fundamentals"""
        return ['sector', 'market_cap']  # Minimal for swing
