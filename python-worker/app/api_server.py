"""
FastAPI Server for Python Worker
Provides endpoints for data fetching, indicators, signals, reports, and more

Industry Standard: RESTful API for AI/ML operations
SOLID: Single Responsibility - API endpoints only
"""
import logging
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.database import db, init_database
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import RefreshMode, DataType
from app.data_validation.signal_readiness import SignalReadinessValidator
from app.services.stock_screener_service import StockScreenerService
from app.services.fundamental_scorer import FundamentalScorer
from app.services.indicator_service import IndicatorService
from app.services.strategy_service import StrategyService
from app.services.swing_risk_manager import SwingRiskManager
from app.strategies import DEFAULT_STRATEGY
from app.di import get_container

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Trading System Python Worker API",
    description="AI/ML Worker API for data fetching, indicators, signals, and reports",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
refresh_manager = DataRefreshManager()
signal_readiness_validator = SignalReadinessValidator()
stock_screener_service = StockScreenerService()
fundamental_scorer = FundamentalScorer()

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_database()
    logger.info("✅ Python Worker API started")


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database connection
        db.execute_query("SELECT 1")
        return {
            "status": "healthy",
            "service": "python-worker",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")


# Request models
class HistoricalDataRequest(BaseModel):
    symbol: str
    period: Optional[str] = "1y"
    include_fundamentals: bool = True
    include_options: bool = True
    calculate_indicators: bool = True


class RefreshDataRequest(BaseModel):
    symbol: str
    data_types: Optional[List[str]] = None  # None = all types
    force: bool = False


class SwingSignalRequest(BaseModel):
    symbol: str
    user_id: Optional[str] = None
    strategy_name: Optional[str] = "swing_trend"


# Data fetching endpoints
@app.post("/api/v1/fetch-historical-data")
async def fetch_historical_data(request: HistoricalDataRequest):
    """
    Fetch historical market data and calculate indicators on-demand
    
    Creates workflow execution record for audit trail
    
    Returns:
        Status and details of data fetched
    """
    import uuid
    from app.workflows.data_frequency import DataFrequency
    
    workflow_id = None
    try:
        logger.info(f"Fetching historical data for {request.symbol} (period: {request.period})")
        
        # Create workflow execution record for audit trail
        workflow_id = str(uuid.uuid4())
        from app.workflows.orchestrator import WorkflowOrchestrator
        orchestrator = WorkflowOrchestrator()
        orchestrator._create_workflow_execution(
            workflow_id=workflow_id,
            workflow_type='on_demand',
            symbols=[request.symbol.upper()],
            data_frequency=DataFrequency.DAILY
        )
        
        # Create stage execution records and symbol states for detailed tracking
        symbol = request.symbol.upper()
        stage_errors = {}  # Track errors by stage
        stage_results = {}  # Track results by stage
        
        # Stage 1: Data Ingestion (price_historical)
        ingestion_stage_id = orchestrator._create_stage_execution(workflow_id, 'ingestion')
        orchestrator._create_symbol_state(workflow_id, symbol, 'ingestion', 'running')
        
        # Use refresh manager for on-demand refresh
        data_types = [
            DataType.PRICE_HISTORICAL,
            DataType.FUNDAMENTALS,
            DataType.EARNINGS,
            DataType.INDUSTRY_PEERS
        ]
        
        # Refresh data
        refresh_result = refresh_manager.refresh_data(
            symbol=symbol,
            data_types=data_types,
            mode=RefreshMode.ON_DEMAND,
            force=True
        )
        
        # Track stage results and errors
        for data_type, result in refresh_result.results.items():
            stage_name = None
            if data_type == 'price_historical':
                stage_name = 'ingestion'
            elif data_type == 'fundamentals':
                stage_name = 'fundamentals'
            elif data_type == 'earnings':
                stage_name = 'earnings'
            elif data_type == 'industry_peers':
                stage_name = 'industry_peers'
            
            if stage_name:
                stage_results[stage_name] = {
                    'status': result.status.value if result else 'unknown',
                    'success': result.status.value == 'success' if result else False,
                    'error': result.error if result else None,
                    'message': result.message if result else None
                }
                
                if result and result.status.value != 'success':
                    stage_errors[stage_name] = result.error or result.message or 'Unknown error'
                    # Update symbol state to failed
                    orchestrator._update_symbol_state(
                        workflow_id, symbol, stage_name, 'failed',
                        error=result.error or result.message
                    )
                else:
                    # Update symbol state to completed
                    orchestrator._update_symbol_state(workflow_id, symbol, stage_name, 'completed')
        
        # Update ingestion stage status
        price_result = refresh_result.results.get('price_historical')
        ingestion_succeeded = price_result.status.value == 'success' if price_result else False
        orchestrator._update_stage_status(
            ingestion_stage_id,
            'completed' if ingestion_succeeded else 'failed',
            {
                'symbols_succeeded': 1 if ingestion_succeeded else 0,
                'symbols_failed': 1 if not ingestion_succeeded else 0
            }
        )
        
        # Indicators are auto-calculated after price data fetch
        indicators_status = None
        indicators_stage_id = None
        if request.calculate_indicators:
            # Stage 2: Indicator Calculation
            indicators_stage_id = orchestrator._create_stage_execution(workflow_id, 'indicators')
            orchestrator._create_symbol_state(workflow_id, symbol, 'indicators', 'running')
            
            indicators_result = refresh_manager.refresh_data(
                symbol=symbol,
                data_types=[DataType.INDICATORS],
                mode=RefreshMode.ON_DEMAND,
                force=True
            )
            indicators_result_obj = indicators_result.results.get('indicators')
            indicators_status = indicators_result_obj.status.value == 'success' if indicators_result_obj else False
            
            # Track indicators stage
            stage_results['indicators'] = {
                'status': indicators_result_obj.status.value if indicators_result_obj else 'failed',
                'success': indicators_status,
                'error': indicators_result_obj.error if indicators_result_obj else None,
                'message': indicators_result_obj.message if indicators_result_obj else None
            }
            
            if not indicators_status:
                stage_errors['indicators'] = indicators_result_obj.error if indicators_result_obj else 'Indicator calculation failed'
                orchestrator._update_symbol_state(
                    workflow_id, symbol, 'indicators', 'failed',
                    error=indicators_result_obj.error if indicators_result_obj else 'Indicator calculation failed'
                )
            else:
                orchestrator._update_symbol_state(workflow_id, symbol, 'indicators', 'completed')
            
            # Update indicators stage status
            orchestrator._update_stage_status(
                indicators_stage_id,
                'completed' if indicators_status else 'failed',
                {
                    'symbols_succeeded': 1 if indicators_status else 0,
                    'symbols_failed': 1 if not indicators_status else 0
                }
            )
        else:
            price_result = refresh_result.results.get('price_historical')
            indicators_status = price_result.status.value == 'success' if price_result else False
        
        # Get validation report if available
        validation_report = None
        try:
            validation_query = """
                SELECT report_json, overall_status, critical_issues, warnings, rows_dropped
                FROM data_validation_reports
                WHERE symbol = :symbol AND data_type = 'price_historical'
                ORDER BY validation_timestamp DESC
                LIMIT 1
            """
            validation_result = db.execute_query(validation_query, {"symbol": request.symbol.upper()})
            if validation_result:
                validation_report = json.loads(validation_result[0]['report_json'])
        except Exception as e:
            logger.debug(f"Could not fetch validation report (non-critical): {e}")
        
        # Check signal readiness
        signal_readiness = None
        try:
            readiness_result = signal_readiness_validator.check_readiness(
                symbol=request.symbol.upper(),
                signal_type="swing_trend"
            )
            signal_readiness = readiness_result.to_dict()
        except Exception as e:
            logger.debug(f"Could not check signal readiness (non-critical): {e}")
        
        # Build comprehensive result
        price_result = refresh_result.results.get('price_historical')
        fundamentals_result = refresh_result.results.get('fundamentals')
        earnings_result = refresh_result.results.get('earnings')
        industry_peers_result = refresh_result.results.get('industry_peers')
        
        # Get data source name from refresh manager
        data_source_name = refresh_manager.data_source.name
        
        # Get latest audit records to extract data source for each data type
        audit_query = """
            SELECT fetch_type, data_source, success, error_message
            FROM data_fetch_audit
            WHERE symbol = :symbol
            ORDER BY fetch_timestamp DESC
            LIMIT 10
        """
        audit_records = db.execute_query(audit_query, {"symbol": request.symbol.upper()})
        
        # Map data source by fetch type
        data_source_map = {}
        for record in audit_records:
            fetch_type = record.get('fetch_type')
            if fetch_type and fetch_type not in data_source_map:
                data_source_map[fetch_type] = record.get('data_source', data_source_name)
        
        result = {
            "success": refresh_result.total_failed == 0 and indicators_status,
            "symbol": request.symbol.upper(),
            "period": request.period,
            "data_source": data_source_name,  # Overall data source used
            "summary": {
                "total_requested": refresh_result.total_requested + (1 if request.calculate_indicators else 0),
                "total_successful": refresh_result.total_successful + (1 if indicators_status else 0),
                "total_failed": refresh_result.total_failed + (0 if indicators_status else 1),
                "total_skipped": refresh_result.total_skipped
            },
            "results": {
                "price_historical": {
                    "status": price_result.status.value if price_result else "failed",
                    "message": price_result.message if price_result else "Not requested",
                    "rows_affected": price_result.rows_affected if price_result else 0,
                    "error": price_result.error if price_result else None,
                    "data_source": data_source_map.get('price_historical', data_source_name),
                    "validation": validation_report
                },
                "fundamentals": {
                    "status": fundamentals_result.status.value if fundamentals_result else "not_requested",
                    "message": fundamentals_result.message if fundamentals_result else "Not requested",
                    "error": fundamentals_result.error if fundamentals_result else None,
                    "data_source": data_source_map.get('fundamentals', data_source_name)
                },
                "earnings": {
                    "status": earnings_result.status.value if earnings_result else "not_requested",
                    "message": earnings_result.message if earnings_result else "Not requested",
                    "rows_affected": earnings_result.rows_affected if earnings_result else 0,
                    "error": earnings_result.error if earnings_result else None,
                    "data_source": data_source_map.get('earnings', data_source_name)
                },
                "industry_peers": {
                    "status": industry_peers_result.status.value if industry_peers_result else "not_requested",
                    "message": industry_peers_result.message if industry_peers_result else "Not requested",
                    "error": industry_peers_result.error if industry_peers_result else None,
                    "data_source": data_source_map.get('industry_peers', data_source_name)
                },
                "indicators": {
                    "status": "success" if indicators_status else "failed",
                    "message": "Indicators calculated" if indicators_status else "Failed to calculate indicators",
                    "error": "Indicator calculation failed or not performed" if not indicators_status else None,
                    "data_source": "internal"  # Indicators are calculated internally, not from external source
                }
            },
            "signal_readiness": signal_readiness,
            "message": f"Refreshed {refresh_result.total_successful}/{refresh_result.total_requested} data types for {request.symbol.upper()} using {data_source_name}",
            "workflow_id": workflow_id  # Include workflow ID for audit trail
        }
        
        # Update workflow execution status with detailed error information
        if workflow_id:
            try:
                workflow_success = refresh_result.total_failed == 0 and (indicators_status if request.calculate_indicators else True)
                
                # Build detailed metadata with stage errors
                metadata = {
                    'symbols_succeeded': 1 if workflow_success else 0,
                    'symbols_failed': 1 if not workflow_success else 0,
                    'total_requested': refresh_result.total_requested + (1 if request.calculate_indicators else 0),
                    'total_successful': refresh_result.total_successful + (1 if (indicators_status if request.calculate_indicators else False) else 0),
                    'total_failed': refresh_result.total_failed + (0 if (indicators_status if request.calculate_indicators else True) else 1),
                    'failed_stages': list(stage_errors.keys()),
                    'stage_errors': stage_errors,
                    'stage_results': stage_results,
                    'failed_data_types': [
                        k for k, v in refresh_result.results.items() 
                        if v and v.status.value != 'success'
                    ]
                }
                
                orchestrator._update_workflow_status(
                    workflow_id=workflow_id,
                    status='completed' if workflow_success else 'failed',
                    metadata=metadata
                )
            except Exception as e:
                logger.warning(f"Failed to update workflow status (non-critical): {e}")
        
        return result
        
    except Exception as e:
        # Update workflow status to failed with detailed error
        if workflow_id:
            try:
                from app.workflows.orchestrator import WorkflowOrchestrator
                orchestrator = WorkflowOrchestrator()
                
                # Update any running symbol states to failed
                try:
                    orchestrator._update_symbol_state(workflow_id, request.symbol.upper(), 'ingestion', 'failed', error=str(e))
                except:
                    pass
                
                orchestrator._update_workflow_status(
                    workflow_id=workflow_id,
                    status='failed',
                    metadata={
                        'error': str(e),
                        'error_type': type(e).__name__,
                        'failed_stage': 'ingestion',  # Failed at the start
                        'symbols_succeeded': 0,
                        'symbols_failed': 1
                    }
                )
            except:
                pass  # Non-critical
        
        logger.error(f"Error fetching historical data for {request.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/refresh-data")
async def refresh_data(request: RefreshDataRequest):
    """
    Refresh data for a symbol
    
    Args:
        symbol: Stock symbol
        data_types: List of data types to refresh (None = all)
        force: Force refresh even if not needed
    """
    try:
        # Convert data type strings to DataType enum
        data_types = None
        if request.data_types:
            data_types = [DataType(dt) for dt in request.data_types]
        else:
            # All data types
            data_types = [
                DataType.PRICE_HISTORICAL,
                DataType.FUNDAMENTALS,
                DataType.NEWS,
                DataType.EARNINGS,
                DataType.INDUSTRY_PEERS
            ]
        
        result = refresh_manager.refresh_data(
            symbol=request.symbol.upper(),
            data_types=data_types,
            mode=RefreshMode.ON_DEMAND,
            force=request.force
        )
        
        return {
            "success": result.total_failed == 0,
            "symbol": request.symbol.upper(),
            "results": {k: {
                "status": v.status.value,
                "message": v.message,
                "error": v.error
            } for k, v in result.results.items()},
            "summary": {
                "total_requested": result.total_requested,
                "total_successful": result.total_successful,
                "total_failed": result.total_failed,
                "total_skipped": result.total_skipped
            }
        }
    except Exception as e:
        logger.error(f"Error refreshing data for {request.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Audit and validation endpoints
@app.get("/api/v1/data-fetch-audit/{symbol}")
async def get_data_fetch_audit(symbol: str, limit: int = 20):
    """Get data fetch audit history for a symbol"""
    try:
        query = """
            SELECT * FROM data_fetch_audit
            WHERE symbol = :symbol
            ORDER BY fetch_timestamp DESC
            LIMIT :limit
        """
        records = db.execute_query(query, {"symbol": symbol.upper(), "limit": limit})
        return {"symbol": symbol.upper(), "audit_records": records, "count": len(records)}
    except Exception as e:
        logger.error(f"Error fetching data fetch audit for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/data-validation-reports/{symbol}")
async def get_data_validation_reports(symbol: str, data_type: str = "price_historical", limit: int = 1):
    """Get latest data validation reports for a symbol"""
    try:
        query = """
            SELECT report_json FROM data_validation_reports
            WHERE symbol = :symbol AND data_type = :data_type
            ORDER BY validation_timestamp DESC
            LIMIT :limit
        """
        records = db.execute_query(query, {"symbol": symbol.upper(), "data_type": data_type, "limit": limit})
        
        reports = []
        for record in records:
            if record.get('report_json'):
                reports.append(json.loads(record['report_json']))
        
        return {"symbol": symbol.upper(), "data_type": data_type, "reports": reports, "count": len(reports)}
    except Exception as e:
        logger.error(f"Error fetching data validation reports for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/signal-readiness/{symbol}")
async def get_signal_readiness(symbol: str, signal_type: str = "any"):
    """Get signal readiness status for a symbol"""
    try:
        readiness = signal_readiness_validator.check_readiness(symbol.upper(), signal_type)
        return readiness.to_dict()
    except Exception as e:
        logger.error(f"Error checking signal readiness for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Swing trading endpoints
@app.post("/api/v1/swing/signal")
async def generate_swing_signal(request: SwingSignalRequest):
    """
    Generate swing trading signal for a symbol
    
    Args:
        symbol: Stock symbol (e.g., TQQQ)
        user_id: Optional user ID for context
        strategy_name: Strategy name (default: swing_trend)
    
    Returns:
        Swing signal with entry/exit levels
    """
    try:
        symbol = request.symbol.upper()
        
        # Pre-flight check for signal readiness
        readiness = signal_readiness_validator.check_readiness(symbol, "swing_trend")
        if readiness.readiness_status == "not_ready":
            raise HTTPException(
                status_code=400,
                detail=f"Signal generation not possible for {symbol}: {'. '.join(readiness.readiness_reason)}"
            )
        elif readiness.readiness_status == "partial":
            logger.warning(f"⚠️ Generating signal for {symbol} with partial readiness: {'. '.join(readiness.readiness_reason)}")
        
        container = get_container()
        data_source = container.get('data_source')
        
        # Fetch historical data
        logger.info(f"Fetching historical data for {symbol} for swing signal")
        market_data = data_source.fetch_price_data(symbol, period="1y")
        
        if market_data is None or market_data.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No market data available for {symbol}. Please refresh data first."
            )
        
        if len(market_data) < 50:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data for {symbol}. Need at least 50 periods, have {len(market_data)}"
            )
        
        # Market context + persisted indicators/fundamentals
        from app.services.market_context_service import MarketContextService
        from app.services.stock_insights_service import StockInsightsService
        from app.signal_engines.swing_regime_engine import SwingRegimeEngine
        
        market_context = MarketContextService().get_market_context()
        insights = StockInsightsService()
        indicators = insights._fetch_indicators(symbol, market_data)
        fundamentals = insights._fetch_fundamentals(symbol)

        # Run SwingRegimeEngine (Layered model) for rich UI breakdown
        engine = SwingRegimeEngine()
        engine_result = engine.generate_signal(
            symbol=symbol,
            market_data=market_data,
            indicators=indicators,
            fundamentals=fundamentals,
            market_context=market_context,
        )
        result_dict = engine_result.to_dict()

        # Build Layer 1-5 payload for Streamlit
        regime = getattr(market_context.regime, "value", str(market_context.regime))
        direction_score = result_dict.get("metadata", {}).get("direction_score")
        try:
            prob_up = (float(direction_score) + 1.0) / 2.0 if direction_score is not None else None
        except Exception:
            prob_up = None
        prob_down = (1.0 - prob_up) if prob_up is not None else None

        confidence = float(result_dict.get("confidence", 0.0) or 0.0)

        # Allocation/vehicle suggestion for leveraged NASDAQ trading
        action = "HOLD"
        suggested_vehicle = "CASH"
        if prob_up is not None and prob_up > 0.65:
            action = "BUY"
            suggested_vehicle = "TQQQ"
        elif prob_down is not None and prob_down > 0.65:
            action = "BUY"
            suggested_vehicle = "SQQQ"

        allocation_pct = float(result_dict.get("position_size_pct", 0.0) or 0.0)

        layers = {
            "layer_1_regime": {
                "regime": regime,
                "regime_confidence": getattr(market_context, "regime_confidence", None),
                "nasdaq_trend": getattr(market_context, "nasdaq_trend", None),
                "vix": getattr(market_context, "vix", None),
                "yield_curve_spread": getattr(market_context, "yield_curve_spread", None),
                "breadth": getattr(market_context, "breadth", None),
            },
            "layer_2_direction": {
                "direction_score": direction_score,
                "prob_up": prob_up,
                "prob_down": prob_down,
                "confidence": confidence,
            },
            "layer_3_allocation": {
                "suggested_vehicle": suggested_vehicle,
                "allocation_pct": allocation_pct,
            },
            "layer_4_reality_adjustment": {
                "original_position_size": result_dict.get("metadata", {}).get("original_position_size"),
                "adjusted_position_size": result_dict.get("metadata", {}).get("adjusted_position_size"),
                "hold_duration_days": result_dict.get("metadata", {}).get("hold_duration_days"),
            },
            "layer_5_daily_output": {
                "date": datetime.now().date().isoformat(),
                "action": action,
                "symbol": suggested_vehicle,
                "allocation_pct": allocation_pct,
                "confidence": confidence,
                "reasoning": result_dict.get("reasoning", []),
            },
        }

        # Backward-compatible response (keep existing fields)
        return {
            "symbol": symbol,
            "signal": result_dict.get("signal", "HOLD"),
            "confidence": confidence,
            "reason": " | ".join(result_dict.get("reasoning", [])[:8]) if result_dict.get("reasoning") else "",
            "metadata": {
                **(result_dict.get("metadata", {}) or {}),
                "entry_price_range": result_dict.get("entry_price_range"),
                "stop_loss": result_dict.get("stop_loss"),
                "take_profit": result_dict.get("take_profit"),
                "position_size_pct": result_dict.get("position_size_pct"),
            },
            "strategy": request.strategy_name or "swing_regime",
            "readiness": readiness.to_dict(),
            "engine": {
                "engine_name": result_dict.get("engine_name"),
                "engine_version": result_dict.get("engine_version"),
                "engine_tier": result_dict.get("engine_tier"),
            },
            "layers": layers,
            "market_context": {
                "regime": regime,
                "regime_confidence": getattr(market_context, "regime_confidence", None),
                "vix": getattr(market_context, "vix", None),
                "nasdaq_trend": getattr(market_context, "nasdaq_trend", None),
                "breadth": getattr(market_context, "breadth", None),
                "yield_curve_spread": getattr(market_context, "yield_curve_spread", None),
                "timestamp": getattr(market_context, "timestamp", None).isoformat() if getattr(market_context, "timestamp", None) else None,
            },
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating swing signal for {request.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/swing/risk/check")
async def check_swing_risk(request: SwingSignalRequest):
    """Check swing trading risk for a symbol"""
    try:
        risk_manager = SwingRiskManager()
        risk_assessment = risk_manager.assess_risk(
            symbol=request.symbol.upper(),
            user_id=request.user_id
        )
        return risk_assessment
    except Exception as e:
        logger.error(f"Error checking swing risk for {request.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Register screener endpoints
from app.api_screener import register_screener_endpoints
register_screener_endpoints(app)


# Live price endpoint
@app.get("/api/v1/live-price/{symbol}")
async def get_live_price(symbol: str):
    """Get live/current price for a symbol"""
    try:
        from app.data_sources import get_data_source
        
        data_source = get_data_source()
        current_price = data_source.fetch_current_price(symbol.upper())
        
        if current_price is None:
            raise HTTPException(
                status_code=404,
                detail=f"Could not fetch live price for {symbol}"
            )
        
        return {
            "symbol": symbol.upper(),
            "price": current_price,
            "timestamp": datetime.now().isoformat(),
            "source": data_source.__class__.__name__
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching live price for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Calculate indicators endpoint
@app.post("/api/v1/calculate-indicators/{symbol}")
async def calculate_indicators(symbol: str, force: bool = False):
    """Calculate indicators for a symbol"""
    try:
        service = IndicatorService()
        success = service.calculate_indicators(symbol.upper())
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to calculate indicators for {symbol}"
            )
        
        return {
            "success": True,
            "symbol": symbol.upper(),
            "message": "Indicators calculated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating indicators for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Strategy execution request model
class StrategyExecuteRequest(BaseModel):
    symbol: str
    strategy_name: Optional[str] = None
    user_id: Optional[str] = None


# Strategy execution endpoint
@app.post("/api/v1/strategy/execute")
async def execute_strategy(request: StrategyExecuteRequest):
    """Execute a trading strategy for a symbol"""
    try:
        symbol = request.symbol.upper()
        strategy_name = request.strategy_name
        user_id = request.user_id
        container = get_container()
        strategy_service = container.get('strategy_service')
        data_source = container.get('data_source')
        
        # Fetch indicators
        from app.utils.database_helper import DatabaseQueryHelper
        indicators_data = DatabaseQueryHelper.get_latest_indicators(symbol)
        
        if not indicators_data:
            raise HTTPException(
                status_code=404,
                detail=f"No indicators found for {symbol}. Calculate indicators first."
            )
        
        # Get current price from raw_market_data (indicators don't have close)
        stock_data = DatabaseQueryHelper.get_stock_by_symbol(symbol, "raw_market_data")
        current_price = stock_data.get('close', 0) if stock_data else 0
        
        # Convert to indicators dict format expected by strategy
        import pandas as pd
        indicators = {
            'price': pd.Series([current_price]),
            'ema20': pd.Series([indicators_data.get('ema20', 0)]),
            'ema50': pd.Series([indicators_data.get('ema50', 0)]),
            'sma200': pd.Series([indicators_data.get('sma200', 0)]),
            'rsi': pd.Series([indicators_data.get('rsi', 0)]),
            'macd': pd.Series([indicators_data.get('macd', 0)]),
            'macd_signal': pd.Series([indicators_data.get('macd_signal', 0)]),
            'macd_histogram': pd.Series([indicators_data.get('macd_histogram', 0)]),
            'atr': pd.Series([indicators_data.get('atr', 0)]),
            'volume': pd.Series([indicators_data.get('volume', 0)]),
            'long_term_trend': pd.Series([indicators_data.get('long_term_trend', 'neutral')]),
            'medium_term_trend': pd.Series([indicators_data.get('medium_term_trend', 'neutral')])
        }
        
        # Fetch market data
        market_data = data_source.fetch_price_data(symbol, period="1y")
        
        # Execute strategy
        strategy_result = strategy_service.execute_strategy(
            strategy_name=strategy_name or DEFAULT_STRATEGY,
            indicators=indicators,
            market_data=market_data,
            context={'symbol': symbol, 'user_id': user_id}
        )
        
        return {
            "symbol": symbol,
            "strategy": strategy_result.strategy_name,
            "signal": strategy_result.signal.upper(),
            "confidence": strategy_result.confidence,
            "reason": strategy_result.reason,
            "metadata": strategy_result.metadata
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing strategy for {request.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Workflow audit endpoints
@app.get("/api/v1/workflow/executions")
async def get_workflow_executions(limit: int = 50, workflow_type: Optional[str] = None):
    """Get workflow execution history"""
    try:
        query = """
            SELECT 
                workflow_id,
                workflow_type,
                status,
                current_stage,
                started_at,
                completed_at,
                metadata_json
            FROM workflow_executions
            WHERE 1=1
        """
        params = {}
        
        if workflow_type:
            query += " AND workflow_type = :workflow_type"
            params['workflow_type'] = workflow_type
        
        query += " ORDER BY started_at DESC LIMIT :limit"
        params['limit'] = limit
        
        results = db.execute_query(query, params)
        
        # Parse metadata JSON
        for result in results:
            if result.get('metadata_json'):
                try:
                    result['metadata'] = json.loads(result['metadata_json'])
                except:
                    result['metadata'] = {}
            result.pop('metadata_json', None)
        
        return {"executions": results, "count": len(results)}
    except Exception as e:
        logger.error(f"Error fetching workflow executions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/workflow/executions/{workflow_id}/stages")
async def get_workflow_stages(workflow_id: str):
    """Get stage execution history for a workflow"""
    try:
        query = """
            SELECT 
                stage_execution_id,
                workflow_id,
                stage_name,
                status,
                started_at,
                completed_at,
                updated_at,
                symbols_succeeded,
                symbols_failed,
                metadata_json
            FROM workflow_stage_executions
            WHERE workflow_id = :workflow_id
            ORDER BY started_at ASC
        """
        
        results = db.execute_query(query, {"workflow_id": workflow_id})
        
        # Parse metadata JSON
        for result in results:
            if result.get('metadata_json'):
                try:
                    result['metadata'] = json.loads(result['metadata_json'])
                except:
                    result['metadata'] = {}
            result.pop('metadata_json', None)
        
        return {"stages": results, "count": len(results)}
    except Exception as e:
        logger.error(f"Error fetching workflow stages: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/workflow/executions/{workflow_id}/symbols")
async def get_workflow_symbol_states(workflow_id: str, symbol: Optional[str] = None):
    """Get symbol state history for a workflow"""
    try:
        query = """
            SELECT 
                workflow_id,
                symbol,
                stage,
                status,
                error_message,
                retry_count,
                started_at,
                completed_at,
                updated_at
            FROM workflow_symbol_states
            WHERE workflow_id = :workflow_id
        """
        params = {"workflow_id": workflow_id}
        
        if symbol:
            query += " AND symbol = :symbol"
            params['symbol'] = symbol.upper()
        
        query += " ORDER BY symbol, started_at ASC"
        
        results = db.execute_query(query, params)
        
        return {"symbol_states": results, "count": len(results)}
    except Exception as e:
        logger.error(f"Error fetching workflow symbol states: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/workflow/executions/{workflow_id}/summary")
async def get_workflow_summary(workflow_id: str):
    """Get complete workflow summary with all audit data"""
    try:
        # Get workflow execution
        workflow_query = """
            SELECT 
                workflow_id,
                workflow_type,
                status,
                current_stage,
                started_at,
                completed_at,
                metadata_json
            FROM workflow_executions
            WHERE workflow_id = :workflow_id
        """
        workflow_result = db.execute_query(workflow_query, {"workflow_id": workflow_id})
        
        if not workflow_result:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
        
        workflow = workflow_result[0]
        if workflow.get('metadata_json'):
            try:
                workflow['metadata'] = json.loads(workflow['metadata_json'])
            except:
                workflow['metadata'] = {}
        workflow.pop('metadata_json', None)
        
        # Get stages
        stages_query = """
            SELECT 
                stage_execution_id,
                stage_name,
                status,
                started_at,
                completed_at,
                symbols_succeeded,
                symbols_failed
            FROM workflow_stage_executions
            WHERE workflow_id = :workflow_id
            ORDER BY started_at ASC
        """
        stages = db.execute_query(stages_query, {"workflow_id": workflow_id})
        
        # Get symbol states
        symbols_query = """
            SELECT 
                symbol,
                stage,
                status,
                error_message,
                retry_count,
                started_at,
                completed_at
            FROM workflow_symbol_states
            WHERE workflow_id = :workflow_id
            ORDER BY symbol, started_at ASC
        """
        symbol_states = db.execute_query(symbols_query, {"workflow_id": workflow_id})
        
        return {
            "workflow": workflow,
            "stages": stages,
            "symbol_states": symbol_states,
            "summary": {
                "total_stages": len(stages),
                "total_symbols": len(set(s['symbol'] for s in symbol_states)),
                "stages_completed": len([s for s in stages if s['status'] == 'completed']),
                "symbols_succeeded": sum(s.get('symbols_succeeded', 0) for s in stages),
                "symbols_failed": sum(s.get('symbols_failed', 0) for s in stages)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workflow summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Data source configuration endpoint
@app.get("/api/v1/data-source/config")
async def get_data_source_config():
    """Get current data source configuration"""
    try:
        from app.data_sources import get_data_source, DEFAULT_DATA_SOURCE, DATA_SOURCES
        from app.config import settings
        
        # Check if Massive is available
        try:
            from app.data_sources.massive_source import MASSIVE_AVAILABLE
            massive_available = MASSIVE_AVAILABLE
        except ImportError:
            massive_available = False
        
        # Get primary and fallback sources from config (Industry Standard pattern)
        from app.data_sources import (
            PRIMARY_DATA_SOURCE, FALLBACK_DATA_SOURCE
        )
        
        # Get source names from config
        primary_source_name = PRIMARY_DATA_SOURCE
        fallback_source_name = FALLBACK_DATA_SOURCE if FALLBACK_DATA_SOURCE else None
        
        # Get current composite source (with fallback if configured)
        current_source = get_data_source(primary_source_name)  # This returns composite if fallback is configured
        source_name = current_source.name
        
        # If current source is composite, extract primary and fallback names
        if hasattr(current_source, 'primary_source') and hasattr(current_source, 'fallback_source'):
            # It's a composite source
            primary_source_name = current_source.primary_source.name
            fallback_source_name = current_source.fallback_source.name if current_source.fallback_source else None
        elif hasattr(current_source, 'primary_source'):
            # It's a fallback source (legacy)
            primary_source_name = current_source.primary_source.name
            if hasattr(current_source, 'fallback_source') and current_source._use_fallback:
                fallback_source_name = current_source.fallback_source.name
        else:
            # Single source
            primary_source_name = source_name
            fallback_source_name = None
        
        # Get available sources
        available_sources = list(DATA_SOURCES.keys())
        
        # Debug information to help diagnose configuration issues
        debug_info = {
            "config_default_provider": settings.default_data_provider,
            "massive_enabled_from_config": settings.massive_enabled,
            "massive_api_key_set": bool(settings.massive_api_key),
            "massive_api_key_length": len(settings.massive_api_key) if settings.massive_api_key else 0,
            "massive_available": massive_available,
            "data_sources_registry": list(DATA_SOURCES.keys()),
            "default_data_source": DEFAULT_DATA_SOURCE,
            "why_not_massive": "massive not in DATA_SOURCES" if "massive" not in DATA_SOURCES else "massive is available"
        }
        
        return {
            "current_source": source_name,
            "primary_source": primary_source_name,
            "fallback_source": fallback_source_name,
            "default_provider": settings.default_data_provider,  # Legacy
            "primary_provider": settings.primary_data_provider,  # New config
            "fallback_provider": settings.fallback_data_provider,  # New config
            "available_sources": available_sources,
            "massive_enabled": settings.massive_enabled,
            "massive_configured": bool(settings.massive_api_key),
            "yahoo_finance_enabled": settings.yahoo_finance_enabled,
            "debug": debug_info
        }
    except Exception as e:
        logger.error(f"Error getting data source config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

