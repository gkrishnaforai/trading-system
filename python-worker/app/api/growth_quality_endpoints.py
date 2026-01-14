"""
Growth Quality Analysis API Endpoints

RESTful API endpoints for Early Warning Flags and Growth Quality Signal analysis.
Provides institutional-grade growth quality assessment for portfolio management.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import date, datetime
import logging

from app.indicators.early_warning_flags import EarlyWarningEngine
from app.indicators.growth_health_classifier import growth_health_classifier, GrowthHealthState
from app.signal_engines.growth_quality_engine import GrowthQualitySignalEngine, GrowthQualitySignal
# Auth temporarily removed for testing
# from app.utils.auth import get_current_user
from app.observability.logging import get_logger

logger = get_logger("growth_quality_api")

# ========================================
# IMPORTANT: Router Configuration Rules
# ========================================
# DO NOT ADD PREFIX HERE! Prefixes are managed in api_server.py
# ❌ WRONG: router = APIRouter(prefix="/api/v1/growth-quality", tags=["growth-quality"])
# ✅ CORRECT: router = APIRouter(tags=["growth-quality"])
# ========================================
router = APIRouter(tags=["growth-quality"])

# Initialize engines
early_warning_engine = EarlyWarningEngine()
growth_quality_engine = GrowthQualitySignalEngine()


# Pydantic models for API responses
class DomainRiskResponse(BaseModel):
    """Domain risk response model"""
    revenue_risk: str
    margin_risk: str
    capital_risk: str
    management_risk: str


class EarlyWarningResponse(BaseModel):
    """Early warning analysis response model"""
    symbol: str
    analysis_date: date
    overall_risk: str
    domain_risks: DomainRiskResponse
    warnings: List[str]
    insights: List[str]
    metrics: Dict[str, Any]


class GrowthQualitySignalResponse(BaseModel):
    """Growth quality signal response model"""
    symbol: str
    signal_type: str
    confidence: float
    technical_action: str
    growth_risk: str
    domain_risks: DomainRiskResponse
    position_sizing_adjustment: float
    technical_reasoning: List[str]
    growth_reasoning: List[str]
    integrated_reasoning: List[str]
    risk_management_notes: List[str]
    analysis_date: date
    price_at_signal: float


class GrowthHealthStateResponse(BaseModel):
    """Institutional-grade growth health assessment"""
    symbol: str
    structural_risk: str  # LOW, MEDIUM, HIGH
    growth_phase: str  # HEALTHY_COMPOUNDER, MATURE_COMPOUNDER, GROWTH_DEGRADATION, GROWTH_BREAKDOWN
    investment_posture: str  # BUY, HOLD_SELECTIVE_ADD, TRIM_REDUCE, EXIT_AVOID
    confidence: float
    reasoning: List[str]
    risk_factors: List[str]
    opportunities: List[str]
    forward_return_expectation: str
    analysis_date: str


class PortfolioGrowthAnalysisRequest(BaseModel):
    """Request for portfolio-wide growth analysis"""
    symbols: List[str] = Field(..., description="List of symbols to analyze")
    include_technical: bool = Field(True, description="Include technical analysis integration")


class PortfolioGrowthAnalysisResponse(BaseModel):
    """Portfolio-wide growth analysis response"""
    analysis_date: date
    total_symbols: int
    successful_analyses: int
    risk_distribution: Dict[str, int]  # GREEN, YELLOW, RED counts
    signals: List[GrowthQualitySignalResponse]
    portfolio_risk_assessment: str
    recommendations: List[str]


@router.get("/early-warning/{symbol}", response_model=EarlyWarningResponse)
async def get_early_warning_analysis(
    symbol: str
    # current_user: Dict = Depends(get_current_user)  # Temporarily removed for testing
):
    """
    Get Early Warning Flags analysis for a single symbol
    
    Analyzes 4 domains of growth quality:
    - Revenue Quality Deterioration
    - Margin & Cost Structure Stress
    - Capital Efficiency & Return Decay
    - Management Signals & Behavioral Shifts
    """
    try:
        logger.info(f"🚨 Early warning analysis requested for {symbol}")
        
        # Run early warning analysis
        result = early_warning_engine.analyze_growth_health(symbol.upper())
        
        # Convert to response model
        response = EarlyWarningResponse(
            symbol=result.symbol,
            analysis_date=result.analysis_date,
            overall_risk=result.overall_risk.value,
            domain_risks=DomainRiskResponse(
                revenue_risk=result.domain_risks['revenue_quality'].value,
                margin_risk=result.domain_risks['margin_stress'].value,
                capital_risk=result.domain_risks['capital_efficiency'].value,
                management_risk=result.domain_risks['management_signals'].value
            ),
            warnings=result.warnings,
            insights=result.insights,
            metrics=result.metrics
        )
        
        logger.info(f"✅ Early warning analysis completed for {symbol}: {result.overall_risk.value}")
        return response
        
    except ValueError as e:
        logger.error(f"❌ No fundamentals data for {symbol}: {str(e)}")
        raise HTTPException(status_code=404, detail=f"No fundamentals data available for {symbol}")
    
    except Exception as e:
        logger.error(f"❌ Error in early warning analysis for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/signal/{symbol}", response_model=GrowthQualitySignalResponse)
async def get_growth_quality_signal(
    symbol: str,
    price: Optional[float] = None
    # current_user: Dict = Depends(get_current_user)  # Temporarily removed for testing
):
    """
    Get integrated Growth Quality Signal
    
    Combines technical analysis with growth quality assessment
    to provide institutional-grade investment signals.
    
    Integration Logic:
    - GREEN growth risk: Normal technical signals
    - YELLOW growth risk: Reduced position sizes
    - RED growth risk: Override BUY signals, force SELL/REDUCE
    """
    try:
        logger.info(f"🎯 Growth quality signal requested for {symbol}")
        
        # Get current price if not provided
        if price is None:
            # TODO: Get current price from market data
            price = 100.0  # Placeholder
            logger.warning(f"⚠️ Using placeholder price ${price} for {symbol}")
        
        # TODO: Get technical states from technical analysis
        # For now, create placeholder states
        from app.indicators.indicator_states import (
            IndicatorStates, TrendState, MACDState, RSIState, 
            VolatilityState, LiquidityState, FearGreedState
        )
        
        technical_states = IndicatorStates(
            trend=TrendState.BULL,
            macd=MACDState.BULLISH,
            rsi=RSIState.NEUTRAL,
            volatility=VolatilityState.NORMAL,
            liquidity=LiquidityState.STRONG,
            fear_greed=FearGreedState.NEUTRAL,
            volume_ratio=1.2,
            price=price
        )
        
        # Generate growth quality signal
        signal = growth_quality_engine.generate_signal(symbol.upper(), technical_states, price)
        
        # Convert to response model
        response = GrowthQualitySignalResponse(
            symbol=signal.symbol,
            signal_type=signal.signal_type.value,
            confidence=signal.confidence,
            technical_action=signal.technical_action.value,
            growth_risk=signal.growth_risk.value,
            domain_risks=DomainRiskResponse(
                revenue_risk=signal.revenue_risk.value,
                margin_risk=signal.margin_risk.value,
                capital_risk=signal.capital_risk.value,
                management_risk=signal.management_risk.value
            ),
            position_sizing_adjustment=signal.position_sizing_adjustment,
            technical_reasoning=signal.technical_reasoning,
            growth_reasoning=signal.growth_reasoning,
            integrated_reasoning=signal.integrated_reasoning,
            risk_management_notes=signal.risk_management_notes,
            analysis_date=signal.analysis_date,
            price_at_signal=signal.price_at_signal
        )
        
        logger.info(f"✅ Growth quality signal generated for {symbol}: {signal.signal_type.value}")
        return response
        
    except ValueError as e:
        logger.error(f"❌ No data available for {symbol}: {str(e)}")
        raise HTTPException(status_code=404, detail=f"No data available for {symbol}")
    
    except Exception as e:
        logger.error(f"❌ Error generating growth quality signal for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Signal generation failed: {str(e)}")


@router.post("/portfolio-analysis", response_model=PortfolioGrowthAnalysisResponse)
async def analyze_portfolio_growth_quality(
    request: PortfolioGrowthAnalysisRequest
    # current_user: Dict = Depends(get_current_user)  # Temporarily removed for testing
):
    """
    Analyze growth quality for entire portfolio
    
    Provides portfolio-wide assessment of growth quality risks
    and recommendations for portfolio management.
    """
    try:
        logger.info(f"📊 Portfolio growth analysis requested for {len(request.symbols)} symbols")
        
        symbols = [s.upper() for s in request.symbols]
        signals = []
        risk_distribution = {"GREEN": 0, "YELLOW": 0, "RED": 0}
        
        successful_analyses = 0
        
        for symbol in symbols:
            try:
                # Get early warning analysis
                early_warning_result = early_warning_engine.analyze_growth_health(symbol)
                risk_distribution[early_warning_result.overall_risk.value] += 1
                successful_analyses += 1
                
                if request.include_technical:
                    # TODO: Get technical states and generate integrated signal
                    # For now, create placeholder signal
                    signal_response = GrowthQualitySignalResponse(
                        symbol=symbol,
                        signal_type="HOLD",
                        confidence=0.5,
                        technical_action="HOLD",
                        growth_risk=early_warning_result.overall_risk.value,
                        domain_risks=DomainRiskResponse(
                            revenue_risk=early_warning_result.domain_risks['revenue_quality'].value,
                            margin_risk=early_warning_result.domain_risks['margin_stress'].value,
                            capital_risk=early_warning_result.domain_risks['capital_efficiency'].value,
                            management_risk=early_warning_result.domain_risks['management_signals'].value
                        ),
                        position_sizing_adjustment=1.0,
                        technical_reasoning=["Technical analysis not included in this request"],
                        growth_reasoning=early_warning_result.warnings + early_warning_result.insights,
                        integrated_reasoning=["Portfolio analysis mode"],
                        risk_management_notes=["See individual analysis for details"],
                        analysis_date=date.today(),
                        price_at_signal=0.0
                    )
                    signals.append(signal_response)
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to analyze {symbol}: {str(e)}")
                continue
        
        # Generate portfolio-level assessment
        portfolio_risk = _calculate_portfolio_risk(risk_distribution)
        recommendations = _generate_portfolio_recommendations(risk_distribution, signals)
        
        response = PortfolioGrowthAnalysisResponse(
            analysis_date=date.today(),
            total_symbols=len(symbols),
            successful_analyses=successful_analyses,
            risk_distribution=risk_distribution,
            signals=signals,
            portfolio_risk_assessment=portfolio_risk,
            recommendations=recommendations
        )
        
        logger.info(f"✅ Portfolio growth analysis completed: {portfolio_risk}")
        return response
        
    except Exception as e:
        logger.error(f"❌ Error in portfolio growth analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Portfolio analysis failed: {str(e)}")


@router.get("/risk-metrics/{symbol}")
async def get_growth_risk_metrics(
    symbol: str
    # current_user: Dict = Depends(get_current_user)  # Temporarily removed for testing
):
    """
    Get detailed growth risk metrics for a symbol
    
    Returns raw metrics used in early warning analysis
    for deeper investigation and custom analysis.
    """
    try:
        logger.info(f"📊 Growth risk metrics requested for {symbol}")
        
        # Run early warning analysis to get metrics
        result = early_warning_engine.analyze_growth_health(symbol.upper())
        
        # Return detailed metrics
        return {
            "symbol": result.symbol,
            "analysis_date": result.analysis_date,
            "overall_risk": result.overall_risk.value,
            "domain_risks": {
                "revenue_quality": {
                    "risk_level": result.domain_risks['revenue_quality'].value,
                    "flags": {
                        "receivables_vs_revenue_divergence": result.revenue_quality.receivables_vs_revenue_divergence,
                        "margin_stress": result.revenue_quality.margin_stress,
                        "revenue_vs_volume_divergence": result.revenue_quality.revenue_vs_volume_divergence
                    }
                },
                "margin_stress": {
                    "risk_level": result.domain_risks['margin_stress'].value,
                    "flags": {
                        "operating_margin_compression": result.margin_stress.operating_margin_compression,
                        "rd_efficiency_decline": result.margin_stress.rd_efficiency_decline
                    }
                },
                "capital_efficiency": {
                    "risk_level": result.domain_risks['capital_efficiency'].value,
                    "flags": {
                        "roic_trend_decay": result.capital_efficiency.roic_trend_decay,
                        "growth_vs_capital_mismatch": result.capital_efficiency.growth_vs_capital_mismatch,
                        "incremental_roic_collapse": result.capital_efficiency.incremental_roic_collapse
                    }
                },
                "management_signals": {
                    "risk_level": result.domain_risks['management_signals'].value,
                    "flags": {
                        "guidance_language_shift": result.management_signals.guidance_language_shift,
                        "kpi_redefinition_removal": result.management_signals.kpi_redefinition_removal,
                        "buybacks_rising_debt": result.management_signals.buybacks_rising_debt
                    }
                }
            },
            "detailed_metrics": result.metrics,
            "warnings": result.warnings,
            "insights": result.insights
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting risk metrics for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get risk metrics: {str(e)}")


def _calculate_portfolio_risk(risk_distribution: Dict[str, int]) -> str:
    """Calculate overall portfolio risk level"""
    total = sum(risk_distribution.values())
    if total == 0:
        return "NO_DATA"
    
    red_percentage = risk_distribution["RED"] / total
    yellow_percentage = risk_distribution["YELLOW"] / total
    
    if red_percentage >= 0.3:  # 30%+ red
        return "HIGH_RISK"
    elif red_percentage >= 0.1 or yellow_percentage >= 0.5:  # 10%+ red or 50%+ yellow
        return "MODERATE_RISK"
    else:
        return "LOW_RISK"


def _generate_portfolio_recommendations(risk_distribution: Dict[str, int], 
                                     signals: List[GrowthQualitySignalResponse]) -> List[str]:
    """Generate portfolio-level recommendations"""
    recommendations = []
    total = sum(risk_distribution.values())
    
    if total == 0:
        return ["No data available for recommendations"]
    
    # Risk-based recommendations
    red_percentage = risk_distribution["RED"] / total
    yellow_percentage = risk_distribution["YELLOW"] / total
    
    if red_percentage >= 0.3:
        recommendations.append("🔴 HIGH RISK: Consider reducing exposure and reviewing risk management")
    elif red_percentage >= 0.1 or yellow_percentage >= 0.5:
        recommendations.append("🟡 MODERATE RISK: Monitor positions closely and consider rebalancing")
    else:
        recommendations.append("🟢 LOW RISK: Current portfolio allocation appears reasonable")
    
    # Add specific recommendations based on signals
    green_count = risk_distribution["GREEN"]
    if green_count > 0:
        recommendations.append(f"✅ MAINTAIN: {green_count} positions with healthy growth quality")
    
    return recommendations


@router.get("/growth-health/{symbol}", response_model=GrowthHealthStateResponse)
async def get_growth_health_classification(
    symbol: str
):
    """
    Get institutional-grade growth health classification
    
    Provides clear investment guidance based on:
    - Structural Risk (balance sheet health, fraud detection)
    - Growth Phase (business lifecycle stage)
    - Investment Posture (BUY/HOLD/TRIM/EXIT)
    
    This eliminates confusion between "healthy" and "growing"
    """
    try:
        logger.info(f"🏥 Growth health classification requested for {symbol}")
        
        # Get early warning analysis
        early_warning_result = early_warning_engine.analyze_growth_health(symbol.upper())
        
        # Convert to dict for classifier
        analysis_dict = early_warning_result.to_dict()
        
        # Create detailed risk metrics from the analysis result
        risk_metrics_result = {
            'domain_risks': {
                'revenue_quality': {
                    'risk_level': analysis_dict.get('domain_risks', {}).get('revenue_quality', 'NO_RISK'),
                    'flags': {
                        'receivables_vs_revenue_divergence': analysis_dict.get('revenue_quality', {}).get('receivables_vs_revenue_divergence', False),
                        'margin_stress': analysis_dict.get('revenue_quality', {}).get('margin_stress', False),
                        'revenue_vs_volume_divergence': analysis_dict.get('revenue_quality', {}).get('revenue_vs_volume_divergence', False)
                    }
                },
                'margin_stress': {
                    'risk_level': analysis_dict.get('domain_risks', {}).get('margin_stress', 'NO_RISK'),
                    'flags': {
                        'operating_margin_compression': analysis_dict.get('margin_stress', {}).get('operating_margin_compression', False),
                        'rd_efficiency_decline': analysis_dict.get('margin_stress', {}).get('rd_efficiency_decline', False)
                    }
                },
                'capital_efficiency': {
                    'risk_level': analysis_dict.get('domain_risks', {}).get('capital_efficiency', 'NO_RISK'),
                    'flags': {
                        'roic_trend_decay': analysis_dict.get('capital_efficiency', {}).get('roic_trend_decay', False),
                        'growth_vs_capital_mismatch': analysis_dict.get('capital_efficiency', {}).get('growth_vs_capital_mismatch', False),
                        'incremental_roic_collapse': analysis_dict.get('capital_efficiency', {}).get('incremental_roic_collapse', False)
                    }
                },
                'management_signals': {
                    'risk_level': analysis_dict.get('domain_risks', {}).get('management_signals', 'NO_RISK'),
                    'flags': {
                        'guidance_language_shift': analysis_dict.get('management_signals', {}).get('guidance_language_shift', False),
                        'kpi_redefinition_removal': analysis_dict.get('management_signals', {}).get('kpi_redefinition_removal', False),
                        'buybacks_rising_debt': analysis_dict.get('management_signals', {}).get('buybacks_rising_debt', False)
                    }
                }
            }
        }
        
        # Classify growth health
        growth_health_state = growth_health_classifier.classify_growth_health(
            analysis_dict, 
            risk_metrics_result
        )
        
        # Convert to response model
        response = GrowthHealthStateResponse(
            symbol=growth_health_state.symbol,
            structural_risk=growth_health_state.structural_risk.value,
            growth_phase=growth_health_state.growth_phase.value,
            investment_posture=growth_health_state.investment_posture.value,
            confidence=growth_health_state.confidence,
            reasoning=growth_health_state.reasoning,
            risk_factors=growth_health_state.risk_factors,
            opportunities=growth_health_state.opportunities,
            forward_return_expectation=growth_health_state.forward_return_expectation,
            analysis_date=growth_health_state.symbol  # Will be updated by classifier
        )
        
        logger.info(f"✅ Growth health classification completed for {symbol}: {growth_health_state.investment_posture.value}")
        return response
        
    except ValueError as e:
        logger.error(f"❌ No fundamentals data for {symbol}: {str(e)}")
        raise HTTPException(status_code=404, detail=f"No fundamentals data available for {symbol}")
    except Exception as e:
        logger.error(f"❌ Error classifying growth health for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to classify growth health: {str(e)}")
    
    red_count = risk_distribution["RED"]
    yellow_count = risk_distribution["YELLOW"]
    
    if red_count > 0:
        recommendations.append(f"🔴 IMMEDIATE: Review {red_count} positions with structural growth breakdown")
        recommendations.append("📉 Consider reducing exposure to RED-rated positions")
    
    if yellow_count > 0:
        recommendations.append(f"🟡 MONITOR: {yellow_count} positions showing early growth stress")
        recommendations.append("⚠️ Reduce position sizes by 50% for YELLOW-rated positions")
    
    green_count = risk_distribution["GREEN"]
    if green_count > 0:
        recommendations.append(f"🟢 MAINTAIN: {green_count} positions with healthy growth quality")
        recommendations.append("✅ GREEN-rated positions can maintain normal allocation")
    
    # Portfolio-level recommendations
    if red_count >= 2:
        recommendations.append("🚨 PORTFOLIO RISK: Multiple growth breakdowns detected")
        recommendations.append("💰 Consider increasing cash allocation until growth quality improves")
    
    if yellow_count >= total * 0.6:
        recommendations.append("⚠️ PORTFOLIO STRESS: High percentage of early warnings")
        recommendations.append("📊 Tighten portfolio risk management across all positions")
    
    return recommendations
