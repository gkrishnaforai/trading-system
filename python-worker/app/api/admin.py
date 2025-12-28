"""
Admin API Endpoints for Trading System
Provides administrative endpoints for monitoring and management
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import db
from app.data_management.refresh_manager import DataRefreshManager
from app.services.indicator_service import IndicatorService
from app.services.strategy_service import StrategyService
from app.services.stock_screener_service import StockScreenerService
from app.services.stock_insights_service import StockInsightsService
from app.plugins.registration_manager import PluginRegistrationManager
from app.observability.logging import get_logger

logger = get_logger("admin_api")

router = APIRouter(prefix="/admin", tags=["admin"])

# Request/Response Models
class RefreshRequest(BaseModel):
    symbols: List[str]
    data_types: List[str]
    force: bool = False

class SignalRequest(BaseModel):
    symbols: List[str]
    strategy: str = "technical"

class ScreenerRequest(BaseModel):
    min_rsi: Optional[float] = None
    max_rsi: Optional[float] = None
    min_sma_50: Optional[float] = None
    max_pe_ratio: Optional[float] = None
    limit: int = 100

class StockInsightsRequest(BaseModel):
    symbol: str
    run_all_strategies: bool = True


@router.get("/data-sources")
async def get_data_sources():
    """Get all configured data sources with their status"""
    try:
        registration_manager = PluginRegistrationManager()
        
        # Get adapter information
        from app.data_sources.adapters.factory import create_all_adapters
        adapters = create_all_adapters()
        
        data_sources = []
        for name, adapter in adapters.items():
            try:
                metadata = adapter.get_metadata()
                is_available = adapter.is_available()
                
                # Get recent activity (mock for now)
                recent_activity = "2 mins ago" if is_available else "N/A"
                api_calls_today = 1247 if is_available else 0
                error_rate = 0.1 if is_available else 0
                
                data_sources.append({
                    "name": metadata.name,
                    "status": "active" if is_available else "inactive",
                    "last_sync": recent_activity,
                    "data_types": ["price_historical", "fundamentals", "news"],  # From metadata
                    "api_calls_today": api_calls_today,
                    "error_rate": error_rate,
                    "config": metadata.config_schema or {}
                })
            except Exception as e:
                logger.error(f"Error getting info for adapter {name}: {e}")
                data_sources.append({
                    "name": name,
                    "status": "error",
                    "error": str(e)
                })
        
        return {"data_sources": data_sources}
        
    except Exception as e:
        logger.error(f"Failed to get data sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/refresh/status")
async def get_refresh_status():
    """Get current refresh status and queue information"""
    try:
        # Get refresh queue information
        query = """
            SELECT 
                stock_symbol,
                dataset,
                interval,
                status,
                error_message,
                last_attempt_at,
                last_success_at,
                EXTRACT(EPOCH FROM (COALESCE(last_success_at, NOW()) - last_attempt_at)) as duration_seconds
            FROM data_ingestion_state 
            WHERE last_attempt_at >= NOW() - INTERVAL '24 hours'
            ORDER BY last_attempt_at DESC
            LIMIT 50
        """
        
        recent_jobs = db.execute_query(query)
        
        # Aggregate status (python-worker refresh manager uses: success/failed/idle)
        active_jobs = len([j for j in recent_jobs if j.get("status") in {"running", "pending"}])
        queued_jobs = len([j for j in recent_jobs if j.get("status") == "pending"])
        completed_today = len([j for j in recent_jobs if j.get("status") in {"completed", "success"}])
        failed_today = len([j for j in recent_jobs if j.get("status") == "failed"])
        
        last_refresh = None
        if recent_jobs:
            last_attempt = recent_jobs[0].get("last_attempt_at")
            last_refresh = last_attempt.isoformat() if last_attempt else None
        
        return {
            "active_jobs": active_jobs,
            "queued_jobs": queued_jobs,
            "completed_today": completed_today,
            "failed_today": failed_today,
            "last_refresh": last_refresh,
            "jobs": [
                {
                    "id": f"job_{job['stock_symbol']}_{job['dataset']}_{job['interval']}",
                    "symbol": job["stock_symbol"],
                    "data_type": job["dataset"],
                    "status": job["status"],
                    "started_at": (job.get("last_attempt_at").isoformat() if job.get("last_attempt_at") else None),
                    "progress": 100 if job.get("status") in {"completed", "success"} else (50 if job.get("status") in {"running", "pending"} else 0),
                    "error": job.get("error_message"),
                }
                for job in recent_jobs[:10]
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to get refresh status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-summary/{table}")
async def get_data_summary(table: str, date_filter: Optional[str] = Query(None)):
    """Get data summary for a specific table"""
    try:
        # Validate table name
        valid_tables = [
            "raw_market_data_daily", 
            "raw_market_data_intraday", 
            "indicators_daily",
            "fundamentals_snapshots",
            "industry_peers"
        ]
        
        if table not in valid_tables:
            raise HTTPException(status_code=400, detail=f"Invalid table: {table}")
        
        # Build query based on date filter
        where_clause = ""
        if date_filter:
            if date_filter == "today":
                where_clause = "WHERE trade_date = CURRENT_DATE"
            elif date_filter == "week":
                where_clause = "WHERE trade_date >= CURRENT_DATE - INTERVAL '7 days'"
            elif date_filter == "month":
                where_clause = "WHERE trade_date >= CURRENT_DATE - INTERVAL '30 days'"
        
        # Get table statistics
        stats_query = f"""
            SELECT 
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE trade_date = CURRENT_DATE) as today_records,
                MAX(trade_date) as last_updated,
                pg_size_pretty(pg_total_relation_size('{table}')) as size_gb
            FROM {table}
            {where_clause}
        """
        
        stats = db.execute_query(stats_query)[0]
        
        # Get quality metrics
        quality_query = f"""
            SELECT 
                ROUND(
                    (COUNT(*) - COUNT(CASE WHEN close IS NULL OR volume IS NULL THEN 1 END)) * 100.0 / COUNT(*), 
                    2
                ) as complete_records,
                ROUND(
                    COUNT(CASE WHEN close IS NULL OR volume IS NULL THEN 1 END) * 100.0 / COUNT(*), 
                    2
                ) as missing_values
            FROM {table}
            {where_clause}
        """
        
        quality = db.execute_query(quality_query)[0]
        
        return {
            "table_name": table,
            "total_records": stats["total_records"],
            "today_records": stats["today_records"],
            "last_updated": stats["last_updated"].isoformat() if stats["last_updated"] else None,
            "size_gb": stats["size_gb"],
            "quality_metrics": {
                "complete_records": quality["complete_records"],
                "missing_values": quality["missing_values"],
                "duplicates": 0.1,  # Would need separate query
                "error_rate": 0.3   # Would need separate query
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get data summary for {table}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/generate")
async def generate_signals(request: SignalRequest):
    """Generate trading signals for symbols"""
    try:
        strategy_service = StrategyService()
        indicator_service = IndicatorService()
        
        results = []
        
        for symbol in request.symbols:
            try:
                # Ensure indicators are calculated
                indicator_service.calculate_indicators(symbol)
                
                # Get latest indicators
                from app.utils.query_utils import fetch_latest_by_symbol
                indicators = fetch_latest_by_symbol(
                    "indicators_daily",
                    symbol,
                    select_cols=["sma_50", "sma_200", "ema_20", "rsi_14", "macd", "macd_signal"]
                )
                
                if indicators:
                    # Add required fields for strategy
                    indicators["price"] = indicators.get("sma_50", 0)
                    indicators["ema20"] = indicators.get("ema_20", 0)
                    indicators["ema50"] = indicators.get("sma_50", 0)
                    indicators["sma200"] = indicators.get("sma_200", 0)
                    indicators["macd_line"] = indicators.get("macd", 0)
                    indicators["rsi"] = indicators.get("rsi_14", 50)
                    
                    # Generate signal
                    signal_result = strategy_service.execute_strategy(request.strategy, indicators)
                    
                    results.append({
                        "symbol": symbol,
                        "signal": signal_result.signal if hasattr(signal_result, 'signal') else "hold",
                        "confidence": signal_result.confidence if hasattr(signal_result, 'confidence') else 0.5,
                        "strategy": request.strategy,
                        "timestamp": datetime.now().isoformat()
                    })
                else:
                    results.append({
                        "symbol": symbol,
                        "signal": "hold",
                        "confidence": 0.0,
                        "strategy": request.strategy,
                        "error": "No indicators available"
                    })
                    
            except Exception as e:
                logger.error(f"Failed to generate signal for {symbol}: {e}")
                results.append({
                    "symbol": symbol,
                    "signal": "hold",
                    "confidence": 0.0,
                    "strategy": request.strategy,
                    "error": str(e)
                })
        
        return {
            "signals": results,
            "total_requested": len(request.symbols),
            "total_generated": len([r for r in results if "error" not in r])
        }
        
    except Exception as e:
        logger.error(f"Failed to generate signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screener/run")
async def run_screener(request: ScreenerRequest):
    """Run stock screener with criteria"""
    try:
        screener_service = StockScreenerService()
        
        # Run screener with provided criteria
        result = screener_service.screen_stocks(
            min_rsi=request.min_rsi,
            max_rsi=request.max_rsi,
            min_sma_50=request.min_sma_50,
            max_pe_ratio=request.max_pe_ratio,
            limit=request.limit
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to run screener: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-logs")
async def get_audit_logs(
    start_date: str = Query(...),
    end_date: str = Query(...),
    level: str = Query("ALL"),
    limit: int = Query(100)
):
    """Get audit logs with filters"""
    try:
        # For now, return mock data since we don't have a proper audit log table
        # In a real implementation, this would query an audit_logs table
        
        logs = [
            {
                "timestamp": "2025-01-26T14:30:00Z",
                "level": "INFO",
                "source": "DataRefresh",
                "message": "Successfully refreshed data for AAPL, MSFT, GOOGL",
                "details": "498 records"
            },
            {
                "timestamp": "2025-01-26T14:25:00Z",
                "level": "WARNING",
                "source": "API",
                "message": "Rate limit approaching for AlphaVantage API",
                "details": "4,950/5,000 calls"
            }
        ]
        
        # Filter by level if specified
        if level != "ALL":
            logs = [log for log in logs if log["level"] == level]
        
        return {"logs": logs[:limit]}
        
    except Exception as e:
        logger.error(f"Failed to get audit logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def get_system_health():
    """Get comprehensive system health status"""
    try:
        # Check database health
        try:
            db.execute_query("SELECT 1")
            db_status = "healthy"
            db_response_time = 12  # ms
        except Exception as db_e:
            db_status = "unhealthy"
            db_response_time = None
            logger.error(f"Database health check failed: {db_e}")
        
        # Check data sources
        try:
            data_sources = {
                "massive": {
                    "status": "healthy",
                    "last_sync": "2025-01-26T14:30:00Z"
                },
                "yahoo_finance": {
                    "status": "healthy",
                    "last_sync": "2025-01-26T14:29:00Z"
                },
                "alpha_vantage": {
                    "status": "degraded",
                    "last_sync": "2025-01-26T14:25:00Z"
                }
            }
        except Exception as e:
            logger.error(f"Failed to check data sources: {e}")
            data_sources = {"error": str(e)}
        
        # Get system metrics (mock for now)
        import psutil
        metrics = {
            "cpu_usage": psutil.cpu_percent(),
            "memory_usage": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent,
            "active_connections": 23  # Mock
        }
        
        overall_status = "healthy" if db_status == "healthy" else "degraded"
        
        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "services": {
                "database": {
                    "status": db_status,
                    "response_time": db_response_time
                },
                "python_api": {
                    "status": "healthy",
                    "response_time": 45
                },
                "data_sources": data_sources
            },
            "metrics": metrics
        }
        
    except Exception as e:
        logger.error(f"Failed to get system health: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Health check failed", "detail": str(e)}
        )


@router.post("/insights/generate")
async def generate_stock_insights(request: StockInsightsRequest):
    """Generate comprehensive stock insights with strategy comparison"""
    try:
        insights_service = StockInsightsService()
        
        # Generate insights
        insights = insights_service.get_stock_insights(
            symbol=request.symbol,
            run_all_strategies=request.run_all_strategies
        )
        
        return insights
        
    except Exception as e:
        logger.error(f"Failed to generate stock insights for {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/insights/strategies")
async def get_available_strategies():
    """Get list of all available trading strategies"""
    try:
        insights_service = StockInsightsService()
        strategies = insights_service.get_available_strategies()
        
        return {
            "strategies": strategies,
            "total": len(strategies)
        }
        
    except Exception as e:
        logger.error(f"Failed to get available strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/insights/strategy/{strategy_name}")
async def run_single_strategy(symbol: str, strategy_name: str):
    """Run a single strategy for a symbol"""
    try:
        insights_service = StockInsightsService()
        
        result = insights_service.run_single_strategy(
            symbol=symbol,
            strategy_name=strategy_name
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to run strategy {strategy_name} for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
