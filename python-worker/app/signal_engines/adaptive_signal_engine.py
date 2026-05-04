"""
Adaptive Signal Engine
Implements institutional-grade adaptive signal generation with market regime, volatility, and relative strength awareness
Refactored to use centralized services for DRY architecture and clean confidence calculation
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
from app.services.component_normalizer_service import ComponentNormalizer
from app.services.confidence_calculator_service import ConfidenceCalculator
from app.services.volatility_percentile_service import VolatilityPercentileService
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
    """Adaptive signal engine with market regime, volatility, and relative strength awareness
    Refactored to use centralized services for clean confidence calculation
    """
    
    def __init__(self):
        self.regime_service = MarketRegimeService()
        self.volatility_service = VolatilityProfilerService()
        self.rs_service = RelativeStrengthService()
        self.config_matrix = ConfigMatrix()
        
        # New centralized services for DRY architecture
        self.component_normalizer = ComponentNormalizer()
        self.confidence_calculator = ConfidenceCalculator()
        self.volatility_percentile_service = VolatilityPercentileService()
        
        logger.info("AdaptiveSignalEngine initialized with centralized services")
        
    def generate_signal_score(self, symbol: str, conditions: MarketConditions) -> SignalScore:
        """Generate adaptive signal score with clean confidence architecture"""
        
        try:
            # 1. Market Regime Detection
            market_regime_data = self.regime_service.detect_market_regime()
            market_regime = market_regime_data.regime
            
            # 2. Relative Strength Analysis (for RS filter and component)
            rs_data = self.rs_service.analyze_relative_strength(symbol)
            rs_tier = rs_data.tier
            
            # 3. Volatility Percentile Calculation (FIXED - uses true rank percentile)
            volatility_profile = self.volatility_percentile_service.calculate_volatility_profile(symbol)
            volatility_percentile = volatility_profile['percentile']
            
            # 4. Prepare Market Data for Normalization
            market_data = {
                'current_price': conditions.current_price,
                'sma_20': conditions.sma_20,
                'sma_50': conditions.sma_50,
                'sma_200': getattr(conditions, 'sma_200', None),
                'rsi': conditions.rsi,
                'rsi_history': getattr(conditions, 'rsi_history', None),
                'macd': getattr(conditions, 'macd', None),
                'macd_signal': getattr(conditions, 'macd_signal', None),
                'relative_strength': rs_data.relative_strength,
                'volatility_percentile': volatility_percentile,
                'volume': getattr(conditions, 'volume', None),
                'avg_volume_20d': getattr(conditions, 'avg_volume_20d', None),
                'volume_history': getattr(conditions, 'volume_history', None),
                'ema_20': getattr(conditions, 'ema_20', None),
                # For breakout calculation
                'recent_high': getattr(conditions, 'recent_high', conditions.current_price * 1.05),
                'recent_low': getattr(conditions, 'recent_low', conditions.current_price * 0.95),
                'atr': volatility_profile.get('current_atr', conditions.volatility)
            }
            
            # 5. Normalize All Components to [-1, +1] (DRY - centralized)
            normalized_components = self.component_normalizer.normalize_all_components(market_data)
            
            # 6. Apply Relative Strength Filter (if negative, penalize long signals)
            if not self.rs_service.should_allow_long_signals(rs_tier):
                if 'momentum' in normalized_components:
                    normalized_components['momentum'] *= 0.2  # Severely penalize
                logger.info(f"Applied RS filter for {symbol}: negative RS ({rs_data.relative_strength:.2%})")
            
            # 7. Calculate Clean Confidence Architecture (DRY - centralized)
            direction_score, environment_confidence, final_confidence = self.confidence_calculator.calculate_complete_confidence(
                normalized_components=normalized_components,
                regime=market_regime.value,
                volatility_percentile=volatility_percentile,
                regime_data={
                    'regime_confidence': market_regime_data.confidence,
                    'momentum_consistency': rs_data.momentum_consistency
                }
            )
            
            # 8. Convert Direction Score to Signal Scores (for compatibility)
            signal_scores = self._direction_score_to_signal_scores(direction_score, normalized_components)
            
            # 9. Create Final Signal Score
            final_score = SignalScore(
                buy_score=signal_scores['buy'],
                sell_score=signal_scores['sell'],
                hold_score=signal_scores['hold'],
                reduce_score=signal_scores['reduce'],
                confidence=final_confidence,
                reasoning=self._generate_reasoning(direction_score, normalized_components, market_regime, rs_data, volatility_profile),
                metadata={
                    'market_regime': market_regime.value,
                    'volatility_profile': volatility_profile['profile'],
                    'relative_strength': rs_tier.value,
                    'relative_strength_value': rs_data.relative_strength,
                    'volatility_atr_pct': volatility_profile.get('current_atr', 0),
                    'volatility_percentile': volatility_percentile,
                    'regime_confidence': market_regime_data.confidence,
                    'momentum_consistency': rs_data.momentum_consistency,
                    'direction_score': direction_score,
                    'environment_confidence': environment_confidence,
                    'normalized_components': normalized_components,
                    'architecture': 'clean_multiplicative_v2'
                }
            )
            
            logger.info(f"Generated adaptive signal for {symbol}: {final_score.get_primary_signal().value} "
                       f"(confidence: {final_confidence:.3f}, direction: {direction_score:.3f})")
            
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
    
    def _direction_score_to_signal_scores(self, direction_score: float, normalized_components: Dict[str, float]) -> Dict[str, float]:
        """
        Convert direction score to individual signal scores for compatibility
        Uses the magnitude of direction score to determine signal strength
        """
        abs_direction = abs(direction_score)
        
        if direction_score > 0.1:  # Bullish
            return {
                'buy': abs_direction,
                'sell': 0.0,
                'hold': max(0.0, 1.0 - abs_direction),
                'reduce': 0.0
            }
        elif direction_score < -0.1:  # Bearish
            return {
                'buy': 0.0,
                'sell': abs_direction,
                'hold': max(0.0, 1.0 - abs_direction),
                'reduce': 0.0
            }
        else:  # Neutral
            return {
                'buy': 0.0,
                'sell': 0.0,
                'hold': 1.0,
                'reduce': 0.0
            }
    
    def _generate_reasoning(
        self, 
        direction_score: float, 
        normalized_components: Dict[str, float],
        market_regime: MarketRegime,
        rs_data,
        volatility_profile: Dict[str, Any]
    ) -> List[str]:
        """
        Generate reasoning based on the new architecture components
        """
        reasoning = []
        
        # Trend reasoning
        if 'trend' in normalized_components:
            trend_val = normalized_components['trend']
            if trend_val > 0.5:
                reasoning.append("Strong uptrend: Price > SMA20 > SMA50")
            elif trend_val < -0.5:
                reasoning.append("Medium downtrend: Price < SMA20 < SMA50")
        
        # Relative Strength reasoning
        if rs_data.relative_strength < -0.15:
            reasoning.append(f"Blocked: Negative relative strength vs SPY ({rs_data.relative_strength:.2%})")
        elif rs_data.relative_strength > 0.15:
            reasoning.append(f"Boosted: Positive relative strength vs SPY ({rs_data.relative_strength:.2%})")
        
        # Momentum reasoning
        if 'momentum' in normalized_components:
            momentum_val = normalized_components['momentum']
            if momentum_val > 0.3:
                reasoning.append("Strong momentum: RSI oversold + MACD bullish")
            elif momentum_val < -0.3:
                reasoning.append("Weak momentum: RSI overbought + MACD bearish")

        # RSI trend reasoning (swing-entry style: rising off ~40)
        if 'rsi_trend' in normalized_components:
            rsi_trend_val = normalized_components['rsi_trend']
            if rsi_trend_val > 0.35:
                reasoning.append("RSI strengthening (rising off support zone)")
            elif rsi_trend_val < -0.35:
                reasoning.append("RSI weakening (rolling over)")

        # Volume confirmation reasoning
        if 'volume_confirmation' in normalized_components:
            vol_conf = normalized_components['volume_confirmation']
            if vol_conf > 0.35:
                reasoning.append("Volume confirmation: above-average participation")
            elif vol_conf < -0.35:
                reasoning.append("Low participation: below-average volume")

        # Breakout confirmation reasoning (EMA + volume confirmation + volume trend)
        try:
            breakout_raw = float(normalized_components.get('breakout_raw', 0.0) or 0.0)
            breakout_adj = float(normalized_components.get('breakout', 0.0) or 0.0)
            if breakout_raw > 0.25 and breakout_adj < breakout_raw * 0.6:
                reasoning.append("Breakout not confirmed: lacking EMA/volume expansion confirmation")
            elif breakout_raw > 0.25 and breakout_adj >= breakout_raw:
                reasoning.append("Breakout confirmed: above EMA with expanding volume")
        except Exception:
            pass
        
        # Volatility reasoning
        vol_percentile = volatility_profile['percentile']
        if vol_percentile < 0.2:
            reasoning.append(f"Low volatility environment (ATR {vol_percentile:.1%} percentile)")
        elif vol_percentile > 0.8:
            reasoning.append(f"High volatility environment (ATR {vol_percentile:.1%} percentile)")
        
        # Regime reasoning
        reasoning.append(f"Market regime: {market_regime.value}")
        
        # Direction summary
        if direction_score > 0.3:
            reasoning.append("Overall bullish bias across multiple factors")
        elif direction_score < -0.3:
            reasoning.append("Overall bearish bias across multiple factors")
        else:
            reasoning.append("Mixed signals with no clear directional edge")
        
        return reasoning
