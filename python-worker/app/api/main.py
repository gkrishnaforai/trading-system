"""
Main API Endpoints for Trading System
Provides core functionality endpoints
"""
from datetime import datetime
from uuid import uuid4
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.database import db
from app.data_management.refresh_manager import DataRefreshManager, DataType
from app.services.indicator_service import IndicatorService
from app.services.strategy_service import StrategyService
from app.observability import audit
from app.observability.context import set_ingestion_run_id
from app.observability.logging import get_logger

logger = get_logger("main_api")

router = APIRouter(tags=["main"])

# Request/Response Models
class RefreshRequest(BaseModel):
    symbols: List[str]
    data_types: List[str]
    force: bool = False

class RefreshResponse(BaseModel):
    success: bool
    message: str
    results: Dict[str, Any]


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_data(request: RefreshRequest, background_tasks: BackgroundTasks):
    """Trigger data refresh for specific symbols and data types"""
    run_id = uuid4()
    set_ingestion_run_id(run_id)
    try:
        try:
            audit.start_run(run_id, metadata={"operation": "refresh", "symbols": request.symbols, "data_types": request.data_types})
            audit.log_event(level="info", provider="system", operation="refresh.request_start")
        except Exception:
            pass

        refresh_manager = DataRefreshManager()
        
        # Convert string data types to DataType enum
        data_type_mapping = {
            "price_historical": DataType.PRICE_HISTORICAL,
            "price_current": DataType.PRICE_CURRENT,
            "price_intraday_15m": DataType.PRICE_INTRADAY_15M,
            "fundamentals": DataType.FUNDAMENTALS,
            "indicators": DataType.INDICATORS,
            "news": DataType.NEWS,
            "earnings": DataType.EARNINGS,
            "industry_peers": DataType.INDUSTRY_PEERS
        }
        
        results = {}
        successful_count = 0
        failed_count = 0
        
        for symbol in request.symbols:
            try:
                logger.info(f"Starting refresh for symbol: {symbol}")
                
                # Convert data types
                data_types = []
                unknown_types: List[str] = []
                for dt in request.data_types:
                    if dt in data_type_mapping:
                        data_types.append(data_type_mapping[dt])
                        logger.info(f"Will refresh data type '{dt}' for symbol {symbol}")
                    else:
                        unknown_types.append(dt)
                        logger.warning(f"Unknown data type '{dt}' requested for symbol {symbol}")
                
                logger.info(f"Calling refresh_manager.refresh_data for {symbol} with {len(data_types)} known data types")
                
                # Refresh data for symbol
                result = refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=data_types,
                    force=request.force
                )
                
                logger.info(f"Refresh completed for {symbol}: {result.total_successful}/{result.total_successful + result.total_failed} successful")
                
                results[symbol] = {
                    "success": result.total_successful > 0,
                    "total_requested": len(request.data_types),
                    "total_successful": result.total_successful,
                    "total_failed": result.total_failed,
                    "results": {}
                }

                # Add results for known data types
                for dt in data_types:
                    status = result.results[dt.value].status.value if dt.value in result.results else "skipped"
                    message = result.results[dt.value].message if dt.value in result.results else "Not requested"
                    
                    if status == "success":
                        logger.info(f"✅ Successfully refreshed '{dt.value}' for {symbol}: {message}")
                    elif status == "failed":
                        logger.error(f"❌ Failed to refresh '{dt.value}' for {symbol}: {message}")
                    else:
                        logger.warning(f"⚠️ Skipped '{dt.value}' for {symbol}: {message}")
                    
                    results[symbol]["results"][dt.value] = {
                        "status": status,
                        "message": message
                    }

                # Report any unknown/unmapped data types back to the caller
                for unknown_dt in unknown_types:
                    logger.error(f"❌ Unknown data type '{unknown_dt}' for {symbol}")
                    results[symbol]["results"][unknown_dt] = {
                        "status": "failed",
                        "message": f"Unknown data type: {unknown_dt}"
                    }
                    results[symbol]["total_failed"] += 1

                if result.total_successful > 0:
                    successful_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to refresh {symbol}: {e}")
                results[symbol] = {
                    "success": False,
                    "error": str(e)
                }
                failed_count += 1
        
        resp = RefreshResponse(
            success=successful_count > 0,
            message=f"Refreshed {successful_count}/{len(request.symbols)} symbols successfully",
            results=results,
        )

        try:
            audit.finish_run(run_id, status="success" if resp.success else "failed", metadata={"operation": "refresh"})
        except Exception:
            pass

        return resp
        
    except Exception as e:
        logger.error(f"Failed to refresh data: {e}")
        try:
            audit.log_event(level="error", provider="system", operation="refresh.request_failure", exception=e)
            audit.finish_run(run_id, status="failed", metadata={"operation": "refresh"})
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test/audit-failure")
async def test_audit_failure():
    """Force a failure to verify audit logging captures the exact error reason."""
    try:
        # Simulate a refresh failure with a clear exception
        raise ValueError("Simulated refresh failure: test error for audit logging")
    except Exception as e:
        logger.error("Test audit failure triggered", exc_info=True)
        # Log to audit with full exception/root cause
        try:
            audit.log_event(
                level="error",
                provider="test",
                operation="test.refresh_failure",
                symbol="TESTSYMBOL",
                message="Intentional test failure to verify audit logging",
                exception=e,
                context={"test": True, "data_type": "price_historical"}
            )
        except Exception as audit_err:
            logger.error(f"Failed to write audit event: {audit_err}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/recent")
async def get_recent_signals(limit: int = 50):
    """Get recent trading signals"""
    try:
        # Query recent signals from stock_signals table
        query = """
            SELECT 
                s.symbol,
                ss.signal,
                ss.confidence,
                ss.engine_name,
                ss.created_at
            FROM stock_signals ss
            JOIN stocks s ON ss.stock_id = s.id
            ORDER BY ss.created_at DESC
            LIMIT :limit
        """
        
        results = db.execute_query(query, {"limit": limit})
        
        signals = []
        for row in results:
            signals.append({
                "symbol": row["symbol"],
                "signal": row["signal"],
                "confidence": row["confidence"],
                "strategy": row["engine_name"],
                "timestamp": row["created_at"].isoformat(),
                "price": None  # Would need to join with price data
            })
        
        return {"signals": signals}
        
    except Exception as e:
        logger.error(f"Failed to get recent signals: {e}")
        # If table doesn't exist or schema mismatch, return empty rather than 500
        err_lower = str(e).lower()
        if ("does not exist" in err_lower or "column" in err_lower or "undefinedtable" in err_lower):
            logger.warning("Signals table missing or schema mismatch; returning empty signals")
            return {"signals": []}
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screener/results/{screener_id}")
async def get_screener_results(screener_id: str):
    """Get screener results by ID"""
    try:
        # For now, return mock data
        # In a real implementation, this would query a screener_results table
        return {
            "screener_id": screener_id,
            "status": "completed",
            "created_at": datetime.now().isoformat(),
            "results": [
                {
                    "symbol": "AAPL",
                    "score": 85,
                    "current_price": 173.50,
                    "rsi": 45.2,
                    "sma_50": 175.20
                }
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to get screener results: {e}")
        raise HTTPException(status_code=500, detail=str(e))
