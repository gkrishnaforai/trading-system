"""
Main API Endpoints for Trading System
Provides core functionality endpoints
"""
from datetime import datetime
import uuid
from uuid import uuid4
from typing import Dict, Any, List, Optional
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
    run_id: Optional[str] = None
    portfolio_id: Optional[str] = None
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
    try:
        run_id = uuid4() if not request.run_id else uuid.UUID(request.run_id)
    except Exception:
        run_id = uuid4()

    set_ingestion_run_id(run_id)
    try:
        try:
            audit.start_run(
                run_id,
                metadata={
                    "operation": "refresh",
                    "symbols": request.symbols,
                    "data_types": request.data_types,
                    "portfolio_id": request.portfolio_id,
                },
            )
            audit.log_event(level="info", provider="system", operation="refresh.request_start")
        except Exception:
            pass

        refresh_manager = DataRefreshManager()
        
        # Convert string data types to DataType enum
        # Updated to include all implemented data types with corresponding database tables
        data_type_mapping = {
            # === MARKET DATA ===
            "price_historical": DataType.PRICE_HISTORICAL,
            "price_current": DataType.PRICE_CURRENT,
            "price_intraday_5m": DataType.PRICE_INTRADAY_5M,  # Updated from 15m to 5m
            
            # === FINANCIAL STATEMENTS ===
            "fundamentals": DataType.FUNDAMENTALS,
            "income_statements": DataType.INCOME_STATEMENTS,
            "balance_sheets": DataType.BALANCE_SHEETS,
            "cash_flow_statements": DataType.CASH_FLOW_STATEMENTS,
            
            # === FINANCIAL METRICS ===
            "indicators": DataType.INDICATORS,
            "financial_ratios": DataType.FINANCIAL_RATIOS,
            
            # === NEWS & EVENTS ===
            "news": DataType.NEWS,
            "earnings": DataType.EARNINGS,
            "industry_peers": DataType.INDUSTRY_PEERS,
            "corporate_actions": DataType.CORPORATE_ACTIONS,
            
            # === ANALYST & GRADING DATA (FMP Primary) ===
            "stock_grades": DataType.STOCK_GRADES,
            "consensus_data": DataType.CONSENSUS_DATA,
            "price_targets": DataType.PRICE_TARGETS,
            
            # === SYSTEM DATA ===
            "signals": DataType.SIGNALS,
            
            # === PARTIALLY IMPLEMENTED (have tables but limited APIs) ===
            # These will be handled with fallback logic
            "analyst_ratings": DataType.ANALYST_RATINGS,
            "ratings_snapshot": DataType.RATINGS_SNAPSHOT,
            "historical_grades": DataType.HISTORICAL_GRADES,
            "earnings_transcripts": DataType.EARNINGS_TRANSCRIPTS,
            "key_metrics_ttm": DataType.KEY_METRICS_TTM,
            "financial_scores": DataType.FINANCIAL_SCORES,
            
            # === NEW DATA TYPES ===
            "institutional_buying": DataType.INSTITUTIONAL_BUYING,  # Added institutional buying
            
            # === GROWTH METRICS ===
            "income_statement_growth": DataType.INCOME_STATEMENT_GROWTH,
            "balance_sheet_growth": DataType.BALANCE_SHEET_GROWTH,
            "cash_flow_growth": DataType.CASH_FLOW_GROWTH,
            "financial_growth": DataType.FINANCIAL_GROWTH,
            
            # === NOT YET IMPLEMENTED (will show warnings) ===
            # These will be marked as unknown until tables/APIs are created
            "short_interest": DataType.SHORT_INTEREST,
            "short_volume": DataType.SHORT_VOLUME,
            "share_float": DataType.SHARE_FLOAT,
            "risk_factors": DataType.RISK_FACTORS,
            "owner_earnings": DataType.OWNER_EARNINGS,
            "reports": DataType.REPORTS,
            "weekly_aggregation": DataType.WEEKLY_AGGREGATION,
            "growth_calculations": DataType.GROWTH_CALCULATIONS
        }
        
        results = {}
        successful_count = 0
        failed_count = 0
        
        for symbol in request.symbols:
            try:
                logger.info(f"Starting refresh for symbol: {symbol}")
                
                # Convert data types with better handling for implementation status
                data_types = []
                unknown_types: List[str] = []
                partially_implemented_types: List[str] = []
                not_implemented_types: List[str] = []
                
                for dt in request.data_types:
                    if dt in data_type_mapping:
                        data_type_enum = data_type_mapping[dt]
                        
                        # Check implementation status and provide appropriate warnings
                        if dt in ["short_interest", "short_volume", "share_float", "risk_factors", 
                                 "owner_earnings", "reports", "weekly_aggregation", "growth_calculations"]:
                            not_implemented_types.append(dt)
                            logger.warning(f"🚧 Data type '{dt}' for {symbol} - NOT YET IMPLEMENTED (no table/API)")
                            # Still add to list so it gets proper error handling
                            data_types.append(data_type_enum)
                        elif dt in ["analyst_ratings", "ratings_snapshot", "historical_grades", 
                                   "earnings_transcripts", "key_metrics_ttm", "financial_scores"]:
                            partially_implemented_types.append(dt)
                            logger.warning(f"⚠️ Data type '{dt}' for {symbol} - PARTIALLY IMPLEMENTED (limited API)")
                            data_types.append(data_type_enum)
                        else:
                            data_types.append(data_type_enum)
                            logger.info(f"✅ Will refresh data type '{dt}' for {symbol}")
                    else:
                        unknown_types.append(dt)
                        logger.error(f"❌ Unknown data type '{dt}' requested for symbol {symbol}")
                
                # Log implementation summary
                if partially_implemented_types:
                    logger.info(f"⚠️ Partially implemented types for {symbol}: {', '.join(partially_implemented_types)}")
                if not_implemented_types:
                    logger.info(f"🚧 Not yet implemented types for {symbol}: {', '.join(not_implemented_types)}")
                if unknown_types:
                    logger.error(f"❌ Unknown types for {symbol}: {', '.join(unknown_types)}")
                
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


@router.get("/data/{symbol}")
async def get_symbol_data(symbol: str, limit: int = 10):
    """Get basic market data for a symbol"""
    try:
        # Get latest intraday data
        intraday_query = """
            SELECT symbol, ts, interval, open, high, low, close, volume, data_source
            FROM raw_market_data_intraday
            WHERE symbol = :symbol
            ORDER BY ts DESC
            LIMIT :limit
        """
        
        intraday_result = db.execute_query(intraday_query, {"symbol": symbol, "limit": limit})
        
        # Get latest daily data if no intraday
        if not intraday_result:
            daily_query = """
                SELECT symbol, date, open, high, low, close, volume
                FROM raw_market_data_daily
                WHERE symbol = :symbol
                ORDER BY date DESC
                LIMIT :limit
            """
            
            daily_result = db.execute_query(daily_query, {"symbol": symbol, "limit": limit})
            
            return {
                "symbol": symbol,
                "data_type": "daily",
                "records": daily_result,
                "count": len(daily_result)
            }
        
        return {
            "symbol": symbol,
            "data_type": "intraday",
            "records": intraday_result,
            "count": len(intraday_result)
        }
        
    except Exception as e:
        logger.error(f"Failed to get data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
