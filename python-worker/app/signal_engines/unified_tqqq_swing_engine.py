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
from app.indicators.indicator_states import (
    IndicatorStates, IndicatorClassifier, SignalDecisionEngine, 
    SignalTextGenerator, classify_all_indicators, generate_professional_signal,
    TradeAction, MACDState, RSIState, TrendState
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

class PositionAction(Enum):
    FULL = "full"
    PARTIAL = "partial"
    SCALE = "scale"
    NONE = "none"


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
    
    @staticmethod
    def map_confidence_to_position(confidence: float, signal: SignalType) -> Dict:
        """
        Converts confidence into execution intent
        """
        if signal == SignalType.HOLD:
            return {"position_action": "none", "position_size_pct": 0.0}
        
        if signal == SignalType.REDUCE:
            # Partial profit taking based on confidence
            return {
                "position_action": "partial_exit", 
                "position_size_pct": 0.3 if confidence >= 0.7 else 0.2,
                "exit_type": "profit_taking"
            }
        
        if signal == SignalType.EXIT:
            # Full exit for risk management
            return {
                "position_action": "full_exit", 
                "position_size_pct": 1.0,
                "exit_type": "risk_management"
            }

        if confidence >= 0.8:
            return {"position_action": "full", "position_size_pct": 1.0}

        if confidence >= 0.65:
            return {"position_action": "scale", "position_size_pct": 0.7}

        if confidence >= 0.5:
            return {"position_action": "partial", "position_size_pct": 0.4}

        return {"position_action": "partial", "position_size_pct": 0.25}


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
        DRY, volatility-aware, execution-ready
        """

        self.logger.info("🔍 Starting TQQQ signal generation", extra={
            "context": {
                "rsi": conditions.rsi,
                "volatility": conditions.volatility,
                "vix_level": conditions.vix_level,
                "price": conditions.current_price,
                "sma_20": conditions.sma_20,
                "sma_50": conditions.sma_50,
                "recent_change": conditions.recent_change,
            }
        })

        try:
            # ------------------------------------------------------------------
            # Step 1: Detect market regime
            # ------------------------------------------------------------------
            regime = self.detect_market_regime(conditions)
            self.logger.info(f"📊 Market regime detected: {regime.value}")

            # ------------------------------------------------------------------
            # Step 2: Regime → base signal dispatch (DRY)
            # ------------------------------------------------------------------
            regime_dispatch = {
                MarketRegime.MEAN_REVERSION: self._mean_reversion_signal,
                MarketRegime.TREND_CONTINUATION: self._trend_continuation_signal,
                MarketRegime.BREAKOUT: self._breakout_signal,
                MarketRegime.VOLATILITY_EXPANSION: self._volatility_expansion_signal,
            }

            signal_fn = regime_dispatch.get(regime)
            if not signal_fn:
                base_signal, confidence, reasoning = (
                    SignalType.HOLD,
                    0.2,
                    ["Unknown or unsupported regime"],
                )
            else:
                base_signal, confidence, reasoning = signal_fn(conditions)

            self.logger.info(
                f"🎯 Base signal generated: {base_signal.value} "
                f"(confidence: {confidence:.2f})"
            )

            # ------------------------------------------------------------------
            # Step 3: Fear / Greed bias overlay
            # ------------------------------------------------------------------
            final_signal, fg_meta = self._apply_fear_greed_bias(
                base_signal, conditions, regime
            )

            # ------------------------------------------------------------------
            # Step 4: Confidence normalization (centralized, DRY)
            # ------------------------------------------------------------------
            if final_signal != base_signal:
                confidence_floor = {
                    SignalType.BUY: 0.5,
                    SignalType.SELL: 0.4,
                    SignalType.HOLD: 0.2,
                    SignalType.REDUCE: 0.3,  # Lower confidence for profit taking
                    SignalType.EXIT: 0.6,   # Higher confidence for risk management
                }
                confidence = max(confidence, confidence_floor[final_signal])
                reasoning.append(
                    f"Signal adjusted by Fear/Greed bias → {final_signal.value}"
                )

            # Hard safety clamps
            confidence = float(min(max(confidence, 0.05), 0.90))

            # Merge Fear/Greed reasoning
            if fg_meta.get("fear_greed_reasoning"):
                reasoning.extend(fg_meta["fear_greed_reasoning"])

            # ------------------------------------------------------------------
            # Step 5: Position sizing & execution intent
            # ------------------------------------------------------------------
            position_meta = self.map_confidence_to_position(confidence, final_signal)

            # Determine trend direction (separate from signal)
            trend_direction = "bullish" if conditions.sma_20 > conditions.sma_50 else "bearish" if conditions.sma_20 < conditions.sma_50 else "neutral"
            
            # Determine risk state
            risk_state = "high" if conditions.rsi > 70 or conditions.volatility > 4.0 else "elevated" if conditions.rsi > 60 or conditions.volatility > 2.5 else "low"

            # Volatility regime clamp (risk-first)
            if regime == MarketRegime.VOLATILITY_EXPANSION:
                position_meta["position_size_pct"] = min(
                    position_meta["position_size_pct"], 0.4
                )
                reasoning.append("Position size capped due to volatility expansion")

            # Partial exit logic (SELL in greed, fade strength)
            if final_signal in [SignalType.SELL, SignalType.REDUCE, SignalType.EXIT]:
                position_meta["exit_size_pct"] = (
                    1.0 if confidence >= 0.7 else 0.25
                )

            # ------------------------------------------------------------------
            # Step 6: Calculate technical and context scores for UI
            # ------------------------------------------------------------------
            
            # Technical Alignment Score (0-1)
            # Based on how well technical indicators align with the signal
            technical_score = 0.0
            
            if final_signal == SignalType.BUY:
                # Buy signal: check bullish technical alignment
                if conditions.rsi < 40:  # Oversold
                    technical_score += 0.3
                if conditions.macd > conditions.macd_signal:  # MACD bullish
                    technical_score += 0.3
                if conditions.sma_20 > conditions.sma_50:  # Uptrend
                    technical_score += 0.4
            elif final_signal == SignalType.SELL:
                # Sell signal: check bearish technical alignment
                if conditions.rsi > 60:  # Overbought
                    technical_score += 0.3
                if conditions.macd < conditions.macd_signal:  # MACD bearish
                    technical_score += 0.3
                if conditions.sma_20 < conditions.sma_50:  # Downtrend
                    technical_score += 0.4
            elif final_signal == SignalType.REDUCE:
                # Reduce signal: partial alignment
                if conditions.rsi > 65:  # Some overbought
                    technical_score += 0.4
                if conditions.recent_change > 0.02:  # Recent gains
                    technical_score += 0.3
                if trend_direction == "bullish":  # Still in uptrend (good for profit taking)
                    technical_score += 0.3
            elif final_signal == SignalType.EXIT:
                # Exit signal: risk-based alignment
                if conditions.volatility > 3.0:  # High volatility
                    technical_score += 0.5
                if conditions.rsi > 70:  # Very overbought
                    technical_score += 0.3
                if trend_direction == "bearish":  # Trend reversed
                    technical_score += 0.2
            else:  # HOLD
                # Hold signal: neutral/mixed conditions
                if 35 <= conditions.rsi <= 65:  # Neutral RSI
                    technical_score += 0.4
                if abs(conditions.recent_change) < 0.02:  # Low recent change
                    technical_score += 0.3
                if conditions.volatility < 2.0:  # Low volatility
                    technical_score += 0.3
            
            # Market Context Score (0-1)
            # Based on broader market conditions
            context_score = 0.0
            
            # VIX contribution (fear gauge)
            if conditions.vix_level < 15:  # Low VIX = complacency (good for profit taking)
                context_score += 0.2 if final_signal in [SignalType.REDUCE, SignalType.SELL] else 0.1
            elif conditions.vix_level > 25:  # High VIX = fear (good for buying)
                context_score += 0.3 if final_signal == SignalType.BUY else 0.1
            else:  # Normal VIX
                context_score += 0.2
            
            # Volatility contribution
            if conditions.volatility < 2.0:  # Low volatility = stable
                context_score += 0.2
            elif conditions.volatility > 4.0:  # High volatility = risky
                context_score += 0.1 if final_signal in [SignalType.EXIT, SignalType.REDUCE] else 0.0
            else:  # Normal volatility
                context_score += 0.2
            
            # Volume contribution
            if conditions.volume > conditions.avg_volume_20d * 1.5:  # High volume = conviction
                context_score += 0.3
            elif conditions.volume < conditions.avg_volume_20d * 0.5:  # Low volume = weak
                context_score += 0.1
            else:  # Normal volume
                context_score += 0.2
            
            # Recent momentum contribution
            if abs(conditions.recent_change) < 0.01:  # Stable
                context_score += 0.2
            elif abs(conditions.recent_change) > 0.03:  # Extreme move
                context_score += 0.1
            else:  # Normal move
                context_score += 0.2
            
            # Clamp scores to 0-1 range
            technical_score = min(max(technical_score, 0.0), 1.0)
            context_score = min(max(context_score, 0.0), 1.0)

            # ------------------------------------------------------------------
            # Step 7: Final structured result
            # ------------------------------------------------------------------
            self.logger.info(
                f"✅ Final TQQQ signal: {final_signal.value}",
                extra={
                    "context": {
                        "base_signal": base_signal.value,
                        "final_signal": final_signal.value,
                        "regime": regime.value,
                        "confidence": confidence,
                        "technical_score": technical_score,
                        "context_score": context_score,
                        "trend_direction": trend_direction,
                        "risk_state": risk_state,
                        "fear_greed_state": fg_meta.get("fear_greed_state"),
                        "fear_greed_bias": fg_meta.get("fear_greed_bias"),
                        "recovery_detected": fg_meta.get("recovery_detected", False),
                        "position_action": position_meta.get("position_action"),
                        "position_size_pct": position_meta.get("position_size_pct"),
                    }
                },
            )

            return SignalResult(
                signal=final_signal,
                confidence=confidence,
                reasoning=reasoning,
                metadata={
                    **position_meta,
                    "engine": "unified_tqqq_swing",
                    "regime": regime.value,
                    "rsi": conditions.rsi,
                    "volatility": conditions.volatility,
                    "recent_change": conditions.recent_change,
                    "sma_20": conditions.sma_20,
                    "sma_50": conditions.sma_50,
                    "trend_direction": trend_direction,
                    "risk_state": risk_state,
                    "technical_score": technical_score,
                    "context_score": context_score,
                    "fear_greed_state": fg_meta.get("fear_greed_state"),
                    "fear_greed_bias": fg_meta.get("fear_greed_bias"),
                    "recovery_detected": fg_meta.get("recovery_detected", False),
                },
            )

        except Exception as e:
            self.logger.error(f"❌ Error generating TQQQ signal: {str(e)}")
            log_exception(self.logger, e, "TQQQ signal generation")
            raise

    
    def _mean_reversion_signal(self, conditions: MarketConditions) -> Tuple[SignalType, float, List[str]]:
        """
        Engine 1: Mean Reversion / Pullback Bounce
        SUPER-ENHANCED: Uses state-based architecture - eliminates contradictions
        """
        
        # 🚀 SUPERIOR ARCHITECTURE: State-based classification (no contradictions)
        try:
            # Step 1: Classify all indicators into states
            states = classify_all_indicators(
                price=conditions.current_price,
                ema20=conditions.ema_20,
                sma50=conditions.sma_50,
                macd=conditions.macd,
                macd_signal=conditions.macd_signal,
                macd_histogram=conditions.macd - conditions.macd_signal,
                rsi=conditions.rsi,
                volatility=conditions.volatility,
                volume=conditions.volume,
                avg_volume=conditions.avg_volume_20d if hasattr(conditions, 'avg_volume_20d') else conditions.volume,
                vix=conditions.vix_level
            )
            
            # Step 2: Make decision based on states only (eliminates contradictions)
            action = SignalDecisionEngine.decide_action(states)
            
            # Step 3: Generate text from states only (eliminates contradictions)
            reasoning = SignalTextGenerator.generate_signal_text(states)
            
            # Step 4: Add action-specific reasoning for educational value
            action_reasoning = SignalTextGenerator.generate_action_reasoning(action, states)
            reasoning.extend(action_reasoning)
            
            # Step 5: Add professional framework context
            reasoning.insert(0, "🧠 State-Based Signal Analysis (No Contradictions)")
            reasoning.insert(1, f"📊 States: {states.trend.value} | {states.macd.value} | {states.rsi.value}")
            reasoning.insert(2, f"📊 Context: {states.volatility.value} | {states.liquidity.value} | {states.fear_greed.value}")
            reasoning.insert(3, f"🎯 Action: {action.value.upper()}")
            
            # Step 6: Convert TradeAction to SignalType
            signal_mapping = {
                TradeAction.BUY: SignalType.BUY,
                TradeAction.ADD: SignalType.ADD,
                TradeAction.HOLD: SignalType.HOLD,
                TradeAction.SELL: SignalType.SELL,
                TradeAction.REDUCE: SignalType.REDUCE
            }
            
            signal_type = signal_mapping.get(action, SignalType.HOLD)
            
            # Step 7: Calculate confidence based on state alignment
            confidence = self._calculate_state_confidence(states, action)
            
            # Step 8: Add state-based reasoning
            reasoning.extend([
                f"✅ State-based decision: {action.value.upper()}",
                f"🎯 Confidence: {confidence:.1%} (state alignment)",
                f"📊 Volume ratio: {states.volume_ratio:.1f}x average",
                "🔒 Contradictions eliminated by state architecture"
            ])
            
            self.logger.info(f"🧠 State-based signal: {signal_type.value} (confidence: {confidence:.2f})", extra={
                'context': {
                    'states': {
                        'trend': states.trend.value,
                        'macd': states.macd.value,
                        'rsi': states.rsi.value,
                        'volatility': states.volatility.value,
                        'liquidity': states.liquidity.value,
                        'fear_greed': states.fear_greed.value
                    },
                    'action': action.value,
                    'confidence': confidence
                }
            })
            
            return signal_type, confidence, reasoning
            
        except Exception as e:
            self.logger.error(f"❌ Error in state-based signal generation: {str(e)}")
            log_exception(self.logger, e, "State-based signal generation")
            
            # Fallback to simple logic
            return SignalType.HOLD, 0.3, ["State-based analysis failed - using fallback"]
    
    def _calculate_state_confidence(self, states: IndicatorStates, action: TradeAction) -> float:
        """
        Calculate confidence based on state alignment
        Higher confidence when more states align with the action
        """
        confidence = 0.5  # Base confidence
        
        # Trend alignment
        if action in {TradeAction.BUY, TradeAction.ADD} and states.trend in {TrendState.BULL, TrendState.STRONG_BULL}:
            confidence += 0.2
        elif action == TradeAction.SELL and states.trend == TrendState.BEAR:
            confidence += 0.2
        elif action == TradeAction.HOLD:
            confidence += 0.1
        
        # Momentum alignment
        if action in {TradeAction.BUY, TradeAction.ADD} and states.macd in {MACDState.RECOVERING, MACDState.BULLISH}:
            confidence += 0.15
        elif action == TradeAction.SELL and states.macd in {MACDState.BEARISH, MACDState.EXHAUSTED}:
            confidence += 0.15
        
        # RSI alignment
        if action in {TradeAction.BUY, TradeAction.ADD} and states.rsi == RSIState.NEUTRAL:
            confidence += 0.1
        elif action == TradeAction.BUY and states.rsi == RSIState.OVERSOLD:
            confidence += 0.15
        elif action in {TradeAction.HOLD, TradeAction.REDUCE} and states.rsi == RSIState.OVERBOUGHT:
            confidence += 0.1
        
        # Liquidity alignment
        if states.liquidity.value in {"STRONG", "NORMAL"}:
            confidence += 0.1
        
        # Volatility alignment
        if states.volatility.value == "NORMAL":
            confidence += 0.1
        elif states.volatility.value == "EXTREME":
            confidence -= 0.2
        
        return min(max(confidence, 0.1), 0.9)  # Clamp between 0.1 and 0.9
    
    def _trend_continuation_signal(self, conditions: MarketConditions) -> Tuple[SignalType, float, List[str]]:
        """
        Engine 2: Trend Continuation
        Works in strong uptrends, captures TQQQ momentum swings
        Professional-grade trend analysis with educational explanations
        """
        
        reasoning = []
        
        # SELL: Trend failure (NEW - was missing!)
        if conditions.current_price < conditions.sma_50:
            reasoning.extend([
                "❌ TREND SELL: Trend Failure - Uptrend Broken",
                "",
                "📊 Technical Analysis:",
                f"• Price Below SMA50: ${conditions.current_price:.2f} < ${conditions.sma_50:.2f}",
                f"• SMA50 Level: ${conditions.sma_50:.2f} (Key long-term trend indicator)",
                f"• RSI Status: {conditions.rsi:.1f} (Momentum indicator)",
                "",
                "💡 What This Means:",
                "• Stock has fallen below its 50-day moving average",
                "• Long-term uptrend has been compromised",
                "• Institutional support level has been broken",
                "• Trend may be reversing to downtrend",
                "",
                "🎯 Trading Strategy:",
                "• Exit positions immediately (70% confidence)",
                "• Cut losses to preserve capital",
                "• Wait for trend to re-establish before re-entering",
                "• Consider short positions if bearish confirmation"
            ])
            return SignalType.SELL, 0.7, reasoning
        
        # SELL: Overbought in trend (NEW - was missing!)
        if conditions.rsi > 70:
            reasoning.extend([
                "⚠️ TREND SELL: Overbought in Trend - Profit Taking Alert",
                "",
                "📊 Technical Analysis:",
                f"• RSI Overbought: {conditions.rsi:.1f} (Above 70 = Extreme optimism)",
                f"• Price vs SMA20: ${conditions.current_price:.2f} vs ${conditions.sma_20:.2f}",
                f"• Trend Status: Still above key moving averages",
                "",
                "💡 What This Means:",
                "• Stock is overextended within current uptrend",
                "• RSI shows extreme optimism - correction likely",
                "• Smart money may be taking profits",
                "• Healthy pullback needed before next leg up",
                "",
                "🎯 Trading Strategy:",
                "• Take partial profits (50% confidence)",
                "• Reduce position size but don't exit completely",
                "• Look for re-entry on pullback to support",
                "• Let winners run but protect profits"
            ])
            return SignalType.SELL, 0.5, reasoning
        
        # HOLD: Price Uptrend + Flat Momentum (Bullish Consolidation)
        price_uptrend_flat_momentum = (
            conditions.current_price > conditions.sma_20 and  # Price structure intact
            conditions.current_price > conditions.sma_50 and  # Uptrend confirmed
            48 <= conditions.rsi <= 58 and                   # Flat momentum (neutral RSI)
            abs(conditions.recent_change) < 0.015              # Minimal recent change
        )
        
        if price_uptrend_flat_momentum:
            reasoning.extend([
                "🟡 HOLD: Bullish Consolidation - Trend Intact, Momentum Flat",
                "",
                "📊 Technical Analysis:",
                f"• Price Structure: ${conditions.current_price:.2f} > SMA20 ${conditions.sma_20:.2f}",
                f"• Uptrend Confirmed: Above SMA50 ${conditions.sma_50:.2f}",
                f"• Momentum Flat: RSI {conditions.rsi:.1f} (Neutral zone)",
                f"• Recent Change: {conditions.recent_change:+.2%} (Minimal movement)",
                "",
                "💡 What This Means:",
                "• Institutions holding positions (not selling)",
                "• Market digesting recent gains",
                "• Trend structure remains intact",
                "• Momentum pausing, not failing",
                "",
                "🎯 Trading Strategy:",
                "• HOLD existing positions (don't exit)",
                "• Consider adding on pullbacks to support",
                "• Wait for momentum confirmation before new breakouts",
                "• Often precedes trend continuation"
            ])
            return SignalType.HOLD, 0.4, reasoning  # Higher confidence for HOLD in consolidation
        
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
        return SignalType.HOLD, 0.3, reasoning  # Changed from 0.0 to 0.3
    
    def _breakout_signal(self, conditions: MarketConditions) -> Tuple[SignalType, float, List[str]]:
        """
        Engine 3: Breakout Detection
        Momentum + volume confirmation → expansion
        Professional-grade breakout analysis with educational explanations
        """
        
        reasoning = []
        
        # Volume Analysis for Breakout Confirmation
        volume_ratio = conditions.volume / conditions.avg_volume_20d if conditions.avg_volume_20d > 0 else 1.0
        volume_above_avg = volume_ratio >= 1.5  # 1.5x average volume requirement
        volume_strong = volume_ratio >= 2.0     # 2x average volume for strong breakout
        
        # Educational volume explanation
        if volume_strong:
            volume_explanation = f"🔥 Exceptional Volume: {volume_ratio:.1f}x normal (Institutional buying detected)"
        elif volume_above_avg:
            volume_explanation = f"📈 Strong Volume: {volume_ratio:.1f}x normal (Healthy buying pressure)"
        else:
            volume_explanation = f"⚠️ Weak Volume: {volume_ratio:.1f}x normal (Lacks conviction)"
        
        # SELL: Overbought in breakout (Profit taking opportunity)
        if conditions.rsi > 68:  # Match regime detection threshold
            reasoning.extend([
                "🚨 BREAKOUT SELL: Overbought Conditions - Profit Taking Alert",
                "",
                "📊 Technical Analysis:",
                f"• RSI Overbought: {conditions.rsi:.1f} (Above 70 = Extreme optimism)",
                f"• Volume Status: {volume_explanation}",
                "",
                "💡 What This Means:",
                "• Stock is overextended after recent rally",
                "• Smart money may be taking profits",
                "• Risk of pullback increases significantly",
                "• Time to consider partial profit taking",
                "",
                "🎯 Trading Strategy:",
                "• Take partial profits on breakout gains",
                "• Reduce exposure to protect capital",
                "• Consider re-entering on pullback to support"
            ])
            return SignalType.SELL, 0.6, reasoning
        
        # SELL: Failed Breakout (Breakdown pattern)
        if conditions.rsi < 57:  # Match regime detection threshold (55 + buffer)
            reasoning.extend([
                "❌ BREAKOUT SELL: Failed Breakout - Capital Protection Alert",
                "",
                "📊 Technical Analysis:",
                f"• RSI Breakdown: {conditions.rsi:.1f} (Below 60 = Momentum lost)",
                f"• Volume Status: {volume_explanation}",
                f"• Price Action: Recent decline {conditions.recent_change:.2%}",
                "",
                "💡 What This Means:",
                "• Breakout has failed - buyers couldn't sustain momentum",
                "• Lack of institutional buying support",
                "• Stock may fall back to previous support levels",
                "• Classic 'fake breakout' pattern detected",
                "",
                "🎯 Trading Strategy:",
                "• Exit positions immediately to limit losses",
                "• Failed breakouts often lead to sharp declines",
                "• Wait for better setup before re-entering",
                "• Capital preservation is priority"
            ])
            return SignalType.SELL, 0.6, reasoning
        
        # BUY: Strong momentum breakout WITH VOLUME CONFIRMATION
        strong_momentum = conditions.recent_change > 0.03
        high_rsi = conditions.rsi > 65
        above_trend = conditions.current_price > conditions.sma_20
        
        if strong_momentum and high_rsi and above_trend and volume_strong:
            reasoning.extend([
                "🚀 BREAKOUT BUY: Strong Momentum Breakout - Institutional Grade Signal",
                "",
                "📊 Technical Analysis:",
                f"• Price Surge: {conditions.recent_change:.2%} (Strong momentum)",
                f"• RSI Strength: {conditions.rsi:.1f} (Above 65 = Bullish momentum)",
                f"• Trend Position: ${conditions.current_price:.2f} > ${conditions.sma_20:.2f} SMA20 (Above key moving average)",
                f"• Volume Confirmation: {volume_explanation}",
                "",
                "💡 What This Means:",
                "• All breakout criteria met with institutional volume support",
                "• Strong buying pressure from market participants",
                "• Momentum likely to continue in near term",
                "• Professional-grade breakout pattern confirmed",
                "",
                "🎯 Trading Strategy:",
                "• Enter position with confidence (85% success probability)",
                "• Consider pyramiding position as breakout sustains",
                "• Set stop-loss below breakout support level",
                "• Target 10-15% gains in coming weeks"
            ])
            return SignalType.BUY, 0.85, reasoning  # Higher confidence with volume
        
        # BUY: Moderate breakout WITH VOLUME CONFIRMATION
        moderate_momentum = conditions.recent_change > 0.02
        moderate_rsi = conditions.rsi > 60
        
        if moderate_momentum and moderate_rsi and above_trend and volume_above_avg:
            reasoning.extend([
                "📈 BREAKOUT BUY: Momentum Breakout - Confirmed Uptrend",
                "",
                "📊 Technical Analysis:",
                f"• Price Movement: {conditions.recent_change:.2%} (Healthy momentum)",
                f"• RSI Level: {conditions.rsi:.1f} (Above 60 = Emerging strength)",
                f"• Trend Status: ${conditions.current_price:.2f} > ${conditions.sma_20:.2f} SMA20 (Above moving average)",
                f"• Volume Support: {volume_explanation}",
                "",
                "💡 What This Means:",
                "• Stock breaking out with solid volume confirmation",
                "• Buying momentum building across market participants",
                "• Trend likely to continue with support",
                "• Good risk/reward setup for swing trading",
                "",
                "🎯 Trading Strategy:",
                "• Enter position with moderate confidence (75% success probability)",
                "• Use position sizing based on risk tolerance",
                "• Set stop-loss below recent support level",
                "• Target 5-10% gains over 1-2 weeks"
            ])
            return SignalType.BUY, 0.75, reasoning
        
        # HOLD: Breakout without volume confirmation (suspect)
        if (strong_momentum and high_rsi and above_trend) or (moderate_momentum and moderate_rsi and above_trend):
            reasoning.extend([
                "⏸️ BREAKOUT HOLD: Suspect Breakout - Wait for Confirmation",
                "",
                "📊 Technical Analysis:",
                f"• Price Action: {conditions.recent_change:.2%} (Breakout attempt)",
                f"• RSI Status: {conditions.rsi:.1f} (Momentum indicator)",
                f"• Volume Issue: {volume_explanation}",
                "",
                "💡 What This Means:",
                "• Price is breaking out but lacks institutional support",
                "• Low volume suggests weak buying conviction",
                "• High probability of fake breakout (60% failure rate)",
                "• Professional traders wait for volume confirmation",
                "",
                "🎯 Trading Strategy:",
                "• DO NOT chase this breakout - high risk of failure",
                "• Wait for volume to pick up (1.5x+ average)",
                "• Better to miss opportunity than lose capital",
                "• Re-evaluate if volume improves in next sessions"
            ])
            return SignalType.HOLD, 0.4, reasoning
        
        reasoning.extend([
            "🔄 BREAKOUT HOLD: No Clear Setup - Waiting for Opportunity",
            "",
            "📊 Technical Analysis:",
            f"• RSI Level: {conditions.rsi:.1f} (Neutral momentum)",
            f"• Volume Status: {volume_explanation}",
            "",
            "💡 What This Means:",
            "• Stock not showing clear breakout patterns",
            "• Mixed signals - not worth the risk currently",
            "• Better opportunities exist elsewhere",
            "",
            "🎯 Trading Strategy:",
            "• Stay on sidelines and monitor for better setup",
            "• Look for stocks with clearer breakout patterns",
            "• Patience is key to successful trading"
        ])
        return SignalType.HOLD, 0.3, reasoning  # Changed from 0.0 to 0.3
    
    def _volatility_expansion_signal(self, conditions: MarketConditions) -> Tuple[SignalType, float, List[str]]:
        """
        Engine 4: Volatility Expansion with Signal Ladder
        Enhanced logic with fear/recovery transition states
        Professional-grade volatility analysis with educational explanations
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
        
        # Step 2: Apply signal ladder logic with educational explanations
        if fear_state == "fear_rising":
            # Fear rising = SELL / Reduce
            reasoning.extend([
                "🚨 VOLATILITY SELL: Fear Rising - Market Stress Alert",
                "",
                "📊 Technical Analysis:",
                f"• VIX Level: {conditions.vix_level:.2f} (Elevated fear index)",
                f"• Volatility: {conditions.volatility:.1f}% (High market volatility)",
                f"• Price Action: Recent decline {conditions.recent_change:.2%}",
                "",
                "💡 What This Means:",
                "• Market fear is increasing rapidly",
                "• VIX (Fear Index) shows elevated stress levels",
                "• High volatility indicates market uncertainty",
                "• Institutional investors reducing risk exposure",
                "",
                "🎯 Trading Strategy:",
                "• Reduce positions immediately (70% confidence)",
                "• Move to defensive assets or cash",
                "• Avoid catching falling knives",
                "• Wait for volatility to stabilize before re-entering"
            ])
            self.logger.warning("📉 Fear rising - SELL signal generated")
            return SignalType.SELL, 0.7, reasoning
        
        elif fear_state == "extreme_fear":
            # Extreme fear = HOLD (don't sell into panic)
            reasoning.extend([
                "⏸️ VOLATILITY HOLD: Extreme Fear - Panic Zone Alert",
                "",
                "📊 Technical Analysis:",
                f"• VIX Level: {conditions.vix_level:.2f} (Extreme fear readings)",
                f"• Volatility: {conditions.volatility:.1f}% (Very high volatility)",
                f"• RSI: {conditions.rsi:.1f} (Oversold conditions)",
                "",
                "💡 What This Means:",
                "• Market in extreme panic/capitulation phase",
                "• Smart money often starts buying at these levels",
                "• Selling now could mean missing recovery bounce",
                "• High volatility can reverse quickly",
                "",
                "🎯 Trading Strategy:",
                "• HOLD positions (don't sell into panic)",
                "• Wait for volatility to flatten or green candle",
                "• Look for stabilization signs before action",
                "• Consider buying if you have high risk tolerance"
            ])
            self.logger.info("⏸️ Extreme Fear - HOLD signal (don't sell into panic)")
            return SignalType.HOLD, 0.4, reasoning
        
        elif fear_state == "fear_stabilizing":
            # Fear stabilizing = BUY (small)
            reasoning.extend([
                "📈 VOLATILITY BUY: Fear Stabilizing - Recovery Opportunity",
                "",
                "📊 Technical Analysis:",
                f"• VIX Level: {conditions.vix_level:.2f} (Fear starting to ease)",
                f"• Volatility: {conditions.volatility:.1f}% (Stabilizing volatility)",
                f"• RSI: {conditions.rsi:.1f} (Potential oversold bounce)",
                "",
                "💡 What This Means:",
                "• Market panic is subsiding",
                "• Volatility starting to normalize",
                "• Early signs of recovery emerging",
                "• Professional traders start building positions",
                "",
                "🎯 Trading Strategy:",
                "• BUY small position (60% confidence)",
                "• Scale in gradually as recovery confirms",
                "• Set tight stop-losses (high volatility environment)",
                "• Target quick gains as volatility provides opportunities"
            ])
            self.logger.info("📈 Fear stabilizing - BUY signal (recovery opportunity)")
            return SignalType.BUY, 0.6, reasoning
        
        # SELL: High volatility with any negative change
        if conditions.recent_change < 0 and conditions.volatility > 5.0:
            reasoning.extend([
                "🚨 VOLATILITY SELL: Risk-Off with Decline - Market Stress",
                "",
                "📊 Technical Analysis:",
                f"• Price Decline: {conditions.recent_change:.2%} (Negative momentum)",
                f"• High Volatility: {conditions.volatility:.1f}% (Above 5% threshold)",
                f"• VIX Level: {conditions.vix_level:.2f} (Fear gauge)",
                "",
                "💡 What This Means:",
                "• High volatility combined with price decline is dangerous",
                "• Market participants are panicking and selling",
                "• Risk-off environment - capital preservation priority",
                "• Institutional money flowing out of markets",
                "",
                "🎯 Trading Strategy:",
                "• Reduce exposure immediately (70% confidence)",
                "• Consider defensive assets or cash positions",
                "• Avoid bottom fishing in high volatility",
                "• Wait for volatility to normalize before re-entering"
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
        return SignalType.HOLD, 0.3, reasoning  # Changed from 0.0 to 0.3
    
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
        Enhanced SELL-in-Greed logic - FIXED
        """
        
        # RSI overbought (higher threshold for true greed)
        rsi_overbought = conditions.rsi >= 70  # Was 65
        
        # Price extended (more realistic threshold)
        price_extended = conditions.current_price > conditions.sma_20 * 1.10  # 10% above SMA20
        
        # Momentum stalling (corrected logic)
        momentum_stalling = 0.005 <= conditions.recent_change <= 0.02  # 0.5-2% (not 1-3%)
        
        # High volatility but not extreme
        high_volatility = 3.0 < conditions.volatility < 8.0  # Not extreme volatility
        
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
            
            # TQQQ-specific bias rules (3x leverage caution) - FIXED LOGIC
            tqqq_specific_rules = {
                "strongly_bullish": {
                    "SELL": ("HOLD", {"reason": "TQQQ: Convert SELL to HOLD in strong bullish bias (3x caution)"}),
                    "HOLD": ("BUY", {"reason": "TQQQ: Convert HOLD to BUY in strong bullish bias"})
                },
                "bullish": {
                    "SELL": ("REDUCE", {"reason": "TQQQ: Convert SELL to REDUCE in bullish bias (profit taking)"}),
                    "HOLD": ("HOLD", {"reason": "TQQQ: Maintain HOLD in bullish bias"})
                },
                "strongly_bearish": {
                    "BUY": ("EXIT", {"reason": "TQQQ: Convert BUY to EXIT in strong bearish bias (3x risk)"}),
                    "HOLD": ("SELL", {"reason": "TQQQ: Convert HOLD to SELL in strong bearish bias"})
                },
                "bearish": {
                    "BUY": ("REDUCE", {"reason": "TQQQ: Convert BUY to REDUCE in bearish bias (risk reduction)"}),
                    "HOLD": ("HOLD", {"reason": "TQQQ: Maintain HOLD in bearish bias"})
                },
                "greed": {
                    "BUY": ("HOLD", {"reason": "TQQQ: Block BUY in greed zone (don't chase)"}),
                    "HOLD": ("REDUCE", {"reason": "TQQQ: Reduce position in greed zone (profit taking)"}),
                    "SELL": ("REDUCE", {"reason": "TQQQ: Convert SELL to REDUCE in greed zone (profit taking)"})
                },
                "fear": {
                    "SELL": ("HOLD", {"reason": "TQQQ: Convert SELL to HOLD in fear zone (don't panic)"}),
                    "HOLD": ("BUY", {"reason": "TQQQ: Convert HOLD to BUY in fear zone (buy in fear)"}),
                    "BUY": ("BUY", {"reason": "TQQQ: Maintain BUY in fear zone (add to position)"})
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
