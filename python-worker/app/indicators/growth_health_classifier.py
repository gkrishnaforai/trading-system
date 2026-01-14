"""
Growth Health Classifier
Institutional-grade classification system that separates structural risk from growth phase
Provides clear investment guidance based on business fundamentals
"""

from typing import Dict, Any, List, Tuple
from enum import Enum
from dataclasses import dataclass
import logging

from app.observability.logging import get_logger

logger = get_logger("growth_health_classifier")


class StructuralRisk(Enum):
    """Structural risk level - balance sheet health and fraud signals"""
    LOW = "LOW"          # 🟢 - Balance sheet strong, no red flags
    MEDIUM = "MEDIUM"    # 🟡 - Some concerns but not critical
    HIGH = "HIGH"        # 🔴 - Structural issues or red flags


class GrowthPhase(Enum):
    """Growth phase - where the company is in its lifecycle"""
    HEALTHY_COMPOUNDER = "HEALTHY_COMPOUNDER"           # 🟢 - Accelerating growth
    MATURE_COMPOUNDER = "MATURE_COMPOUNDER"           # 🟡 - Late cycle, still growing
    GROWTH_DEGRADATION = "GROWTH_DEGRADATION"         # 🟠 - Growth slowing materially
    GROWTH_BREAKDOWN = "GROWTH_BREAKDOWN"              # 🔴 - Structural breakdown


class InvestmentPosture(Enum):
    """Clear investment guidance"""
    BUY = "BUY"                              # 🟢 - Aggressive accumulation
    HOLD_SELECTIVE_ADD = "HOLD_SELECTIVE_ADD"  # 🟡 - Hold, add on fear
    TRIM_REDUCE = "TRIM_REDUCE"               # 🟠 - Reduce position
    EXIT_AVOID = "EXIT_AVOID"                 # 🔴 - Sell or avoid


@dataclass
class GrowthHealthState:
    """Comprehensive growth health assessment"""
    symbol: str
    structural_risk: StructuralRisk
    growth_phase: GrowthPhase
    investment_posture: InvestmentPosture
    confidence: float
    reasoning: List[str]
    risk_factors: List[str]
    opportunities: List[str]
    forward_return_expectation: str


