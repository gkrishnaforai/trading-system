"""
Unified TQQQ Swing Signal Engine
High-Level Design: Always generate signals with regime classification
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np

from app.signal_engines.signal_calculator_core import (
    SignalType, MarketConditions, SignalConfig, SignalResult
)
from app.engines.fear_greed_engine import (
    create_fear_greed_engine, apply_fear_greed_bias, MarketData
)
from app.observability.logging import get_logger, log_exception, log_with_context


class MarketRegime(Enum):
    """Market regime classification"""
    MEAN_REVERSION = "mean_reversion"
    TREND_CONTINUATION = "trend_continuation"
    BREAKOUT = "breakout"
    VOLATILITY_EXPANSION = "volatility_expansion"


@dataclass
class SignalMetadata:
    """Metadata for signal tracking and analysis"""
    regime: str
    rsi: float
    volatility: float
    recent_change: float
    sma_20: float
    sma_50: float
    confidence: float
    reasoning: List[str]


class UnifiedTQQQSwingEngine:
    """
    Unified TQQQ Swing Signal Engine with Fear/Greed Integration
    
    Design Principles:
    1. Always generate a signal (BUY/SELL/HOLD)
    2. First classify market regime
    3. Apply regime-specific logic
    4. Integrate Fear/Greed bias for enhanced signals
    5. Recovery Detection in volatility expansion
    6. No dead zones or fallbacks
    7. Optimizer-friendly with clear signal attribution
    """
    
    def __init__(self, config: SignalConfig):
        self.config = config
        # Initialize Fear/Greed engine for ETFs
        self.fear_greed_engine = create_fear_greed_engine("etf")
        # Initialize logger
        self.logger = get_logger(__name__)
        self.logger.info("🚀 Unified TQQQ Swing Engine initialized with Fear/Greed integration")
    
    def detect_market_regime(self, conditions: MarketConditions) -> MarketRegime:
        """
        Determines which regime should be active
        Priority: Volatility > Mean Reversion (extreme RSI) > Trend > Breakout > Mean Reversion
        """
        
        # Calculate trend conditions (more relaxed for TQQQ)
        is_uptrend = (
            conditions.sma_20 > conditions.sma_50 and
            conditions.current_price > conditions.sma_50  # More relaxed: above SMA50 instead of SMA20
        )
        
        is_downtrend = (
            conditions.sma_20 < conditions.sma_50 and
            conditions.current_price < conditions.sma_50
        )
        
        # Priority 1: Volatility Expansion (risk-off) - working threshold for TQQQ
        if conditions.volatility > 4.0:  # Back to working threshold
            return MarketRegime.VOLATILITY_EXPANSION
        
        # Priority 2: Extreme RSI conditions (mean reversion priority)
        if conditions.rsi > 70 or conditions.rsi < 30:  # Extreme RSI gets priority
            return MarketRegime.MEAN_REVERSION
        
        # Priority 3: Trend Continuation
        if is_uptrend:
            return MarketRegime.TREND_CONTINUATION
        elif is_downtrend:  # Any downtrend = risk-off for TQQQ
            return MarketRegime.VOLATILITY_EXPANSION
        
        # Priority 4: Breakout (price expansion + momentum) - but NOT for overbought conditions
        if (
            conditions.recent_change > 0.02 and  # Reduced from 0.03
            conditions.rsi > 55 and conditions.rsi < 70 and  # Added upper bound to avoid overbought
            conditions.current_price > conditions.sma_20
        ):
            return MarketRegime.BREAKOUT
        
        # Priority 5: Default → Mean Reversion / Bounce
        return MarketRegime.MEAN_REVERSION
    
    def generate_signal(self, conditions: MarketConditions) -> SignalResult:
        """
        Unified signal generator with Fear/Greed integration
        """
        
        # Log signal generation start
        self.logger.info("🔍 Starting TQQQ signal generation", extra={
            'context': {
                'rsi': conditions.rsi,
                'volatility': conditions.volatility,
                'vix_level': conditions.vix_level,
                'price': conditions.current_price,
                'sma_20': conditions.sma_20,
                'sma_50': conditions.sma_50,
                'recent_change': conditions.recent_change
            }
        })
        
        try:
            # Step 1: Classify market regime
            regime = self.detect_market_regime(conditions)
            self.logger.info(f"📊 Market regime detected: {regime.value}")
            
            # Step 2: Apply regime-specific logic
            if regime == MarketRegime.MEAN_REVERSION:
                signal, confidence, reasoning = self._mean_reversion_signal(conditions)
            
            elif regime == MarketRegime.TREND_CONTINUATION:
                signal, confidence, reasoning = self._trend_continuation_signal(conditions)
            
            elif regime == MarketRegime.BREAKOUT:
                signal, confidence, reasoning = self._breakout_signal(conditions)
            
            elif regime == MarketRegime.VOLATILITY_EXPANSION:
                signal, confidence, reasoning = self._volatility_expansion_signal(conditions)
            
            else:
                signal, confidence, reasoning = SignalType.HOLD, 0.0, ["Unknown regime"]
            
            self.logger.info(f"🎯 Base signal generated: {signal.value} (confidence: {confidence:.2f})")
            
            # Step 3: Apply Fear/Greed bias
            final_signal, fear_greed_adjustments = self._apply_fear_greed_bias(
                signal, conditions, regime
            )
            
            # Step 4: Merge reasoning
            if fear_greed_adjustments.get('fear_greed_reasoning'):
                reasoning.extend(fear_greed_adjustments['fear_greed_reasoning'])
            
            # Step 5: Create metadata for tracking
            metadata = SignalMetadata(
                regime=regime.value,
                rsi=conditions.rsi,
                volatility=conditions.volatility,
                recent_change=conditions.recent_change,
                sma_20=conditions.sma_20,
                sma_50=conditions.sma_50,
                confidence=confidence,
                reasoning=reasoning
            )
            
            # Log final signal
            self.logger.info(f"✅ Final TQQQ signal: {final_signal.value}", extra={
                'context': {
                    'base_signal': signal.value,
                    'final_signal': final_signal.value,
                    'regime': regime.value,
                    'confidence': confidence,
                    'fear_greed_state': fear_greed_adjustments.get('fear_greed_state'),
                    'fear_greed_bias': fear_greed_adjustments.get('fear_greed_bias'),
                    'recovery_detected': fear_greed_adjustments.get('recovery_detected', False),
                    'reasoning_count': len(reasoning)
                }
            })
            
            return SignalResult(
                signal=final_signal,
                confidence=confidence,
                reasoning=reasoning,
                metadata={
                    "regime": regime.value,
                    "rsi": conditions.rsi,
                    "volatility": conditions.volatility,
                    "recent_change": conditions.recent_change,
                    "sma_20": conditions.sma_20,
                    "sma_50": conditions.sma_50,
                    "engine": "unified_tqqq_swing",
                    "fear_greed_state": fear_greed_adjustments.get('fear_greed_state'),
                    "fear_greed_bias": fear_greed_adjustments.get('fear_greed_bias'),
                    "recovery_detected": fear_greed_adjustments.get('recovery_detected', False)
                }
            )
            
        except Exception as e:
            self.logger.error(f"❌ Error generating TQQQ signal: {str(e)}")
            log_exception(self.logger, e, "TQQQ signal generation")
            raise
    
    def _mean_reversion_signal(self, conditions: MarketConditions) -> Tuple[SignalType, float, List[str]]:
        """
        Engine 1: Mean Reversion / Pullback Bounce
        Works in non-trending or weak-trend markets
        """
        
        is_oversold = conditions.rsi < self.config.rsi_oversold
        is_moderately_oversold = conditions.rsi < self.config.rsi_moderately_oversold
        is_recently_down = conditions.recent_change < -0.02
        
        # SELL conditions (NEW - was missing!)
        is_overbought = conditions.rsi > 65  # Lowered from 68
        is_recently_up = conditions.recent_change > 0.015  # Lowered from 0.02
        
        reasoning = []
        
        # SELL: Overbought with recent strength (more aggressive)
        if is_overbought and is_recently_up:
            reasoning.extend([
                "Mean reversion: Overbought with recent strength",
                f"RSI overbought: {conditions.rsi:.1f}",
                f"Recent rise: {conditions.recent_change:.2%}",
                "Mean reversion sell expected",
                "Take profits now"
            ])
            return SignalType.SELL, 0.6, reasoning
        
        # SELL: Overbought even without recent strength (NEW)
        if is_overbought:
            reasoning.extend([
                "Mean reversion: Overbought conditions",
                f"RSI overbought: {conditions.rsi:.1f}",
                "Price likely to revert",
                "Sell into strength",
                "Risk management"
            ])
            return SignalType.SELL, 0.5, reasoning
        
        # SELL: Recent strength in neutral RSI (NEW - higher threshold)
        if 50 < conditions.rsi < 60 and conditions.recent_change > 0.04:  # Increased from 55 and 0.03
            reasoning.extend([
                "Mean reversion: Recent strength in neutral zone",
                f"RSI neutral: {conditions.rsi:.1f}",
                f"Recent rise: {conditions.recent_change:.2%}",
                "Likely mean reversion",
                "Sell into momentum"
            ])
            return SignalType.SELL, 0.4, reasoning
        
        # BUY conditions (existing logic)
        if is_oversold and is_recently_down:
            reasoning.extend([
                "Strong oversold with recent decline",
                f"RSI oversold: {conditions.rsi:.1f}",
                f"Recent decline: {conditions.recent_change:.2%}",
                "Mean reversion bounce expected"
            ])
            return SignalType.BUY, 0.7, reasoning
        
        elif is_oversold:
            reasoning.extend([
                "Oversold stabilization",
                f"RSI oversold: {conditions.rsi:.1f}",
                "Bottoming pattern detected"
            ])
            return SignalType.BUY, 0.6, reasoning
        
        elif is_moderately_oversold and is_recently_down:
            reasoning.extend([
                "Moderately oversold with decline",
                f"RSI moderately oversold: {conditions.rsi:.1f}",
                f"Recent decline: {conditions.recent_change:.2%}",
                "Support level likely"
            ])
            return SignalType.BUY, 0.5, reasoning
        
        reasoning.extend([
            "Mean reversion: No clear setup",
            f"RSI neutral: {conditions.rsi:.1f}",
            "Waiting for extreme levels"
        ])
        return SignalType.HOLD, 0.0, reasoning
    
    def _trend_continuation_signal(self, conditions: MarketConditions) -> Tuple[SignalType, float, List[str]]:
        """
        Engine 2: Trend Continuation
        Works in strong uptrends, captures TQQQ momentum swings
        """
        
        reasoning = []
        
        # SELL: Trend failure (NEW - was missing!)
        if conditions.current_price < conditions.sma_50:
            reasoning.extend([
                "Trend continuation: Trend failure",
                f"Below SMA50: ${conditions.sma_50:.2f}",
                f"Current price: ${conditions.current_price:.2f}",
                "Trend breakdown detected",
                "Exit position"
            ])
            return SignalType.SELL, 0.7, reasoning
        
        # SELL: Overbought in trend (NEW - was missing!)
        if conditions.rsi > 70:
            reasoning.extend([
                "Trend continuation: Overbought",
                f"RSI overbought: {conditions.rsi:.1f}",
                "Take profits in trend",
                "Reduce exposure"
            ])
            return SignalType.SELL, 0.5, reasoning
        
        # BUY: Pullback to SMA20 in uptrend (relaxed conditions)
        pullback_to_sma = (
            conditions.current_price <= conditions.sma_20 and  # Allow equality
            conditions.current_price > conditions.sma_50
        )
        
        if pullback_to_sma and 35 < conditions.rsi < 60:  # Expanded RSI range
            reasoning.extend([
                "Trend continuation: Healthy pullback",
                f"Price pulled back to SMA20: ${conditions.sma_20:.2f}",
                f"RSI in pullback zone: {conditions.rsi:.1f}",
                f"Above SMA50 support: ${conditions.sma_50:.2f}",
                "Trend resumption expected"
            ])
            return SignalType.BUY, 0.65, reasoning
        
        # BUY: Shallow pullback in strong uptrend
        shallow_pullback = (
            conditions.current_price > conditions.sma_20 and
            conditions.rsi < 50 and
            conditions.recent_change < -0.01
        )
        
        if shallow_pullback:
            reasoning.extend([
                "Trend continuation: Shallow pullback",
                f"RSI reset: {conditions.rsi:.1f}",
                f"Minor decline: {conditions.recent_change:.2%}",
                "Above all trend lines"
            ])
            return SignalType.BUY, 0.55, reasoning
        
        reasoning.extend([
            "Trend continuation: No setup",
            f"RSI: {conditions.rsi:.1f}",
            "Wait for pullback"
        ])
        return SignalType.HOLD, 0.0, reasoning
    
    def _breakout_signal(self, conditions: MarketConditions) -> Tuple[SignalType, float, List[str]]:
        """
        Engine 3: Breakout Detection
        Momentum + volatility contraction → expansion
        """
        
        reasoning = []
        
        # SELL: Overbought in breakout (NEW - was missing!)
        if conditions.rsi > 68:  # Match regime detection threshold
            reasoning.extend([
                "Breakout: Overbought conditions",
                f"RSI overbought: {conditions.rsi:.1f}",
                "Take profits on breakout",
                "Reduce exposure"
            ])
            return SignalType.SELL, 0.6, reasoning
        
        # SELL: Failed breakout
        if conditions.rsi < 57:  # Match regime detection threshold (55 + buffer)
            reasoning.extend([
                "Breakout: Failed breakout",
                f"RSI collapsed: {conditions.rsi:.1f}",
                "Breakout failure, exit",
                "Cut losses on failed breakout"
            ])
            return SignalType.SELL, 0.6, reasoning
        
        # BUY: Strong momentum breakout
        strong_momentum = conditions.recent_change > 0.03
        high_rsi = conditions.rsi > 65
        above_trend = conditions.current_price > conditions.sma_20
        
        if strong_momentum and high_rsi and above_trend:
            reasoning.extend([
                "Breakout: Strong momentum",
                f"Recent surge: {conditions.recent_change:.2%}",
                f"High RSI: {conditions.rsi:.1f}",
                f"Above trend: ${conditions.sma_20:.2f}",
                "Momentum breakout confirmed"
            ])
            return SignalType.BUY, 0.75, reasoning
        
        # BUY: Moderate breakout
        moderate_momentum = conditions.recent_change > 0.02
        moderate_rsi = conditions.rsi > 60
        
        if moderate_momentum and moderate_rsi and above_trend:
            reasoning.extend([
                "Breakout: Moderate momentum",
                f"Recent rise: {conditions.recent_change:.2%}",
                f"Elevated RSI: {conditions.rsi:.1f}",
                "Breakout continuation"
            ])
            return SignalType.BUY, 0.6, reasoning
        
        reasoning.extend([
            "Breakout: No clear setup",
            f"RSI: {conditions.rsi:.1f}",
            "Waiting for momentum"
        ])
        return SignalType.HOLD, 0.0, reasoning
    
    def _volatility_expansion_signal(self, conditions: MarketConditions) -> Tuple[SignalType, float, List[str]]:
        """
        Engine 4: Volatility Expansion with Signal Ladder
        Enhanced logic with fear/recovery transition states
        """
        
        reasoning = []
        
        # Log volatility expansion analysis
        self.logger.info("🌊 Analyzing volatility expansion regime", extra={
            'context': {
                'volatility': conditions.volatility,
                'vix_level': conditions.vix_level,
                'recent_change': conditions.recent_change,
                'rsi': conditions.rsi
            }
        })
        
        # Step 1: Analyze Fear/Greed state ladder
        fear_state = self._analyze_fear_state_ladder(conditions)
        self.logger.info(f"😨 Fear state ladder: {fear_state}")
        
        # Step 2: Apply signal ladder logic
        if fear_state == "fear_rising":
            # Fear rising = SELL / Reduce
            reasoning.extend([
                "Signal Ladder: Fear rising",
                "VIX elevated and volatility increasing",
                "Risk-off: Reduce positions",
                f"VIX: {conditions.vix_level:.2f}",
                f"Volatility: {conditions.volatility:.1f}%",
                "Market stress increasing"
            ])
            self.logger.warning("📉 Fear rising - SELL signal generated")
            return SignalType.SELL, 0.7, reasoning
        
        elif fear_state == "extreme_fear":
            # Extreme fear = HOLD (don't sell into panic)
            reasoning.extend([
                "Signal Ladder: Extreme Fear",
                "High VIX and volatility but NOT exhaustion confirmed",
                "HOLD or SELL → HOLD",
                "WAIT FOR: volatility flattening or another green close",
                f"VIX: {conditions.vix_level:.2f}",
                f"Volatility: {conditions.volatility:.1f}%",
                "Avoid selling into panic bounce"
            ])
            self.logger.info("⏸️ Extreme Fear - HOLD signal (don't sell into panic)")
            return SignalType.HOLD, 0.4, reasoning
        
        elif fear_state == "fear_stabilizing":
            # Fear stabilizing = BUY (small)
            reasoning.extend([
                "Signal Ladder: Fear stabilizing",
                "Volatility flattening and recovery signs",
                "BUY (small size) - recovery opportunity",
                f"RSI recovery: {conditions.rsi:.1f}",
                f"Recent change: {conditions.recent_change:.2%}",
                "Mean-reversion bounce setup"
            ])
            self.logger.info("🔄 Fear stabilizing - BUY signal (small size)")
            return SignalType.BUY, 0.5, reasoning
        
        elif fear_state == "recovery_confirmed":
            # Recovery confirmed = BUY (normal)
            reasoning.extend([
                "Signal Ladder: Recovery confirmed",
                "Multiple recovery signals confirmed",
                "BUY (normal size) - recovery trade",
                f"Strong recovery: RSI {conditions.rsi:.1f}",
                f"Positive momentum: {conditions.recent_change:.2%}",
                "Recovery leg in progress"
            ])
            self.logger.info("📈 Recovery confirmed - BUY signal (normal size)")
            return SignalType.BUY, 0.6, reasoning
        
        # Step 3: Fallback to original logic for other cases
        # SELL: Sharp decline (more aggressive)
        if conditions.recent_change < -0.02:  # Any decline > 2%
            reasoning.extend([
                "Volatility expansion: Sharp decline detected",
                f"Recent decline: {conditions.recent_change:.2%}",
                f"High volatility: {conditions.volatility:.1f}%",
                "Risk-off: Exit positions immediately",
                "Capital preservation mode"
            ])
            return SignalType.SELL, 0.8, reasoning
        
        # SELL: High volatility with any negative change
        if conditions.recent_change < 0 and conditions.volatility > 5.0:
            reasoning.extend([
                "Volatility expansion: Risk-off with decline",
                f"Negative change: {conditions.recent_change:.2%}",
                f"High volatility: {conditions.volatility:.1f}%",
                "Market stress detected",
                "Reduce exposure"
            ])
            return SignalType.SELL, 0.7, reasoning
        
        # ENHANCED: Very high volatility - check for fear exhaustion first
        if conditions.volatility > 8.0:
            # Check if this is fear exhaustion (recovery setup)
            if self._is_fear_exhaustion(conditions):
                reasoning.extend([
                    "Volatility expansion: Fear exhaustion detected",
                    f"Extreme volatility: {conditions.volatility:.1f}%",
                    "Potential capitulation bottom",
                    "Watch for recovery signals",
                    "Risk-off but prepare for bounce"
                ])
                return SignalType.HOLD, 0.3, reasoning  # Hold with low confidence
            else:
                reasoning.extend([
                    "Volatility expansion: Extreme volatility",
                    f"Very high volatility: {conditions.volatility:.1f}%",
                    "Market uncertainty high",
                    "Risk-off: Stay in cash",
                    "Wait for stability"
                ])
                return SignalType.SELL, 0.6, reasoning
        
        # ENHANCED: SELL-in-Greed logic
        if self._is_greed_sell_setup(conditions):
            reasoning.extend([
                "Volatility expansion: SELL-in-Greed setup",
                f"RSI overbought: {conditions.rsi:.1f}",
                f"Price extended: ${conditions.current_price:.2f} vs SMA20: ${conditions.sma_20:.2f}",
                "Volatility rising or momentum stalling",
                "Take profits / scale out"
            ])
            return SignalType.SELL, 0.6, reasoning
        
        # BUY: Strong oversold in volatile market (cautious)
        if conditions.rsi < 25 and conditions.recent_change > -0.05:
            reasoning.extend([
                "Volatility expansion: Deep oversold bounce",
                f"Extreme oversold: {conditions.rsi:.1f}",
                f"Recent decline: {conditions.recent_change:.2%}",
                "Potential bounce opportunity",
                "Small position only"
            ])
            return SignalType.BUY, 0.5, reasoning
        
        reasoning.extend([
            "Volatility expansion: No clear setup",
            f"Volatility: {conditions.volatility:.1f}%",
            f"Recent change: {conditions.recent_change:.2%}",
            "Wait for clarity",
            "Risk management priority"
        ])
        return SignalType.HOLD, 0.0, reasoning
    
    def _analyze_fear_state_ladder(self, conditions: MarketConditions) -> str:
        """
        Signal Ladder: Analyze fear/recovery state
        
        States:
        - fear_rising: SELL / Reduce
        - extreme_fear: HOLD (don't sell into panic)
        - fear_stabilizing: BUY (small)
        - recovery_confirmed: BUY (normal)
        """
        
        vix_level = conditions.vix_level  # Now available from conditions
        volatility = conditions.volatility
        rsi = conditions.rsi
        recent_change = conditions.recent_change
        
        # Get volatility trend from conditions
        volatility_trend = conditions.volatility_trend
        
        # Step 1: Check for Extreme Fear (your May 19 example)
        if (vix_level >= 25.0 and volatility >= 8.0 and 35 <= rsi <= 50):
            # Check if exhaustion confirmed
            if self._is_fear_exhaustion(conditions):
                return "fear_stabilizing"  # Ready for recovery
            else:
                return "extreme_fear"  # HOLD, don't sell into panic
        
        # Step 2: Check for Fear Rising
        if (vix_level >= 22.0 and volatility >= 6.0 and 
            recent_change < 0 and rsi < 45):
            return "fear_rising"  # SELL / Reduce
        
        # Step 3: Check for Fear Stabilizing
        if (volatility >= 4.0 and recent_change > 0.015 and 42 <= rsi <= 55):
            return "fear_stabilizing"  # BUY (small)
        
        # Step 4: Check for Recovery Confirmed
        if (recent_change > 0.02 and rsi >= 45 and rsi <= 65 and
            volatility_trend in ['stable', 'falling']):
            return "recovery_confirmed"  # BUY (normal)
        
        # Default: No clear fear state
        return "neutral"
    
    def _detect_fear_recovery(self, conditions: MarketConditions) -> bool:
        """
        🟢 Recovery Setup (BUY-in-Fear) - Enhanced with ladder logic
        """
        fear_state = self._analyze_fear_state_ladder(conditions)
        return fear_state in ["fear_stabilizing", "recovery_confirmed"]
    
    def _is_fear_exhaustion(self, conditions: MarketConditions) -> bool:
        """
        Check if high volatility represents fear exhaustion (potential bottom)
        """
        
        # Very high volatility
        extreme_vol = conditions.volatility > 8.0
        
        # RSI in fear zone but not extreme oversold
        rsi_fear_zone = 35 <= conditions.rsi <= 45
        
        # Recent change not too negative (stabilizing)
        stabilizing = conditions.recent_change > -0.03  # Not declining more than 3%
        
        return extreme_vol and rsi_fear_zone and stabilizing
    
    def _is_greed_sell_setup(self, conditions: MarketConditions) -> bool:
        """
        Enhanced SELL-in-Greed logic
        SELL when:
        - RSI ≥ 65
        - AND price extended above SMA20
        - AND volatility rising OR momentum stalling
        """
        
        # RSI overbought
        rsi_overbought = conditions.rsi >= 65
        
        # Price extended above SMA20
        price_extended = conditions.current_price > conditions.sma_20 * 1.03  # 3% above SMA20
        
        # Momentum stalling (recent change not strong)
        momentum_stalling = 0.01 <= conditions.recent_change <= 0.03  # Weak positive change
        
        # High volatility (rising)
        high_volatility = conditions.volatility > 5.0
        
        return rsi_overbought and price_extended and (momentum_stalling or high_volatility)
    
    def _apply_fear_greed_bias(self, signal: SignalType, conditions: MarketConditions, 
                             regime: MarketRegime) -> Tuple[SignalType, Dict]:
        """
        Apply Fear/Greed bias to base signal
        """
        
        self.logger.info(f"🎭 Applying Fear/Greed bias to {signal.value} signal", extra={
            'context': {
                'base_signal': signal.value,
                'regime': regime.value,
                'vix_level': conditions.vix_level,
                'volatility': conditions.volatility
            }
        })
        
        try:
            # Prepare market data for Fear/Greed engine
            market_data = MarketData(
                vix_level=conditions.vix_level,  # Now available from conditions
                volatility=conditions.volatility,
                rsi=conditions.rsi,
                price=conditions.current_price,
                sma20=conditions.sma_20,
                sma50=conditions.sma_50,
                volatility_trend=conditions.volatility_trend,
                volume=0.0,  # Default value - not available in MarketConditions
                avg_volume=0.0,  # Default value - not available in MarketConditions
                asset_type="etf"  # Default asset type
            )
            
            # Get Fear/Greed analysis
            fear_greed_analysis = self.fear_greed_engine.calculate_fear_greed_state(market_data)
            
            # Check if Fear/Greed analysis returned an error state
            if (fear_greed_analysis.state.value == 'neutral' and 
                fear_greed_analysis.confidence == 0.0 and 
                fear_greed_analysis.raw_score == 0.0):
                self.logger.warning("⚠️ Fear/Greed engine returned error state", extra={
                    'context': {
                        'error_reasoning': fear_greed_analysis.reasoning,
                        'market_data': {
                            'vix_level': market_data.vix_level,
                            'volatility': market_data.volatility,
                            'rsi': market_data.rsi,
                            'price': market_data.price
                        }
                    }
                })
            
            self.logger.info(f"🧠 Fear/Greed analysis: {fear_greed_analysis.state.value} (bias: {fear_greed_analysis.signal_bias})", extra={
                'context': {
                    'fear_greed_state': fear_greed_analysis.state.value,
                    'fear_greed_bias': fear_greed_analysis.signal_bias,
                    'fear_greed_confidence': fear_greed_analysis.confidence,
                    'fear_greed_score': fear_greed_analysis.raw_score
                }
            })
            
            # TQQQ-specific bias rules (3x leverage caution)
            tqqq_specific_rules = {
                "strongly_bullish": {
                    "SELL": ("HOLD", {"reason": "TQQQ: Convert SELL to HOLD in strong bullish bias (3x caution)"}),
                    "HOLD": ("BUY", {"reason": "TQQQ: Convert HOLD to BUY in strong bullish bias"})
                },
                "bullish": {
                    "SELL": ("HOLD", {"reason": "TQQQ: Soften SELL to HOLD in bullish bias (3x caution)"})
                },
                "strongly_bearish": {
                    "BUY": ("SELL", {"reason": "TQQQ: Convert BUY to SELL in strong bearish bias (3x risk)"}),
                    "HOLD": ("SELL", {"reason": "TQQQ: Convert HOLD to SELL in strong bearish bias"})
                },
                "bearish": {
                    "BUY": ("HOLD", {"reason": "TQQQ: Soften BUY to HOLD in bearish bias (3x caution)"})
                }
            }
            
            # Apply universal bias function with TQQQ-specific rules
            # Convert SignalType enum to string for the bias function
            base_signal_str = signal.value if hasattr(signal, 'value') else str(signal)
            
            final_signal, adjustments = apply_fear_greed_bias(
                base_signal_str,  # Pass as string
                fear_greed_analysis,
                tqqq_specific_rules
            )
            
            # Convert back to SignalType (handle case conversion)
            if isinstance(final_signal, str):
                final_signal_lower = final_signal.lower()
                try:
                    final_signal_type = SignalType(final_signal_lower)
                except ValueError:
                    # If signal not found in enum, default to HOLD
                    self.logger.warning(f"⚠️ Unknown signal '{final_signal}', defaulting to HOLD")
                    final_signal_type = SignalType.HOLD
            else:
                final_signal_type = final_signal
            
            self.logger.info(f"⚡ Fear/Greed bias applied: {signal.value} → {final_signal_type.value}", extra={
                'context': {
                    'base_signal': signal.value,
                    'final_signal': final_signal_type.value,
                    'bias_applied': adjustments.get('reason')
                }
            })
            
            # Add Fear/Greed context to adjustments
            adjustments.update({
                'fear_greed_state': fear_greed_analysis.state.value,
                'fear_greed_bias': fear_greed_analysis.signal_bias,
                'fear_greed_reasoning': fear_greed_analysis.reasoning,
                'recovery_detected': regime == MarketRegime.VOLATILITY_EXPANSION and 
                                  self._detect_fear_recovery(conditions)
            })
            
            return final_signal_type, adjustments
            
        except Exception as e:
            self.logger.error(f"❌ Error applying Fear/Greed bias: {str(e)}")
            log_exception(self.logger, e, "Fear/Greed bias application")
            # Return original signal if bias application fails
            return signal, {'error': str(e)}


# Factory function for easy instantiation
def create_unified_tqqq_engine(config: SignalConfig) -> UnifiedTQQQSwingEngine:
    """Create unified TQQQ swing engine with default configuration"""
    return UnifiedTQQQSwingEngine(config)
