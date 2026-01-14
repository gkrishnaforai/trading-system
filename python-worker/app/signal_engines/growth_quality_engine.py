"""
Growth Quality Signal Engine

Integrates Early Warning Flags with technical analysis to provide
comprehensive investment signals that account for both technical
momentum and fundamental growth quality.

This engine answers: "Should I buy/hold/sell this stock considering
both technical signals AND growth quality?"

Integration Logic:
- GREEN growth risk: Allow normal technical signals
- YELLOW growth risk: Reduce position sizes, tighten stops
- RED growth risk: Override BUY signals, force SELL/REDUCE
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum

from app.indicators.early_warning_flags import (
    EarlyWarningEngine, RiskState, DomainRisk, EarlyWarningResult
)
from app.indicators.indicator_states import (
    IndicatorStates, TradeAction, SignalDecisionEngine, SignalTextGenerator
)
from app.signal_engines.signal_calculator_core import SignalType

from app.observability.logging import get_logger

logger = get_logger("growth_quality_engine")


@dataclass
class GrowthQualitySignal:
    """Combined signal incorporating technical and growth quality analysis"""
    symbol: str
    signal_type: SignalType
    confidence: float
    technical_action: TradeAction
    growth_risk: RiskState
    
    # Domain risks
    revenue_risk: DomainRisk
    margin_risk: DomainRisk
    capital_risk: DomainRisk
    management_risk: DomainRisk
    
    # Reasoning
    technical_reasoning: List[str]
    growth_reasoning: List[str]
    integrated_reasoning: List[str]
    
    # Action guidance
    position_sizing_adjustment: float  # 0.0 to 2.0 (1.0 = normal)
    risk_management_notes: List[str]
    
    # Metadata
    analysis_date: date
    price_at_signal: float


class GrowthQualitySignalEngine:
    """
    Growth Quality Signal Engine
    
    Combines technical analysis with growth quality assessment
    to provide institutional-grade investment signals.
    
    Key Features:
    - Growth risk overrides technical signals
    - Position sizing adjustments based on growth quality
    - Comprehensive reasoning for educational value
    - Risk management guidance
    """
    
    def __init__(self):
        self.early_warning_engine = EarlyWarningEngine()
        self.logger = logger
        self.logger.info("🎯 Growth Quality Signal Engine initialized")
    
    def generate_signal(self, symbol: str, technical_states: IndicatorStates, 
                       price: float) -> GrowthQualitySignal:
        """
        Generate integrated signal combining technical and growth quality analysis
        
        Args:
            symbol: Stock symbol
            technical_states: Technical indicator states
            price: Current price
            
        Returns:
            GrowthQualitySignal with comprehensive analysis
        """
        try:
            # Step 1: Get technical signal
            technical_action = SignalDecisionEngine.decide_action(technical_states)
            technical_reasoning = SignalTextGenerator.generate_signal_text(technical_states)
            technical_reasoning.extend(SignalTextGenerator.generate_action_reasoning(technical_action, technical_states))
            
            # Step 2: Get growth quality analysis
            growth_analysis = self.early_warning_engine.analyze_growth_health(symbol)
            
            # Step 3: Integrate signals
            final_signal_type, final_confidence, integrated_reasoning = self._integrate_signals(
                technical_action, growth_analysis, technical_reasoning
            )
            
            # Step 4: Calculate position sizing adjustment
            position_adjustment = self._calculate_position_sizing_adjustment(growth_analysis)
            
            # Step 5: Generate risk management notes
            risk_notes = self._generate_risk_management_notes(growth_analysis, technical_action)
            
            signal = GrowthQualitySignal(
                symbol=symbol,
                signal_type=final_signal_type,
                confidence=final_confidence,
                technical_action=technical_action,
                growth_risk=growth_analysis.overall_risk,
                revenue_risk=growth_analysis.revenue_risk,
                margin_risk=growth_analysis.margin_risk,
                capital_risk=growth_analysis.capital_risk,
                management_risk=growth_analysis.management_risk,
                technical_reasoning=technical_reasoning,
                growth_reasoning=growth_analysis.warnings + growth_analysis.insights,
                integrated_reasoning=integrated_reasoning,
                position_sizing_adjustment=position_adjustment,
                risk_management_notes=risk_notes,
                analysis_date=date.today(),
                price_at_signal=price
            )
            
            self.logger.info(f"🎯 Growth Quality Signal generated for {symbol}: {final_signal_type.value} (growth risk: {growth_analysis.overall_risk.value})")
            return signal
            
        except Exception as e:
            self.logger.error(f"❌ Error generating growth quality signal for {symbol}: {str(e)}")
            # Fallback to technical-only signal
            return self._create_fallback_signal(symbol, technical_states, price, str(e))
    
    def _integrate_signals(self, technical_action: TradeAction, 
                          growth_analysis: EarlyWarningResult,
                          technical_reasoning: List[str]) -> Tuple[SignalType, float, List[str]]:
        """
        Integrate technical signals with growth quality assessment
        
        Integration Rules:
        - GREEN growth risk: Normal technical signals
        - YELLOW growth risk: Reduce confidence, tighten stops
        - RED growth risk: Override BUY signals, force SELL/REDUCE
        """
        
        integrated_reasoning = []
        growth_risk = growth_analysis.overall_risk
        
        # Start with technical reasoning
        integrated_reasoning.extend(technical_reasoning)
        
        # Add growth quality context
        integrated_reasoning.insert(0, f"🎯 Growth Quality Analysis (Risk: {growth_risk.value})")
        integrated_reasoning.insert(1, f"📊 Domain Risks: Revenue {growth_analysis.revenue_risk.value} | Margins {growth_analysis.margin_risk.value} | Capital {growth_analysis.capital_risk.value} | Management {growth_analysis.management_risk.value}")
        
        # Apply integration logic
        if growth_risk == RiskState.RED:
            # RED growth risk overrides technical BUY signals
            if technical_action in {TradeAction.BUY, TradeAction.ADD}:
                final_signal_type = SignalType.SELL
                final_confidence = 0.7  # High confidence in risk management
                
                integrated_reasoning.insert(2, "🔴 GROWTH BREAKDOWN DETECTED - Overriding technical BUY signals")
                integrated_reasoning.insert(3, "⚠️ Institutional distribution risk - exit positions")
                integrated_reasoning.insert(4, "📉 Growth quality deterioration precedes price decline")
                
            else:
                # Technical SELL/HOLD signals reinforced
                final_signal_type = self._trade_action_to_signal_type(technical_action)
                final_confidence = min(0.9, 0.6 + 0.3)  # Boost confidence for risk-off signals
                
                integrated_reasoning.insert(2, "🔴 GROWTH BREAKDOWN CONFIRMS technical risk signals")
                integrated_reasoning.insert(3, "⚠️ Structural issues support defensive positioning")
                
        elif growth_risk == RiskState.YELLOW:
            # YELLOW growth risk reduces confidence and position size
            if technical_action in {TradeAction.BUY, TradeAction.ADD}:
                final_signal_type = SignalType.HOLD  # Downgrade to HOLD
                final_confidence = 0.5  # Reduced confidence
                
                integrated_reasoning.insert(2, "🟡 GROWTH STRESS DETECTED - Downgrading BUY to HOLD")
                integrated_reasoning.insert(3, "⚠️ Early deterioration - wait for clarity")
                integrated_reasoning.insert(4, "📊 Reduce position sizes, tighten risk management")
                
            elif technical_action == TradeAction.HOLD:
                final_signal_type = SignalType.REDUCE  # Upgrade to REDUCE
                final_confidence = 0.6
                
                integrated_reasoning.insert(2, "🟡 GROWTH STRESS + Technical HOLD = REDUCE exposure")
                integrated_reasoning.insert(3, "⚠️ Risk management - trim positions")
                
            else:  # SELL/REDUCE
                final_signal_type = self._trade_action_to_signal_type(technical_action)
                final_confidence = 0.8  # Boost confidence for risk-off
                
                integrated_reasoning.insert(2, "🟡 GROWTH STRESS CONFIRMS technical SELL signals")
                integrated_reasoning.insert(3, "⚠️ Multiple risks support defensive action")
                
        else:  # GREEN growth risk
            # Normal technical signals with slight confidence boost
            final_signal_type = self._trade_action_to_signal_type(technical_action)
            final_confidence = min(0.9, 0.6 + 0.1)  # Slight confidence boost
            
            integrated_reasoning.insert(2, "🟢 GROWTH QUALITY INTACT - Technical signals valid")
            integrated_reasoning.insert(3, "✅ Fundamental health supports technical analysis")
        
        # Add growth-specific insights
        if growth_analysis.warnings:
            integrated_reasoning.append("🚨 Growth Quality Warnings:")
            integrated_reasoning.extend([f"  • {warning}" for warning in growth_analysis.warnings[:3]])  # Top 3 warnings
        
        if growth_analysis.insights:
            integrated_reasoning.append("💡 Growth Quality Insights:")
            integrated_reasoning.extend([f"  • {insight}" for insight in growth_analysis.insights[:2]])  # Top 2 insights
        
        return final_signal_type, final_confidence, integrated_reasoning
    
    def _calculate_position_sizing_adjustment(self, growth_analysis: EarlyWarningResult) -> float:
        """
        Calculate position sizing adjustment based on growth quality
        
        Adjustment Rules:
        - GREEN: 1.0x (normal sizing)
        - YELLOW: 0.5x (half size)
        - RED: 0.2x (minimal size)
        """
        if growth_analysis.overall_risk == RiskState.GREEN:
            return 1.0
        elif growth_analysis.overall_risk == RiskState.YELLOW:
            return 0.5
        else:  # RED
            return 0.2
    
    def _generate_risk_management_notes(self, growth_analysis: EarlyWarningResult, 
                                      technical_action: TradeAction) -> List[str]:
        """Generate specific risk management notes"""
        notes = []
        
        if growth_analysis.overall_risk == RiskState.RED:
            notes.extend([
                "🔴 IMMEDIATE ACTION REQUIRED",
                "Consider exiting all positions on strength",
                "Avoid new allocations until growth quality improves",
                "Monitor for institutional distribution patterns"
            ])
        elif growth_analysis.overall_risk == RiskState.YELLOW:
            notes.extend([
                "🟡 ENHANCED RISK MANAGEMENT",
                "Reduce position sizes by 50%",
                "Tighten stop-losses to recent lows",
                "Monitor next earnings report closely"
            ])
        else:  # GREEN
            notes.extend([
                "🟢 NORMAL RISK MANAGEMENT",
                "Standard position sizing appropriate",
                "Normal stop-loss levels",
                "Growth quality supports technical signals"
            ])
        
        # Domain-specific notes
        if growth_analysis.revenue_risk == DomainRisk.STRUCTURAL_BREAKDOWN:
            notes.append("📊 Revenue quality breakdown - watch for earnings miss")
        
        if growth_analysis.margin_risk == DomainRisk.STRUCTURAL_BREAKDOWN:
            notes.append("💸 Margin stress - potential guidance cut")
        
        if growth_analysis.capital_risk == DomainRisk.STRUCTURAL_BREAKDOWN:
            notes.append("🏭 Capital efficiency decay - ROIC declining")
        
        if growth_analysis.management_risk == DomainRisk.STRUCTURAL_BREAKDOWN:
            notes.append("👥 Management credibility risk - watch guidance changes")
        
        return notes
    
    def _trade_action_to_signal_type(self, action: TradeAction) -> SignalType:
        """Convert TradeAction to SignalType"""
        mapping = {
            TradeAction.BUY: SignalType.BUY,
            TradeAction.ADD: SignalType.ADD,
            TradeAction.HOLD: SignalType.HOLD,
            TradeAction.SELL: SignalType.SELL,
            TradeAction.REDUCE: SignalType.REDUCE
        }
        return mapping.get(action, SignalType.HOLD)
    
    def _create_fallback_signal(self, symbol: str, technical_states: IndicatorStates,
                               price: float, error_message: str) -> GrowthQualitySignal:
        """Create fallback signal when growth analysis fails"""
        technical_action = SignalDecisionEngine.decide_action(technical_states)
        technical_reasoning = SignalTextGenerator.generate_signal_text(technical_states)
        
        return GrowthQualitySignal(
            symbol=symbol,
            signal_type=self._trade_action_to_signal_type(technical_action),
            confidence=0.3,  # Low confidence due to missing growth data
            technical_action=technical_action,
            growth_risk=RiskState.YELLOW,  # Conservative assumption
            revenue_risk=DomainRisk.NO_RISK,
            margin_risk=DomainRisk.NO_RISK,
            capital_risk=DomainRisk.NO_RISK,
            management_risk=DomainRisk.NO_RISK,
            technical_reasoning=technical_reasoning,
            growth_reasoning=[f"⚠️ Growth analysis unavailable: {error_message}"],
            integrated_reasoning=[
                "🎯 Technical-Only Signal (Growth Analysis Unavailable)",
                "⚠️ Using technical signals only - reduced confidence",
                f"Error: {error_message}"
            ],
            position_sizing_adjustment=0.5,  # Conservative sizing
            risk_management_notes=[
                "⚠️ Limited analysis due to missing fundamentals data",
                "Consider reducing position size until growth analysis available",
                "Monitor for fundamentals data updates"
            ],
            analysis_date=date.today(),
            price_at_signal=price
        )


# Global instance
growth_quality_engine = GrowthQualitySignalEngine()
