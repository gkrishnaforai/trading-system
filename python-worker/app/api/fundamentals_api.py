"""
Fundamentals Analysis API
Endpoints for fair value analysis and fundamental signal integration
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
import logging
import os

from app.services.fair_value_service import FairValueService
from app.fair_value_v2.service import FairValueV2Service
from app.signal_engines.enhanced_adaptive_signal_engine import EnhancedAdaptiveSignalEngine
from app.observability.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["fundamentals"])

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
ENABLE_FAIR_VALUE_V2 = os.getenv("ENABLE_FAIR_VALUE_V2", "false").strip().lower() in _TRUE_VALUES

# Request models
class FairValueRequest(BaseModel):
    symbol: str
    date: Optional[str] = None  # For historical analysis

class FundamentalScreenRequest(BaseModel):
    symbols: list[str]
    limit: Optional[int] = 20

class EnhancedSignalRequest(BaseModel):
    symbol: str
    date: Optional[str] = None
    asset_type: Optional[str] = "stock"

# Response models
class FairValueResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class FundamentalScreenResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# Initialize services
fair_value_service = FairValueService()
fair_value_v2_service = FairValueV2Service()
enhanced_engine = EnhancedAdaptiveSignalEngine()


@router.get("/fair-value", response_model=FairValueResponse)
async def get_fair_value_analysis_query(symbol: str, method_key: Optional[str] = None):
    """Get fair value analysis for a symbol.

    If `method_key` is provided, this forces a single Fair Value v2 method to run for the symbol.
    """

    try:
        if method_key:
            if not ENABLE_FAIR_VALUE_V2:
                raise HTTPException(status_code=400, detail="fair_value_v2 is disabled")
            try:
                v2 = fair_value_v2_service.calculate_method(method_key=method_key, symbol=symbol)
            except KeyError:
                raise HTTPException(status_code=400, detail=f"unknown method_key: {method_key}")

            return FairValueResponse(
                success=True,
                data={
                    "symbol": symbol,
                    "method_key": method_key,
                    "v2": v2.model_dump(),
                },
            )

        # Default: preserve existing behavior of /fair-value by delegating to the POST handler
        # semantics (v1 fair value with optional v2 override).
        req = FairValueRequest(symbol=symbol)
        return await get_fair_value_analysis(req)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in fair value analysis for {symbol}: {e}")
        return FairValueResponse(success=False, error=f"Error analyzing fair value: {str(e)}")

@router.post("/fair-value", response_model=FairValueResponse)
async def get_fair_value_analysis(request: FairValueRequest):
    """Get comprehensive fair value analysis for a symbol"""
    
    try:
        # Calculate fair value
        if ENABLE_FAIR_VALUE_V2:
            v2 = fair_value_v2_service.calculate(request.symbol)
            fair_value_result = fair_value_service.calculate_fair_value(request.symbol)
            if v2.fair_value and v2.fair_value > 0:
                fair_value_result.fair_value = float(v2.fair_value)
                fair_value_result.individual_valuations = dict(fair_value_result.individual_valuations or {})
                method_key = None
                try:
                    if v2.method_results:
                        method_key = v2.method_results[0].method_key
                except Exception:
                    method_key = None
                fair_value_result.individual_valuations[f"{(method_key or 'v2')}_v2"] = float(v2.fair_value)
                fair_value_result.valuation_metrics = dict(fair_value_result.valuation_metrics or {})
                fair_value_result.valuation_metrics["fair_value_model"] = f"fair_value_v2.{(method_key or 'unknown')}"
        else:
            fair_value_result = fair_value_service.calculate_fair_value(request.symbol)
        
        # Debug logging to understand the data structure
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Fair value result for {request.symbol}: fair_value={fair_value_result.fair_value if fair_value_result else 'None'}, current_price={fair_value_result.current_price if fair_value_result else 'None'}")
        logger.info(f"Fundamentals present: {bool(fair_value_result.fundamentals) if fair_value_result else 'None'}")
        logger.info(f"Individual valuations present: {bool(fair_value_result.individual_valuations) if fair_value_result else 'None'}")
        
        if not fair_value_result or fair_value_result.fair_value <= 0:
            # Determine what data is missing
            missing_data = []
            
            if not fair_value_result.fundamentals:
                missing_data.append("fundamentals (EPS, revenue, ratios)")
            
            if not fair_value_result.individual_valuations:
                missing_data.append("valuation metrics (P/E, P/S, etc.)")
            
            # Create informative error message
            if missing_data:
                error_msg = f"Unable to calculate fair value for {request.symbol}: missing {', '.join(missing_data)}"
            else:
                error_msg = f"Unable to calculate fair value for {request.symbol}: insufficient data for reliable valuation"
            
            return FairValueResponse(
                success=False,
                error=error_msg
            )
        
        # Get industry comparison
        industry_comparison = fair_value_service.get_industry_comparison(request.symbol)
        
        # Determine entry signal
        from app.signal_engines.signal_calculator_core import MarketConditions
        # Create basic conditions for entry signal calculation
        conditions = MarketConditions(
            rsi=50,  # Neutral RSI for fundamental analysis
            sma_20=fair_value_result.current_price,
            sma_50=fair_value_result.current_price,
            ema_20=fair_value_result.current_price,
            current_price=fair_value_result.current_price,
            recent_change=0.0,
            macd=0.0,  # Neutral MACD for fundamental analysis
            macd_signal=0.0,  # Neutral MACD signal for fundamental analysis
            volatility=0.0,
            vix_level=20.0,
            volume=0,
            avg_volume_20d=0
        )
        
        enhanced_signal = enhanced_engine.generate_enhanced_signal_score(request.symbol, conditions)
        
        # Prepare response data
        valuation_ratio = None
        undervaluation_pct = None
        try:
            if fair_value_result.current_price and fair_value_result.current_price > 0 and fair_value_result.fair_value and fair_value_result.fair_value > 0:
                valuation_ratio = fair_value_result.current_price / fair_value_result.fair_value
                undervaluation_pct = (1 - valuation_ratio) * 100
        except Exception:
            valuation_ratio = None
            undervaluation_pct = None

        response_data = {
            "run_id": fair_value_result.run_id,
            "symbol": request.symbol,
            "current_price": fair_value_result.current_price,
            "fair_value": fair_value_result.fair_value,
            "valuation_ratio": valuation_ratio,
            "undervaluation_pct": undervaluation_pct,
            "valuation_rating": fair_value_result.valuation_metrics.get("valuation_rating", "Unknown"),
            "valuation_metrics": fair_value_result.valuation_metrics,
            "quality_score": fair_value_result.quality_score,
            "individual_valuations": fair_value_result.individual_valuations,
            "fundamentals": fair_value_result.fundamentals,
            "industry_comparison": industry_comparison,
            "entry_signal": enhanced_signal.entry_signal,
            "fundamental_scores": {
                "buy_score": enhanced_signal.fundamental.buy_score,
                "sell_score": enhanced_signal.fundamental.sell_score,
                "hold_score": enhanced_signal.fundamental.hold_score,
                "reduce_score": enhanced_signal.fundamental.reduce_score,
                "confidence": enhanced_signal.fundamental.confidence,
                "reasoning": enhanced_signal.fundamental.reasoning
            },
            "updated_at": fair_value_result.updated_at.isoformat()
        }
        
        return FairValueResponse(success=True, data=response_data)
        
    except Exception as e:
        logger.error(f"Error in fair value analysis for {request.symbol}: {e}")
        return FairValueResponse(
            success=False,
            error=f"Error analyzing fair value: {str(e)}"
        )

@router.post("/top-undervalued", response_model=FairValueResponse)
async def get_top_undervalued_stocks():
    """Get top undervalued stocks based on fair value analysis"""
    
    try:
        # Get top undervalued stocks
        undervalued_stocks = fair_value_service.get_top_undervalued_stocks(limit=20)
        
        response_data = {
            "undervalued_stocks": undervalued_stocks,
            "total_count": len(undervalued_stocks),
            "criteria": {
                "max_valuation_ratio": 0.9,  # At least 10% undervalued
                "min_quality_score": 50      # Minimum quality score
            },
            "updated_at": datetime.now().isoformat()
        }
        
        return FairValueResponse(success=True, data=response_data)
        
    except Exception as e:
        logger.error(f"Error getting top undervalued stocks: {e}")
        return FairValueResponse(
            success=False,
            error=f"Error getting undervalued stocks: {str(e)}"
        )

@router.post("/screen", response_model=FundamentalScreenResponse)
async def screen_fundamental_stocks(request: FundamentalScreenRequest):
    """Screen stocks based on fundamental criteria"""
    
    try:
        # Screen stocks
        screened_stocks = enhanced_engine.screen_fundamental_stocks(request.symbols[:50])  # Limit to 50 for performance
        
        # Apply limit
        if request.limit:
            screened_stocks = screened_stocks[:request.limit]
        
        response_data = {
            "screened_stocks": screened_stocks,
            "total_screened": len(screened_stocks),
            "original_count": len(request.symbols),
            "screening_criteria": enhanced_engine.get_fundamental_filter_criteria(),
            "updated_at": datetime.now().isoformat()
        }
        
        return FundamentalScreenResponse(success=True, data=response_data)
        
    except Exception as e:
        logger.error(f"Error in fundamental screening: {e}")
        return FundamentalScreenResponse(
            success=False,
            error=f"Error screening stocks: {str(e)}"
        )

@router.post("/enhanced-signal", response_model=FairValueResponse)
async def get_enhanced_signal(request: EnhancedSignalRequest):
    """Get enhanced signal combining technical and fundamental analysis"""
    
    try:
        # Get market conditions (simplified for this endpoint)
        from app.services.data_service import get_latest_market_data
        
        market_data = get_latest_market_data(request.symbol)
        if not market_data:
            return FairValueResponse(
                success=False,
                error=f"No market data available for {request.symbol}"
            )
        
        # Create market conditions
        from app.signal_engines.signal_calculator_core import MarketConditions
        conditions = MarketConditions(
            rsi=market_data.get('rsi', 50),
            sma_20=market_data.get('sma_20', market_data.get('close', 0)),
            sma_50=market_data.get('sma_50', market_data.get('close', 0)),
            ema_20=market_data.get('ema_20', market_data.get('close', 0)),
            current_price=market_data.get('close', 0),
            recent_change=market_data.get('recent_change', 0),
            volatility=market_data.get('volatility', 0),
            vix_level=market_data.get('vix_level', 20),
            volume=market_data.get('volume', 0),
            avg_volume_20d=market_data.get('avg_volume_20d', 0)
        )
        
        # Generate enhanced signal
        enhanced_signal = enhanced_engine.generate_enhanced_signal_score(request.symbol, conditions)
        
        # Prepare response data
        response_data = {
            "symbol": request.symbol,
            "primary_signal": enhanced_signal.combined.get_primary_signal().value,
            "confidence": enhanced_signal.combined.confidence,
            "entry_signal": enhanced_signal.entry_signal,
            "technical_scores": {
                "buy_score": enhanced_signal.technical.buy_score,
                "sell_score": enhanced_signal.technical.sell_score,
                "hold_score": enhanced_signal.technical.hold_score,
                "reduce_score": enhanced_signal.technical.reduce_score,
                "reasoning": enhanced_signal.technical.reasoning
            },
            "fundamental_scores": {
                "buy_score": enhanced_signal.fundamental.buy_score,
                "sell_score": enhanced_signal.fundamental.sell_score,
                "hold_score": enhanced_signal.fundamental.hold_score,
                "reduce_score": enhanced_signal.fundamental.reduce_score,
                "reasoning": enhanced_signal.fundamental.reasoning
            },
            "combined_scores": {
                "buy_score": enhanced_signal.combined.buy_score,
                "sell_score": enhanced_signal.combined.sell_score,
                "hold_score": enhanced_signal.combined.hold_score,
                "reduce_score": enhanced_signal.combined.reduce_score,
                "reasoning": enhanced_signal.combined.reasoning
            },
            "fair_value_analysis": {
                "current_price": enhanced_signal.fair_value_analysis.current_price,
                "fair_value": enhanced_signal.fair_value_analysis.fair_value,
                "valuation_ratio": enhanced_signal.fair_value_analysis.current_price / enhanced_signal.fair_value_analysis.fair_value if enhanced_signal.fair_value_analysis.fair_value > 0 else 1.0,
                "quality_score": enhanced_signal.quality_score,
                "individual_valuations": enhanced_signal.fair_value_analysis.individual_valuations,
                "fundamentals": enhanced_signal.fair_value_analysis.fundamentals
            },
            "metadata": enhanced_signal.combined.metadata,
            "updated_at": enhanced_signal.updated_at.isoformat()
        }
        
        return FairValueResponse(success=True, data=response_data)
        
    except Exception as e:
        logger.error(f"Error generating enhanced signal for {request.symbol}: {e}")
        return FairValueResponse(
            success=False,
            error=f"Error generating enhanced signal: {str(e)}"
        )

@router.get("/industry-benchmarks")
async def get_industry_benchmarks():
    """Get industry benchmarks for fundamental metrics"""
    
    try:
        benchmarks = fair_value_service.industry_benchmarks
        
        response_data = {
            "industry_benchmarks": benchmarks,
            "total_industries": len(benchmarks),
            "updated_at": datetime.now().isoformat()
        }
        
        return FairValueResponse(success=True, data=response_data)
        
    except Exception as e:
        logger.error(f"Error getting industry benchmarks: {e}")
        return FairValueResponse(
            success=False,
            error=f"Error getting benchmarks: {str(e)}"
        )

@router.get("/quality-thresholds")
async def get_quality_thresholds():
    """Get quality assessment thresholds"""
    
    try:
        thresholds = fair_value_service.quality_thresholds
        
        response_data = {
            "quality_thresholds": thresholds,
            "updated_at": datetime.now().isoformat()
        }
        
        return FairValueResponse(success=True, data=response_data)
        
    except Exception as e:
        logger.error(f"Error getting quality thresholds: {e}")
        return FairValueResponse(
            success=False,
            error=f"Error getting thresholds: {str(e)}"
        )
