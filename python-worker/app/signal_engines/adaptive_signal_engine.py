"""
Adaptive Signal Engine
Implements institutional-grade adaptive signal generation with market regime, volatility, and relative strength awareness
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from app.signal_engines.signal_calculator_core import SignalType, SignalResult, MarketConditions
from app.services.market_regime_service import MarketRegimeService, MarketRegime
from app.services.volatility_profiler_service import VolatilityProfilerService, VolatilityProfile
from app.services.relative_strength_service import RelativeStrengthService, RelativeStrengthTier
from app.adaptive_config_matrix import ConfigMatrix
from app.observability.logging import get_logger

logger = get_logger(__name__)

@dataclass
class SignalScore:
    buy_score: float = 0.0      # 0-1
    sell_score: float = 0.0     # 0-1
    hold_score: float = 0.0     # 0-1
    reduce_score: float = 0.0   # 0-1
    confidence: float = 0.0     # 0-1
    reasoning: List[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.reasoning is None:
            self.reasoning = []
        if self.metadata is None:
            self.metadata = {}
    
    def get_primary_signal(self) -> SignalType:
        """Convert scores back to binary for compatibility"""
        scores = {
            SignalType.BUY: self.buy_score,
            SignalType.SELL: self.sell_score,
            SignalType.HOLD: self.hold_score,
            SignalType.REDUCE: self.reduce_score
        }
        return max(scores, key=scores.get)

class AdaptiveSignalEngine:
    """Adaptive signal engine with market regime, volatility, and relative strength awareness"""
    
    def __init__(self):
        self.regime_service = MarketRegimeService()
        self.volatility_service = VolatilityProfilerService()
        self.rs_service = RelativeStrengthService()
        self.config_matrix = ConfigMatrix()
        
    def generate_signal_score(self, symbol: str, conditions: MarketConditions) -> SignalScore:
        """Generate adaptive signal score with multi-factor analysis"""
        
        try:
            # 1. Market Regime Detection
            market_regime_data = self.regime_service.detect_market_regime()
            market_regime = market_regime_data.regime
            
            # 2. Volatility Profiling
            market_data = {
                'atr': getattr(conditions, 'atr', None),
                'close': conditions.current_price
            }
            vol_data = self.volatility_service.get_volatility_profile(symbol, market_data)
            vol_profile = vol_data.profile
            
            # 3. Relative Strength Analysis
            rs_data = self.rs_service.analyze_relative_strength(symbol)
            rs_tier = rs_data.tier
            
            # 4. Get Adaptive Configuration
            config = self.config_matrix.get_config(vol_profile, market_regime, rs_tier)
            
            # 5. Calculate Component Scores
            trend_score = self._calculate_trend_score(conditions, config)
            momentum_score = self._calculate_momentum_score(conditions, config)
            breakout_score = self._calculate_breakout_score(conditions, config)
            
            # 6. Apply Relative Strength Filter
            if not self.rs_service.should_allow_long_signals(rs_tier):
                momentum_score.buy_score *= 0.2  # Severely penalize long signals
                momentum_score.reasoning.append(f"Blocked: Negative relative strength vs SPY ({rs_data.relative_strength:.2%})")
            else:
                rs_multiplier = self.rs_service.get_relative_strength_filter_multiplier(rs_tier)
                momentum_score.buy_score *= rs_multiplier
                if rs_multiplier < 1.0:
                    momentum_score.reasoning.append(f"Reduced: Relative strength vs SPY ({rs_data.relative_strength:.2%})")
            
            # 7. Combine Scores with Adaptive Weights
            final_score = self._combine_scores(trend_score, momentum_score, breakout_score, config)
            
            # 8. Add Market Context Metadata
            final_score.metadata.update({
                'market_regime': market_regime.value,
                'volatility_profile': vol_profile.value,
                'relative_strength': rs_tier.value,
                'relative_strength_value': rs_data.relative_strength,
                'volatility_atr_pct': vol_data.atr_pct,
                'volatility_percentile': vol_data.atr_percentile,
                'config_used': config,
                'regime_confidence': market_regime_data.confidence,
                'momentum_consistency': rs_data.momentum_consistency
            })
            
            # 9. Apply Final Confidence Adjustments
            final_score.confidence = self._adjust_confidence(final_score, config, market_regime_data)
            
            logger.debug(f"Generated adaptive signal for {symbol}: {final_score.get_primary_signal().value} (confidence: {final_score.confidence:.2f})")
            
            return final_score
            
        except Exception as e:
            logger.error(f"Error generating adaptive signal for {symbol}: {e}")
            # Return default score on error
            return SignalScore(
                buy_score=0.0,
                sell_score=0.0,
                hold_score=1.0,
                reduce_score=0.0,
                confidence=0.0,
                reasoning=[f"Error in signal generation: {str(e)}"],
                metadata={'error': str(e)}
            )
    
    def _calculate_trend_score(self, conditions: MarketConditions, config: Dict[str, Any]) -> SignalScore:
        """Calculate trend-based signal score"""
        score = SignalScore()
        
        # Trend direction analysis
        is_uptrend = (conditions.sma_20 > conditions.sma_50 and 
                      conditions.current_price > conditions.sma_20)
        is_downtrend = (conditions.sma_20 < conditions.sma_50 and 
                       conditions.current_price < conditions.sma_20)
        
        # Long-term trend (if available)
        long_term_uptrend = hasattr(conditions, 'sma_200') and conditions.sma_200 and \
                           conditions.current_price > conditions.sma_200
        
        if is_uptrend:
            if long_term_uptrend:
                score.buy_score = 0.7
                score.reasoning.append("Strong uptrend: Price > SMA20 > SMA50 > SMA200")
            else:
                score.buy_score = 0.5
                score.reasoning.append("Medium uptrend: Price > SMA20 > SMA50")
        elif is_downtrend:
            if hasattr(conditions, 'sma_200') and conditions.sma_200 and \
               conditions.current_price < conditions.sma_200:
                score.sell_score = 0.6
                score.reasoning.append("Strong downtrend: Price < SMA20 < SMA50 < SMA200")
            else:
                score.sell_score = 0.4
                score.reasoning.append("Medium downtrend: Price < SMA20 < SMA50")
        else:
            score.hold_score = 0.6
            score.reasoning.append("Sideways trend: Mixed SMA signals")
        
        # Apply configuration adjustments
        rsi_oversold = config.get('rsi_oversold', 35)
        rsi_overbought = config.get('rsi_overbought', 70)
        
        # RSI trend confirmation
        if conditions.rsi < rsi_oversold and is_uptrend:
            score.buy_score = min(score.buy_score + 0.2, 1.0)
            score.reasoning.append(f"Trend + Oversold RSI ({conditions.rsi:.1f} < {rsi_oversold})")
        elif conditions.rsi > rsi_overbought and is_downtrend:
            score.sell_score = min(score.sell_score + 0.2, 1.0)
            score.reasoning.append(f"Trend + Overbought RSI ({conditions.rsi:.1f} > {rsi_overbought})")
        
        return score
    
    def _calculate_momentum_score(self, conditions: MarketConditions, config: Dict[str, Any]) -> SignalScore:
        """Calculate momentum-based signal score"""
        score = SignalScore()
        
        # RSI momentum
        rsi_oversold = config.get('rsi_oversold', 35)
        rsi_overbought = config.get('rsi_overbought', 70)
        rsi_extreme_oversold = config.get('rsi_extreme_oversold', 25)
        rsi_extreme_overbought = config.get('rsi_extreme_overbought', 80)
        
        if conditions.rsi < rsi_extreme_oversold:
            score.buy_score = 0.8
            score.reasoning.append(f"Extreme oversold: RSI {conditions.rsi:.1f} < {rsi_extreme_oversold}")
        elif conditions.rsi < rsi_oversold:
            score.buy_score = 0.6
            score.reasoning.append(f"Oversold: RSI {conditions.rsi:.1f} < {rsi_oversold}")
        elif conditions.rsi > rsi_extreme_overbought:
            score.sell_score = 0.8
            score.reasoning.append(f"Extreme overbought: RSI {conditions.rsi:.1f} > {rsi_extreme_overbought}")
        elif conditions.rsi > rsi_overbought:
            score.sell_score = 0.6
            score.reasoning.append(f"Overbought: RSI {conditions.rsi:.1f} > {rsi_overbought}")
        
        # Recent price momentum
        breakout_threshold = config.get('breakout_threshold', 0.02)
        if conditions.recent_change > breakout_threshold:
            momentum_boost = min(conditions.recent_change / 0.05, 0.3)  # Cap at 0.3
            score.buy_score = min(score.buy_score + momentum_boost, 1.0)
            score.reasoning.append(f"Price momentum: +{conditions.recent_change:.2%}")
        elif conditions.recent_change < -breakout_threshold:
            momentum_boost = min(abs(conditions.recent_change) / 0.05, 0.3)
            score.sell_score = min(score.sell_score + momentum_boost, 1.0)
            score.reasoning.append(f"Price momentum: {conditions.recent_change:.2%}")
        
        # MACD confirmation
        if hasattr(conditions, 'macd') and hasattr(conditions, 'macd_signal'):
            if conditions.macd and conditions.macd_signal and conditions.macd > conditions.macd_signal:
                if score.buy_score > 0:
                    score.buy_score = min(score.buy_score + 0.1, 1.0)
                    score.reasoning.append("MACD bullish confirmation")
            elif conditions.macd and conditions.macd_signal and conditions.macd < conditions.macd_signal:
                if score.sell_score > 0:
                    score.sell_score = min(score.sell_score + 0.1, 1.0)
                    score.reasoning.append("MACD bearish confirmation")
        
        return score
    
    def _calculate_breakout_score(self, conditions: MarketConditions, config: Dict[str, Any]) -> SignalScore:
        """Calculate breakout-based signal score"""
        score = SignalScore()
        
        # Breakout conditions
        breakout_threshold = config.get('breakout_threshold', 0.02)
        breakout_rsi_upper = config.get('breakout_rsi_upper_bound', 65)
        
        # Price breakout above SMA20 with momentum
        if (conditions.recent_change > breakout_threshold and 
            conditions.rsi > 55 and conditions.rsi < breakout_rsi_upper and
            conditions.current_price > conditions.sma_20):
            
            score.buy_score = 0.7
            score.reasoning.append(f"Breakout: Price > SMA20, RSI {conditions.rsi:.1f}, momentum +{conditions.recent_change:.2%}")
        
        # Failed breakout (RSI drops below 55 after breakout attempt)
        elif (conditions.recent_change < 0 and conditions.rsi < 55 and 
              conditions.current_price < conditions.sma_20):
            
            score.sell_score = 0.6
            score.reasoning.append(f"Failed breakout: RSI {conditions.rsi:.1f}, price below SMA20")
        
        # Volume confirmation (if available)
        if hasattr(conditions, 'volume') and hasattr(conditions, 'avg_volume_20d'):
            if conditions.volume and conditions.avg_volume_20d and conditions.avg_volume_20d > 0:
                volume_ratio = conditions.volume / conditions.avg_volume_20d
                
                if score.buy_score > 0.5 and volume_ratio > 1.5:
                    score.buy_score = min(score.buy_score + 0.1, 1.0)
                    score.reasoning.append(f"Volume confirmation: {volume_ratio:.1f}x average")
                elif score.sell_score > 0.5 and volume_ratio > 2.0:
                    score.sell_score = min(score.sell_score + 0.1, 1.0)
                    score.reasoning.append(f"High volume selling: {volume_ratio:.1f}x average")
        
        return score
    
    def _combine_scores(self, trend_score: SignalScore, momentum_score: SignalScore, 
                       breakout_score: SignalScore, config: Dict[str, Any]) -> SignalScore:
        """Combine component scores with adaptive weights"""
        
        final_score = SignalScore()
        
        # Get adaptive weights from config
        weights = config.get('score_weights', {
            'trend': 0.3,
            'momentum': 0.4,
            'breakout': 0.3
        })
        
        # Combine buy scores
        final_score.buy_score = (
            trend_score.buy_score * weights['trend'] +
            momentum_score.buy_score * weights['momentum'] +
            breakout_score.buy_score * weights['breakout']
        )
        
        # Combine sell scores
        final_score.sell_score = (
            trend_score.sell_score * weights['trend'] +
            momentum_score.sell_score * weights['momentum'] +
            breakout_score.sell_score * weights['breakout']
        )
        
        # Combine hold scores
        final_score.hold_score = (
            trend_score.hold_score * weights['trend'] +
            momentum_score.hold_score * weights['momentum'] +
            breakout_score.hold_score * weights['breakout']
        )
        
        # Combine reduce scores
        final_score.reduce_score = (
            trend_score.reduce_score * weights['trend'] +
            momentum_score.reduce_score * weights['momentum'] +
            breakout_score.reduce_score * weights['breakout']
        )
        
        # Combine reasoning
        all_reasoning = (trend_score.reasoning + momentum_score.reasoning + 
                        breakout_score.reasoning)
        final_score.reasoning = list(dict.fromkeys(all_reasoning))  # Remove duplicates
        
        # Calculate initial confidence
        max_score = max(final_score.buy_score, final_score.sell_score, 
                       final_score.hold_score, final_score.reduce_score)
        final_score.confidence = max_score
        
        return final_score
    
    def _adjust_confidence(self, score: SignalScore, config: Dict[str, Any], 
                          market_regime_data) -> float:
        """Apply final confidence adjustments"""
        
        confidence = score.confidence
        
        # Apply confidence boost from config
        confidence_boost = config.get('confidence_boost', 0.0)
        confidence += confidence_boost
        
        # Apply regime-based adjustments
        regime_confidence = market_regime_data.confidence
        confidence *= (0.5 + regime_confidence * 0.5)  # Scale by regime confidence
        
        # Apply volatility-based adjustments
        vol_profile = score.metadata.get('volatility_profile')
        if vol_profile == VolatilityProfile.HIGH.value:
            confidence *= 0.9  # Reduce confidence in high volatility
        elif vol_profile == VolatilityProfile.LOW.value:
            confidence *= 1.1  # Boost confidence in low volatility
        
        # Apply relative strength consistency adjustments
        momentum_consistency = score.metadata.get('momentum_consistency', 0.5)
        confidence *= (0.7 + momentum_consistency * 0.3)  # Scale by consistency
        
        # Ensure confidence stays in valid range
        return max(0.0, min(confidence, 1.0))
    
    def generate_signal_result(self, symbol: str, conditions: MarketConditions) -> SignalResult:
        """Generate SignalResult for compatibility with existing systems"""
        
        # Get adaptive signal score
        signal_score = self.generate_signal_score(symbol, conditions)
        
        # Convert to SignalResult
        primary_signal = signal_score.get_primary_signal()
        
        return SignalResult(
            signal=primary_signal,
            confidence=signal_score.confidence,
            reasoning=signal_score.reasoning,
            metadata=signal_score.metadata
        )
