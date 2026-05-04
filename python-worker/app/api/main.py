"""
Main API Endpoints for Trading System
Provides core functionality endpoints
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from uuid import uuid4
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


class TradingDecisionV2RunRequest(BaseModel):
    symbols: List[str]
    as_of_date: Optional[str] = None


class PortfolioTradingDecisionRunRequest(BaseModel):
    portfolio_id: str
    as_of_date: Optional[str] = None
    refresh: bool = False
    data_types: Optional[List[str]] = None
    force: bool = False


class TradingDecisionShadowRunRequest(BaseModel):
    symbols: List[str]
    as_of_date: Optional[str] = None


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


@router.post("/trading-v3/decisions/run")
async def run_trading_decisions_v3(req: TradingDecisionV2RunRequest) -> Dict[str, Any]:
    """Generate and persist EOD trading decisions v3 for given symbols."""
    try:
        from app.services.trading_decision_v3_service import TradingDecisionV3Service

        service = TradingDecisionV3Service()
        decisions = service.run_and_persist(req.symbols, as_of_date=req.as_of_date)

        return {
            "success": True,
            "as_of_date": req.as_of_date,
            "decisions": [
                {
                    "symbol": d.symbol,
                    "as_of_date": d.as_of_date,
                    "state": d.state,
                    "phase": d.phase,
                    "extension": d.extension,
                    "action": d.action,
                    "confidence": d.confidence,
                    "opportunity_score": (d.features or {}).get("opportunity_score"),
                    "volume_context": (d.features or {}).get("volume_context"),
                    "price": d.price,
                    "reasons": d.reasons,
                }
                for d in decisions
            ],
        }
    except Exception as e:
        logger.error(f"Failed to run trading decision v3: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trading-v3/decisions/run-portfolio")
async def run_trading_decisions_v3_for_portfolio(req: PortfolioTradingDecisionRunRequest) -> Dict[str, Any]:
    """Expand symbols from a portfolio, optionally refresh data, then generate and persist v3 decisions."""
    try:
        portfolio_rows = db.execute_query(
            "SELECT id FROM portfolios WHERE id = :portfolio_id",
            {"portfolio_id": req.portfolio_id},
        )
        if not portfolio_rows:
            raise HTTPException(status_code=404, detail="Portfolio not found")

        holding_rows = db.execute_query(
            """
            SELECT DISTINCT s.symbol
            FROM portfolio_positions pp
            JOIN stocks s
              ON pp.stock_id = s.id
            WHERE pp.portfolio_id = :portfolio_id
            """,
            {"portfolio_id": req.portfolio_id},
        )
        symbols = [r.get("symbol") for r in holding_rows if r.get("symbol")]
        if not symbols:
            return {
                "success": True,
                "portfolio_id": req.portfolio_id,
                "as_of_date": req.as_of_date,
                "symbols": [],
                "refresh": {"requested": False, "results": {}},
                "decisions": [],
            }

        refresh_summary: Dict[str, Any] = {"requested": bool(req.refresh), "results": {}}
        if req.refresh:
            refresh_manager = DataRefreshManager()

            # Default: only the minimum set needed for decisions.
            requested_types = req.data_types or ["price_historical", "indicators"]
            data_type_mapping = {
                "price_historical": DataType.PRICE_HISTORICAL,
                "price_current": DataType.PRICE_CURRENT,
                "indicators": DataType.INDICATORS,
                "signals": DataType.SIGNALS,
            }

            resolved_types: List[DataType] = []
            for dt in requested_types:
                if dt in data_type_mapping:
                    resolved_types.append(data_type_mapping[dt])

            for sym in symbols:
                try:
                    result = refresh_manager.refresh_data(sym, resolved_types, force=req.force)
                    refresh_summary["results"][sym] = {
                        "total_requested": result.total_requested,
                        "total_successful": result.total_successful,
                        "total_failed": result.total_failed,
                        "total_skipped": result.total_skipped,
                    }
                except Exception as e:
                    refresh_summary["results"][sym] = {"error": str(e)}

        from app.services.trading_decision_v3_service import TradingDecisionV3Service

        service = TradingDecisionV3Service()
        decisions = service.run_and_persist(symbols, as_of_date=req.as_of_date)

        return {
            "success": True,
            "portfolio_id": req.portfolio_id,
            "as_of_date": req.as_of_date,
            "symbols": symbols,
            "refresh": refresh_summary,
            "decisions": [
                {
                    "symbol": d.symbol,
                    "as_of_date": d.as_of_date,
                    "state": d.state,
                    "phase": d.phase,
                    "extension": d.extension,
                    "action": d.action,
                    "confidence": d.confidence,
                    "opportunity_score": (d.features or {}).get("opportunity_score"),
                    "volume_context": (d.features or {}).get("volume_context"),
                    "price": d.price,
                    "reasons": d.reasons,
                }
                for d in decisions
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to run portfolio trading decision v3: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trading-v2/decisions/run")
async def run_trading_decisions_v2(req: TradingDecisionV2RunRequest) -> Dict[str, Any]:
    """Generate and persist EOD trading decisions (add/add_light/hold/trim/reduce/exit) for given symbols."""
    try:
        from app.services.trading_decision_v2_service import TradingDecisionV2Service

        service = TradingDecisionV2Service()
        decisions = service.run_and_persist(req.symbols, as_of_date=req.as_of_date)

        return {
            "success": True,
            "as_of_date": req.as_of_date,
            "decisions": [
                {
                    "symbol": d.symbol,
                    "as_of_date": d.as_of_date,
                    "state": d.state,
                    "action": d.action,
                    "confidence": d.confidence,
                    "price": d.price,
                    "reasons": d.reasons,
                }
                for d in decisions
            ],
        }
    except Exception as e:
        logger.error(f"Failed to run trading decision v2: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trading-v2/decisions/latest/{symbol}")
async def get_latest_trading_decision_v2(symbol: str) -> Dict[str, Any]:
    """Fetch latest persisted trading decision v2 for a symbol."""
    try:
        from app.services.trading_decision_v2_service import TradingDecisionV2Service

        service = TradingDecisionV2Service()
        row = service.get_latest_decision(symbol)
        return {"success": True, "decision": row}
    except Exception as e:
        logger.error(f"Failed to get latest trading decision v2 for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trading-v3/decisions/latest/{symbol}")
async def get_latest_trading_decision_v3(symbol: str) -> Dict[str, Any]:
    """Fetch latest persisted trading decision v3 for a symbol."""
    try:
        from app.services.trading_decision_v3_service import TradingDecisionV3Service

        service = TradingDecisionV3Service()
        row = service.get_latest_decision(symbol)
        return {"success": True, "decision": row}
    except Exception as e:
        logger.error(f"Failed to get latest trading decision v3 for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trading-v3/decisions/dates")
async def list_trading_decision_v3_dates(limit: int = 60) -> Dict[str, Any]:
    """List recent distinct as_of_date values for persisted trading decision v3 signals."""
    try:
        lim = max(1, min(int(limit), 365))
        rows = db.execute_query(
            """
            SELECT DISTINCT (metadata::jsonb->>'as_of_date') AS as_of_date
            FROM signals
            WHERE signal_type = :signal_type
              AND metadata IS NOT NULL
              AND (metadata::jsonb ? 'as_of_date')
            ORDER BY as_of_date DESC
            LIMIT :limit
            """,
            {"signal_type": "trading_decision_v3", "limit": lim},
        )

        dates = [r.get("as_of_date") for r in rows if r.get("as_of_date")]
        return {"success": True, "dates": dates}
    except Exception as e:
        logger.error(f"Failed to list trading decision v3 dates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trading-v3/decisions/by-date")
async def list_trading_decision_v3_by_date(
    as_of_date: str,
    portfolio_id: Optional[str] = None,
    limit: int = 5000,
) -> Dict[str, Any]:
    """List persisted trading decision v3 decisions for a given as_of_date.

    If portfolio_id is provided, restrict results to symbols currently in that portfolio.
    """
    try:
        if not as_of_date:
            raise HTTPException(status_code=400, detail="as_of_date is required")

        lim = max(1, min(int(limit), 20000))

        symbols_filter: Optional[List[str]] = None
        if portfolio_id:
            holding_rows = db.execute_query(
                """
                SELECT DISTINCT s.symbol
                FROM portfolio_positions pp
                JOIN stocks s
                  ON pp.stock_id = s.id
                WHERE pp.portfolio_id = :portfolio_id
                """,
                {"portfolio_id": portfolio_id},
            )
            symbols_filter = [r.get("symbol") for r in holding_rows if r.get("symbol")]
            if not symbols_filter:
                return {
                    "success": True,
                    "as_of_date": as_of_date,
                    "portfolio_id": portfolio_id,
                    "decisions": [],
                }

        # Pull latest row per symbol for that as_of_date
        rows = db.execute_query(
            """
            SELECT s.symbol,
                   s.confidence,
                   s.price_at_signal,
                   s.timestamp,
                   s.metadata
            FROM signals s
            JOIN (
                SELECT symbol, MAX(timestamp) AS max_ts
                FROM signals
                WHERE signal_type = :signal_type
                  AND (metadata::jsonb->>'as_of_date') = :as_of_date
                GROUP BY symbol
            ) latest
              ON latest.symbol = s.symbol AND latest.max_ts = s.timestamp
            WHERE s.signal_type = :signal_type
              AND (s.metadata::jsonb->>'as_of_date') = :as_of_date
            ORDER BY s.symbol ASC
            LIMIT :limit
            """,
            {
                "signal_type": "trading_decision_v3",
                "as_of_date": as_of_date,
                "limit": lim,
            },
        )

        decisions: List[Dict[str, Any]] = []
        for r in rows:
            sym = r.get("symbol")
            if symbols_filter is not None and sym not in symbols_filter:
                continue

            md = r.get("metadata") or {}
            # db layer may return metadata as string or dict depending on driver
            if isinstance(md, str):
                try:
                    import json

                    md = json.loads(md)
                except Exception:
                    md = {}

            decisions.append(
                {
                    "symbol": sym,
                    "as_of_date": md.get("as_of_date") or as_of_date,
                    "state": md.get("state"),
                    "phase": md.get("phase"),
                    "extension": md.get("extension"),
                    "action": md.get("action"),
                    "confidence": r.get("confidence"),
                    "opportunity_score": ((md.get("features") or {}) if isinstance(md.get("features"), dict) else {}).get(
                        "opportunity_score"
                    ),
                    "volume_context": ((md.get("features") or {}) if isinstance(md.get("features"), dict) else {}).get(
                        "volume_context"
                    ),
                    "price": r.get("price_at_signal"),
                    "reasons": md.get("reasons"),
                    "timestamp": str(r.get("timestamp")) if r.get("timestamp") is not None else None,
                    "metadata": md,
                }
            )

        return {
            "success": True,
            "as_of_date": as_of_date,
            "portfolio_id": portfolio_id,
            "decisions": decisions,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list trading decision v3 by date: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trading/decisions/shadow-run")
async def shadow_run_trading_decisions(req: TradingDecisionShadowRunRequest) -> Dict[str, Any]:
    """Run V2 and V3 decisions side-by-side and return structured diffs for validation."""
    try:
        from app.services.trading_decision_v2_service import TradingDecisionV2Service
        from app.services.trading_decision_v3_service import TradingDecisionV3Service

        v2 = TradingDecisionV2Service()
        v3 = TradingDecisionV3Service()

        out: List[Dict[str, Any]] = []
        for sym in req.symbols:
            d2 = v2.run_for_symbol(sym, as_of_date=req.as_of_date)
            d3 = v3.run_for_symbol(sym, as_of_date=req.as_of_date)

            v2_extension_metrics = v2._compute_extension_metrics(d2.indicators)
            v2_extension_type = v2._classify_extension_type(d2.indicators, v2_extension_metrics, list(d2.reasons or []))
            v2_phase = v2._classify_market_phase(d2.indicators, v2_extension_metrics, list(d2.reasons or []))

            diff: Dict[str, Any] = {}
            for k in ("state", "action"):
                if getattr(d2, k) != getattr(d3, k):
                    diff[k] = {"v2": getattr(d2, k), "v3": getattr(d3, k)}
            if v2_phase != d3.phase:
                diff["phase"] = {"v2": v2_phase, "v3": d3.phase}
            if v2_extension_type != d3.extension:
                diff["extension"] = {"v2": v2_extension_type, "v3": d3.extension}

            out.append(
                {
                    "symbol": sym,
                    "v2": {
                        "state": d2.state,
                        "action": d2.action,
                        "phase": v2_phase,
                        "extension": v2_extension_type,
                        "confidence": d2.confidence,
                        "price": d2.price,
                        "risk": d2.risk,
                    },
                    "v3": {
                        "state": d3.state,
                        "phase": d3.phase,
                        "extension": d3.extension,
                        "action": d3.action,
                        "confidence": d3.confidence,
                        "price": d3.price,
                        "risk": d3.risk,
                    },
                    "diff": diff,
                }
            )

        return {"success": True, "as_of_date": req.as_of_date, "results": out}
    except Exception as e:
        logger.error(f"Failed to shadow-run trading decisions: {e}", exc_info=True)
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