class GrowthHealthClassifier:
    """
    Institutional-grade growth health classifier
    
    Separates structural risk (balance sheet health) from growth phase (business lifecycle)
    Provides clear investment guidance that matches institutional research
    """
    
    def __init__(self):
        self.logger = logger
    
    def classify_growth_health(self, analysis_data: Dict[str, Any], risk_metrics: Dict[str, Any]) -> GrowthHealthState:
        """
        Classify growth health based on comprehensive analysis
        
        Args:
            analysis_data: Early warning analysis results
            risk_metrics: Detailed risk metrics
            
        Returns:
            GrowthHealthState with institutional-grade assessment
        """
        symbol = analysis_data.get('symbol', 'UNKNOWN')
        
        # Step 1: Assess Structural Risk
        structural_risk = self._assess_structural_risk(analysis_data, risk_metrics)
        
        # Step 2: Determine Growth Phase
        growth_phase = self._determine_growth_phase(analysis_data, risk_metrics)
        
        # Step 3: Determine Investment Posture
        investment_posture = self._determine_investment_posture(structural_risk, growth_phase)
        
        # Step 4: Generate reasoning and insights
        reasoning, risk_factors, opportunities = self._generate_insights(
            structural_risk, growth_phase, analysis_data, risk_metrics
        )
        
        # Step 5: Set forward return expectations
        forward_return_expectation = self._set_forward_return_expectations(
            structural_risk, growth_phase
        )
        
        # Step 6: Calculate confidence
        confidence = self._calculate_confidence(analysis_data, risk_metrics)
        
        return GrowthHealthState(
            symbol=symbol,
            structural_risk=structural_risk,
            growth_phase=growth_phase,
            investment_posture=investment_posture,
            confidence=confidence,
            reasoning=reasoning,
            risk_factors=risk_factors,
            opportunities=opportunities,
            forward_return_expectation=forward_return_expectation
        )
    
    def _assess_structural_risk(self, analysis_data: Dict[str, Any], risk_metrics: Dict[str, Any]) -> StructuralRisk:
        """
        Assess structural risk - balance sheet health, revenue quality, management signals
        
        This is about survival and fraud detection, NOT growth rate
        """
        domain_risks = analysis_data.get('domain_risks', {})
        detailed_risks = risk_metrics.get('domain_risks', {})
        
        # Check for structural red flags
        structural_flags = []
        
        # Revenue Quality - Structural Issues
        revenue_risk = domain_risks.get('revenue_risk', 'NO_RISK')
        if revenue_risk == 'STRUCTURAL_BREAKDOWN':
            structural_flags.append("Revenue quality breakdown - potential accounting issues")
        elif revenue_risk == 'EARLY_STRESS':
            # Check if it's structural or cyclical
            revenue_flags = detailed_risks.get('revenue_quality', {}).get('flags', {})
            if revenue_flags.get('receivables_vs_revenue_divergence', False):
                structural_flags.append("Receivables growing faster than revenue - quality concern")
        
        # Management Signals - Structural Red Flags
        management_risk = domain_risks.get('management_risk', 'NO_RISK')
        if management_risk == 'STRUCTURAL_BREAKDOWN':
            structural_flags.append("Management signal breakdown - potential governance issues")
        elif management_risk == 'EARLY_STRESS':
            mgmt_flags = detailed_risks.get('management_signals', {}).get('flags', {})
            if mgmt_flags.get('buybacks_rising_debt', False):
                structural_flags.append("Aggressive buybacks funded by debt")
        
        # Capital Efficiency - Structural Issues
        capital_risk = domain_risks.get('capital_risk', 'NO_RISK')
        if capital_risk == 'STRUCTURAL_BREAKDOWN':
            structural_flags.append("Capital efficiency collapse - business model broken")
        
        # Determine structural risk level
        if len(structural_flags) >= 2 or any('breakdown' in flag.lower() or 'potential' in flag.lower() for flag in structural_flags):
            return StructuralRisk.HIGH
        elif len(structural_flags) == 1:
            return StructuralRisk.MEDIUM
        else:
            return StructuralRisk.LOW
    
    def _determine_growth_phase(self, analysis_data: Dict[str, Any], risk_metrics: Dict[str, Any]) -> GrowthPhase:
        """
        Determine growth phase - where the company is in its business lifecycle
        
        This is about growth trajectory, NOT structural health
        """
        domain_risks = analysis_data.get('domain_risks', {})
        detailed_risks = risk_metrics.get('domain_risks', {})
        metrics = analysis_data.get('metrics', {})
        
        # Growth acceleration indicators
        revenue_risk = domain_risks.get('revenue_risk', 'NO_RISK')
        margin_risk = domain_risks.get('margin_risk', 'NO_RISK')
        capital_risk = domain_risks.get('capital_risk', 'NO_RISK')
        
        # Check for healthy compounder (accelerating growth)
        healthy_indicators = []
        if revenue_risk == 'NO_RISK':
            healthy_indicators.append("Revenue quality clean")
        
        if margin_risk == 'NO_RISK':
            healthy_indicators.append("Margins stable or expanding")
        
        if capital_risk == 'NO_RISK':
            healthy_indicators.append("Capital efficiency intact")
        
        # Check ROIC trend
        roic_trend = metrics.get('roic_trend', 'stable')
        if roic_trend == 'stable' or roic_trend == 'rising':
            healthy_indicators.append("ROIC stable or rising")
        
        # Determine growth phase
        if len(healthy_indicators) >= 3:
            return GrowthPhase.HEALTHY_COMPOUNDER
        
        # Check for growth breakdown
        breakdown_indicators = []
        if revenue_risk == 'STRUCTURAL_BREAKDOWN':
            breakdown_indicators.append("Revenue quality issues")
        
        if margin_risk == 'STRUCTURAL_BREAKDOWN':
            breakdown_indicators.append("Margin collapse")
        
        if capital_risk == 'STRUCTURAL_BREAKDOWN':
            breakdown_indicators.append("Capital efficiency collapse")
        
        # Check management signals for breakdown
        management_risk = domain_risks.get('management_risk', 'NO_RISK')
        if management_risk == 'STRUCTURAL_BREAKDOWN':
            breakdown_indicators.append("Management signal red flags")
        
        if len(breakdown_indicators) >= 2:
            return GrowthPhase.GROWTH_BREAKDOWN
        
        # Check for growth degradation
        degradation_indicators = []
        if margin_risk == 'EARLY_STRESS':
            degradation_indicators.append("Margin compression")
        
        if capital_risk == 'EARLY_STRESS':
            degradation_indicators.append("Capital inefficiency")
        
        # Check incremental ROIC
        capital_flags = detailed_risks.get('capital_efficiency', {}).get('flags', {})
        if capital_flags.get('incremental_roic_collapse', False):
            degradation_indicators.append("Incremental ROIC falling")
        
        if len(degradation_indicators) >= 2:
            return GrowthPhase.GROWTH_DEGRADATION
        
        # Default to mature compounder (late cycle)
        return GrowthPhase.MATURE_COMPOUNDER
    
    def _determine_investment_posture(self, structural_risk: StructuralRisk, growth_phase: GrowthPhase) -> InvestmentPosture:
        """
        Determine investment posture based on structural risk and growth phase
        
        This is the decision matrix that tells users what to do
        """
        # 🟢 BUY - Only for healthy compounders with low structural risk
        if (structural_risk == StructuralRisk.LOW and 
            growth_phase == GrowthPhase.HEALTHY_COMPOUNDER):
            return InvestmentPosture.BUY
        
        # 🔴 EXIT/AVOID - Any structural breakdown or growth breakdown
        if (structural_risk == StructuralRisk.HIGH or 
            growth_phase == GrowthPhase.GROWTH_BREAKDOWN):
            return InvestmentPosture.EXIT_AVOID
        
        # 🟠 TRIM/REDUCE - Growth degradation or medium structural risk
        if (structural_risk == StructuralRisk.MEDIUM or 
            growth_phase == GrowthPhase.GROWTH_DEGRADATION):
            return InvestmentPosture.TRIM_REDUCE
        
        # 🟡 HOLD/SELECTIVE ADD - Mature compounders with low structural risk
        if (structural_risk == StructuralRisk.LOW and 
            growth_phase == GrowthPhase.MATURE_COMPOUNDER):
            return InvestmentPosture.HOLD_SELECTIVE_ADD
        
        # Default to hold
        return InvestmentPosture.HOLD_SELECTIVE_ADD
    
    def _generate_insights(self, structural_risk: StructuralRisk, growth_phase: GrowthPhase,
                          analysis_data: Dict[str, Any], risk_metrics: Dict[str, Any]) -> Tuple[List[str], List[str], List[str]]:
        """Generate reasoning, risk factors, and opportunities"""
        
        reasoning = []
        risk_factors = []
        opportunities = []
        
        # Structural risk reasoning
        if structural_risk == StructuralRisk.LOW:
            reasoning.append("Balance sheet and revenue quality remain strong")
            opportunities.append("Strong financial foundation provides downside protection")
        elif structural_risk == StructuralRisk.MEDIUM:
            reasoning.append("Some structural concerns but no critical issues")
            risk_factors.append("Monitor balance sheet metrics closely")
        else:
            reasoning.append("Structural issues require immediate attention")
            risk_factors.append("Capital preservation priority over growth")
        
        # Growth phase reasoning
        if growth_phase == GrowthPhase.HEALTHY_COMPOUNDER:
            reasoning.append("Business in acceleration phase with expanding margins")
            opportunities.append("Multiple expansion potential as growth accelerates")
        elif growth_phase == GrowthPhase.MATURE_COMPOUNDER:
            reasoning.append("Growth continues but efficiency and margins are no longer expanding")
            risk_factors.append("Forward returns may compress as growth matures")
            opportunities.append("Stable compounder suitable for long-term holding")
        elif growth_phase == GrowthPhase.GROWTH_DEGRADATION:
            reasoning.append("Growth trajectory showing material slowdown")
            risk_factors.append("Margin pressure and capital inefficiency impacting returns")
        else:
            reasoning.append("Growth breakdown indicates structural business issues")
            risk_factors.append("Business model may be fundamentally broken")
        
        return reasoning, risk_factors, opportunities
    
    def _set_forward_return_expectations(self, structural_risk: StructuralRisk, growth_phase: GrowthPhase) -> str:
        """Set forward return expectations based on risk and growth profile"""
        
        if growth_phase == GrowthPhase.HEALTHY_COMPOUNDER:
            return "15-25% annualized (accelerating growth + multiple expansion)"
        elif growth_phase == GrowthPhase.MATURE_COMPOUNDER:
            if structural_risk == StructuralRisk.LOW:
                return "8-12% annualized (stable compounding at reasonable valuation)"
            else:
                return "5-8% annualized (mature growth with some risk factors)"
        elif growth_phase == GrowthPhase.GROWTH_DEGRADATION:
            return "0-5% annualized (slowing growth compresses returns)"
        else:
            return "Negative returns likely (structural breakdown)"
    
    def _calculate_confidence(self, analysis_data: Dict[str, Any], risk_metrics: Dict[str, Any]) -> float:
        """Calculate confidence in the assessment"""
        
        # Base confidence on data completeness
        confidence = 0.7  # Base confidence
        
        # Boost confidence if we have comprehensive data
        if analysis_data.get('domain_risks') and risk_metrics.get('domain_risks'):
            confidence += 0.1
        
        # Boost confidence if metrics are consistent
        metrics = analysis_data.get('metrics', {})
        if metrics:
            confidence += 0.1
        
        # Cap at 0.95 (never 100% confidence)
        return min(confidence, 0.95)


# Singleton instance for easy import
growth_health_classifier = GrowthHealthClassifier()
