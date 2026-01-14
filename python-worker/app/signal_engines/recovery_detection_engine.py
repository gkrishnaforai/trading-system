#!/usr/bin/env python3
"""
RecoveryDetectionEngine - BUY-Before-Breakout Signal Engine

Detects early recovery patterns in bearish trends with institutional accumulation.
Targets the sweet spot before breakout confirmation for optimal risk/reward.

Engine Philosophy:
- Buy in fear → Early relief rally
- Capture smart money accumulation
- Activate before SMA breaks
- Produce asymmetric risk entries

Author: Trading System
Date: 2026-01-06
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging

from app.signal_engines.base import BaseSignalEngine
from app.signal_engines.signal_calculator_core import SignalType, MarketConditions
from app.utils.market_data_utils import (
    calculate_relative_strength, 
    check_price_stability,
    get_symbol_indicators_data,
    calculate_market_regime_context
)
from app.observability.logging import get_logger

logger = get_logger(__name__)


class RecoveryLayer(Enum):
    """Recovery detection layers for systematic analysis"""
    CONTEXT_GATE = "context_gate"
    DOWNTREND_WEAKENING = "downtrend_weakening"
    MOMENTUM_SHIFT = "momentum_shift"
    ACCUMULATION_CONFIRMATION = "accumulation_confirmation"
    RELATIVE_STRENGTH_FILTER = "relative_strength_filter"


@dataclass
class RecoveryAnalysis:
    """Comprehensive recovery analysis results"""
    layer_results: Dict[RecoveryLayer, bool]
    layer_reasons: Dict[RecoveryLayer, str]
    confidence_score: float
    position_size_recommendation: float
    risk_level: str
    metadata: Dict[str, float]


class RecoveryDetectionEngine(BaseSignalEngine):
    """
    Recovery Detection Engine - BUY-Before-Breakout Strategy
    
    Detects early recovery patterns when:
    1. Market context is favorable (VIX < 25, volatility controlled)
    2. Downtrend is weakening (no new lows, price stabilizing)
    3. Momentum is shifting positive (MACD, RSI patterns)
    4. Accumulation is confirmed (high volume, bullish price action)
    5. Relative strength vs market is positive (outperforming SPY)
    """
    
    def __init__(self, max_volatility: float = 8.0):
        """
        Initialize Recovery Detection Engine
        
        Args:
            max_volatility: Maximum allowed volatility for recovery trades
        """
        self.max_volatility = max_volatility
        self.engine_name = "RecoveryDetectionEngine"
        self.required_indicators = self._get_required_indicators()
        
    def _get_required_indicators(self) -> List[str]:
        """Return required indicators for recovery detection"""
        return [
            'close', 'high', 'low', 'open', 'volume',
            'sma_20', 'sma_50', 'ema_20',
            'rsi_14', 'macd', 'macd_signal',
            'avg_volume_20d'
        ]
    
    def analyze(self, symbol: str, conditions: MarketConditions) -> SignalType:
        """
        Analyze symbol for recovery signals
        
        Args:
            symbol: Stock/ETF symbol
            conditions: Current market conditions
            
        Returns:
            SignalType: BUY/HOLD/SELL recommendation
        """
        try:
            logger.info(f"🔄 Starting Recovery Detection Analysis for {symbol}")
            
            # Get comprehensive analysis
            analysis = self._analyze_recovery_layers(symbol, conditions)
            
            # Log detailed decision process
            self._log_analysis_decision(symbol, analysis)
            
            # Convert analysis to signal
            if analysis.confidence_score >= 0.55:
                logger.info(f"🟢 RECOVERY BUY SIGNAL: {symbol} (Confidence: {analysis.confidence_score:.2f})")
                return SignalType.BUY
            else:
                logger.info(f"⚪ NO RECOVERY SIGNAL: {symbol} (Confidence: {analysis.confidence_score:.2f})")
                return SignalType.HOLD
                
        except Exception as e:
            logger.error(f"❌ Recovery Detection Engine failed for {symbol}: {e}")
            return SignalType.HOLD
    
    def _analyze_recovery_layers(self, symbol: str, conditions: MarketConditions) -> RecoveryAnalysis:
        """
        Systematic 5-layer recovery analysis
        
        Args:
            symbol: Stock/ETF symbol
            conditions: Current market conditions
            
        Returns:
            RecoveryAnalysis: Comprehensive analysis results
        """
        layer_results = {}
        layer_reasons = {}
        confidence_factors = {}
        
        # Layer 1: Context Gate (Market Environment)
        context_passed, context_reason = self._check_context_gate(conditions)
        layer_results[RecoveryLayer.CONTEXT_GATE] = context_passed
        layer_reasons[RecoveryLayer.CONTEXT_GATE] = context_reason
        
        if not context_passed:
            logger.warning(f"🚫 Context gate failed for {symbol}: {context_reason}")
            return self._create_failed_analysis(layer_results, layer_reasons)
        
        # Layer 2: Downtrend Weakening (Structure)
        trend_result, trend_reason = self._check_downtrend_weakening(symbol, conditions)
        layer_results[RecoveryLayer.DOWNTREND_WEAKENING] = trend_result
        layer_reasons[RecoveryLayer.DOWNTREND_WEAKENING] = trend_reason
        if trend_result:
            confidence_factors['trend_weakening'] = 0.10
        
        # Layer 3: Momentum Shift (Key Signal)
        momentum_result, momentum_reason, momentum_score = self._check_momentum_shift(symbol, conditions)
        layer_results[RecoveryLayer.MOMENTUM_SHIFT] = momentum_result
        layer_reasons[RecoveryLayer.MOMENTUM_SHIFT] = momentum_reason
        confidence_factors.update(momentum_score)
        
        # Layer 4: Accumulation Confirmation (Smart Money)
        accumulation_result, accumulation_reason, accumulation_score = self._check_accumulation(symbol, conditions)
        layer_results[RecoveryLayer.ACCUMULATION_CONFIRMATION] = accumulation_result
        layer_reasons[RecoveryLayer.ACCUMULATION_CONFIRMATION] = accumulation_reason
        confidence_factors.update(accumulation_score)
        
        # Layer 5: Relative Strength Filter (Critical)
        strength_result, strength_reason, strength_score = self._check_relative_strength(symbol, conditions)
        layer_results[RecoveryLayer.RELATIVE_STRENGTH_FILTER] = strength_result
        layer_reasons[RecoveryLayer.RELATIVE_STRENGTH_FILTER] = strength_reason
        if strength_result:
            confidence_factors['relative_strength'] = strength_score
        
        # Calculate final confidence
        confidence_score = self._calculate_confidence_score(confidence_factors)
        
        # Determine position sizing and risk
        position_size = self._calculate_position_size(confidence_score, conditions.volatility)
        risk_level = self._assess_risk_level(confidence_score, conditions.volatility)
        
        return RecoveryAnalysis(
            layer_results=layer_results,
            layer_reasons=layer_reasons,
            confidence_score=confidence_score,
            position_size_recommendation=position_size,
            risk_level=risk_level,
            metadata=confidence_factors
        )
    
    def _check_context_gate(self, conditions: MarketConditions) -> Tuple[bool, str]:
        """Layer 1: Market context validation"""
        try:
            # Get VIX from market context
            from app.config import settings
            market_context = calculate_market_regime_context(
                conditions.symbol or 'SPY', 
                '2026-01-06',  # Would use actual date in production
                settings.database_url
            )
            vix_level = market_context.get('vix_level', 20.0)
            
            # Check volatility limits
            volatility_ok = conditions.volatility < self.max_volatility
            vix_ok = vix_level < 25.0
            
            if volatility_ok and vix_ok:
                reason = f"Context favorable (VIX: {vix_level:.1f}, Vol: {conditions.volatility:.1f}%)"
                logger.info(f"✅ Context gate passed: {reason}")
                return True, reason
            else:
                reason = f"Context unfavorable (VIX: {vix_level:.1f}, Vol: {conditions.volatility:.1f}%)"
                logger.warning(f"❌ Context gate failed: {reason}")
                return False, reason
                
        except Exception as e:
            logger.error(f"Error in context gate: {e}")
            return False, f"Context check error: {e}"
    
    def _check_downtrend_weakening(self, symbol: str, conditions: MarketConditions) -> Tuple[bool, str]:
        """Layer 2: Downtrend structure analysis"""
        try:
            from app.config import settings
            
            # Must still be in downtrend (price below SMA50)
            if not conditions.sma_50 or conditions.current_price >= conditions.sma_50:
                reason = f"Not in downtrend (Price: ${conditions.current_price:.2f} >= SMA50: ${conditions.sma_50:.2f})"
                logger.info(f"❌ Downtrend check failed: {reason}")
                return False, reason
            
            # Check price stability
            stability = check_price_stability(symbol, '2026-01-06', settings.database_url)
            stability_score = stability.get('stability_score', 0.0)
            
            # Price must be stabilizing
            if stability_score >= 0.67:  # At least 2/3 stability factors
                reason = f"Downtrend weakening (Stability: {stability_score:.2f}, No new lows, Range stable)"
                logger.info(f"✅ Downtrend weakening confirmed: {reason}")
                return True, reason
            else:
                reason = f"Downtrend not weakening (Stability: {stability_score:.2f})"
                logger.warning(f"❌ Downtrend weakening failed: {reason}")
                return False, reason
                
        except Exception as e:
            logger.error(f"Error in downtrend analysis: {e}")
            return False, f"Downtrend analysis error: {e}"
    
    def _check_momentum_shift(self, symbol: str, conditions: MarketConditions) -> Tuple[bool, str, Dict[str, float]]:
        """Layer 3: Momentum shift detection"""
        try:
            from app.config import settings
            
            # Get detailed symbol data
            symbol_data = get_symbol_indicators_data(symbol, '2026-01-06', settings.database_url)
            if not symbol_data:
                return False, "No symbol data available", {}
            
            macd_histogram = symbol_data.get('macd_histogram', 0)
            rsi = symbol_data.get('rsi_14', 50)
            
            momentum_factors = {}
            
            # MACD histogram positive
            macd_positive = macd_histogram > 0
            if macd_positive:
                momentum_factors['macd_positive'] = 0.20
                logger.info(f"✅ MACD positive: {macd_histogram:.4f}")
            else:
                logger.info(f"❌ MACD negative: {macd_histogram:.4f}")
            
            # RSI in recovery range (40-55)
            rsi_range = 40 <= rsi <= 55
            if rsi_range:
                momentum_factors['rsi_range'] = 0.15
                logger.info(f"✅ RSI in recovery range: {rsi:.1f}")
            else:
                logger.info(f"❌ RSI outside recovery range: {rsi:.1f}")
            
            momentum_passed = macd_positive and rsi_range
            reason = f"MACD: {macd_histogram:+.4f}, RSI: {rsi:.1f} ({'Recovery' if momentum_passed else 'Not recovery'})"
            
            return momentum_passed, reason, momentum_factors
            
        except Exception as e:
            logger.error(f"Error in momentum analysis: {e}")
            return False, f"Momentum analysis error: {e}", {}
    
    def _check_accumulation(self, symbol: str, conditions: MarketConditions) -> Tuple[bool, str, Dict[str, float]]:
        """Layer 4: Accumulation confirmation (smart money)"""
        try:
            from app.config import settings
            
            symbol_data = get_symbol_indicators_data(symbol, '2026-01-06', settings.database_url)
            if not symbol_data:
                return False, "No symbol data available", {}
            
            accumulation_factors = {}
            
            # Volume rule: >= 1.8x average
            volume_ratio = symbol_data.get('volume_ratio', 0)
            volume_confirm = volume_ratio >= 1.8
            
            if volume_confirm:
                accumulation_factors['high_volume'] = 0.20
                logger.info(f"✅ High volume accumulation: {volume_ratio:.1f}x")
            else:
                logger.info(f"❌ Insufficient volume: {volume_ratio:.1f}x")
            
            # Price rule: close >= open (bullish candle)
            price_action_bullish = symbol_data.get('price_action_bullish', False)
            
            if price_action_bullish:
                accumulation_factors['bullish_price'] = 0.05  # Small confirmation
                logger.info(f"✅ Bullish price action confirmed")
            else:
                logger.info(f"❌ Bearish price action")
            
            accumulation_passed = volume_confirm and price_action_bullish
            reason = f"Volume: {volume_ratio:.1f}x, Price: {'Bullish' if price_action_bullish else 'Bearish'}"
            
            return accumulation_passed, reason, accumulation_factors
            
        except Exception as e:
            logger.error(f"Error in accumulation analysis: {e}")
            return False, f"Accumulation analysis error: {e}", {}
    
    def _check_relative_strength(self, symbol: str, conditions: MarketConditions) -> Tuple[bool, str, float]:
        """Layer 5: Relative strength vs SPY (CRITICAL)"""
        try:
            from app.config import settings
            
            relative_strength = calculate_relative_strength(symbol, '2026-01-06', settings.database_url)
            
            strength_positive = relative_strength > 0
            
            if strength_positive:
                logger.info(f"✅ Positive relative strength: {relative_strength:+.3f}")
                return True, f"Outperforming SPY by {relative_strength:+.3f}", 0.25
            else:
                logger.info(f"❌ Negative relative strength: {relative_strength:+.3f}")
                return False, f"Underperforming SPY by {relative_strength:+.3f}", 0.0
                
        except Exception as e:
            logger.error(f"Error in relative strength analysis: {e}")
            return False, f"Relative strength error: {e}", 0.0
    
    def _calculate_confidence_score(self, confidence_factors: Dict[str, float]) -> float:
        """Calculate overall confidence score from factors"""
        base_score = sum(confidence_factors.values())
        
        # Apply volatility penalty
        # (Would need actual volatility data for this)
        
        # Ensure score is within bounds
        confidence_score = max(0.0, min(1.0, base_score))
        
        logger.info(f"📊 Confidence calculation: {confidence_factors} → {confidence_score:.2f}")
        return confidence_score
    
    def _calculate_position_size(self, confidence_score: float, volatility: float) -> float:
        """Calculate recommended position size (30-50% for recovery)"""
        base_size = 0.30  # 30% base for recovery trades
        
        # Scale up with confidence
        confidence_multiplier = 0.20 * confidence_score  # Up to 20% additional
        
        # Reduce for high volatility
        volatility_penalty = max(0, (volatility - 4.0) * 0.05)  # 5% reduction per 1% vol above 4%
        
        position_size = base_size + confidence_multiplier - volatility_penalty
        return max(0.20, min(0.50, position_size))  # Clamp between 20-50%
    
    def _assess_risk_level(self, confidence_score: float, volatility: float) -> str:
        """Assess risk level based on confidence and volatility"""
        if confidence_score >= 0.65 and volatility < 4.0:
            return "LOW"
        elif confidence_score >= 0.55 and volatility < 6.0:
            return "MODERATE"
        else:
            return "HIGH"
    
    def _create_failed_analysis(self, layer_results: Dict[RecoveryLayer, bool], 
                               layer_reasons: Dict[RecoveryLayer, str]) -> RecoveryAnalysis:
        """Create analysis result for failed context gate"""
        return RecoveryAnalysis(
            layer_results=layer_results,
            layer_reasons=layer_reasons,
            confidence_score=0.0,
            position_size_recommendation=0.0,
            risk_level="HIGH",
            metadata={}
        )
    
    def _log_analysis_decision(self, symbol: str, analysis: RecoveryAnalysis) -> None:
        """Log detailed analysis decision for transparency"""
        logger.info(f"🔄 RECOVERY ANALYSIS SUMMARY for {symbol}:")
        logger.info(f"   Overall Confidence: {analysis.confidence_score:.2f}")
        logger.info(f"   Position Size: {analysis.position_size_recommendation:.1%}")
        logger.info(f"   Risk Level: {analysis.risk_level}")
        
        logger.info(f"📋 LAYER RESULTS:")
        for layer, passed in analysis.layer_results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            reason = analysis.layer_reasons.get(layer, "No reason")
            logger.info(f"   {layer.value.upper()}: {status} - {reason}")
        
        logger.info(f"🎯 METADATA FACTORS:")
        for factor, value in analysis.metadata.items():
            logger.info(f"   {factor}: {value}")
        
        # Final decision logic
        if analysis.confidence_score >= 0.55:
            logger.info(f"🟢 FINAL DECISION: RECOVERY BUY - Confidence meets threshold")
        else:
            logger.info(f"⚪ FINAL DECISION: HOLD - Confidence below threshold")


# Factory function for dependency injection
def create_recovery_engine(max_volatility: float = 8.0) -> RecoveryDetectionEngine:
    """Factory function to create recovery detection engine"""
    return RecoveryDetectionEngine(max_volatility=max_volatility)
