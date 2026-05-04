"""
Admin API endpoints for trading system
Clean version with signal generation and storage
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import json
import uuid
import os

from sqlalchemy import text

from app.database import db
from app.data_management.refresh_manager import DataRefreshManager, DataType
from app.data_management.refresh_result import RefreshStatus
from app.data_management.refresh_strategy import RefreshMode
from app.services.indicator_service import IndicatorService
from app.services.strategy_service import StrategyService
from app.observability import audit
from app.observability.context import set_ingestion_run_id
from app.observability.logging import get_logger

logger = get_logger("admin_api")

# ========================================
# IMPORTANT: Router Configuration Rules
# ========================================
# DO NOT ADD PREFIX HERE! Prefixes are managed in api_server.py
# WRONG: router = APIRouter(prefix="/admin", tags=["admin"])
# CORRECT: router = APIRouter(tags=["admin"])
# ========================================
router = APIRouter(tags=["admin"])

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

class SignalRequest(BaseModel):
    symbols: List[str]
    strategy: str = "technical"
    backtest_date: Optional[str] = None  # Format: "YYYY-MM-DD"

class ScreenerRequest(BaseModel):
    min_rsi: Optional[float] = None
    max_rsi: Optional[float] = None
    min_sma_50: Optional[float] = None
    max_pe_ratio: Optional[float] = None
    limit: int = 100

class StockInsightsRequest(BaseModel):
    symbol: str


class FairValueV2CategoryOverrideRequest(BaseModel):
    symbol: str
    category_override: str
    enabled: bool = True
    reason: Optional[str] = None
    updated_by: Optional[str] = None


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_data(request: RefreshRequest, background_tasks: BackgroundTasks):
    """Trigger data refresh for specific symbols and data types"""
    run_id_str = request.run_id or str(uuid.uuid4())
    run_uuid = uuid.UUID(run_id_str)
    set_ingestion_run_id(run_uuid)
    try:
        try:
            audit.start_run(
                run_uuid,
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
        # Support all DataType enum values by their `.value` strings.
        data_type_mapping = {dt.value: dt for dt in DataType}
        # Backward-compatible alias used by UIs
        data_type_mapping["market_news"] = DataType.NEWS
        
        # Validate data types
        invalid_types = [dt for dt in request.data_types if dt not in data_type_mapping]
        if invalid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid data types: {invalid_types}. Valid types: {list(data_type_mapping.keys())}"
            )
        
        results = {}
        for symbol in request.symbols:
            symbol_results = {}
            try:
                mapped_types = [data_type_mapping[dt] for dt in request.data_types]
                refresh_result = refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=mapped_types,
                    # Use PERIODIC to enable freshness-based skipping and self-healing backfills.
                    # force=True will still override freshness checks.
                    mode=RefreshMode.PERIODIC,
                    force=request.force,
                )

                for dt in request.data_types:
                    dt_key = str(dt)
                    res = (refresh_result.results or {}).get(dt_key)
                    success = bool(res and res.status == RefreshStatus.SUCCESS)
                    msg = res.message if res and getattr(res, "message", None) else (
                        f"Successfully refreshed {dt} for {symbol}" if success else f"Failed to refresh {dt} for {symbol}"
                    )

                    symbol_results[dt] = {
                        "success": success,
                        "message": msg,
                    }

                    audit.log_event(
                        level="info",
                        provider="system",
                        operation="refresh.symbol_complete",
                        context={"symbol": symbol, "data_type": dt, "success": success}
                    )
            except Exception as e:
                logger.error(f"Failed to refresh data for {symbol}: {e}")
                for dt in request.data_types:
                    symbol_results[dt] = {
                        "success": False,
                        "message": f"Error refreshing {dt} for {symbol}: {str(e)}",
                    }
            
            results[symbol] = symbol_results
        
        audit.finish_run(run_uuid, status="completed", metadata={"results": results})
        
        return RefreshResponse(
            success=True,
            message=f"Data refresh completed for {len(request.symbols)} symbols",
            results=results
        )
        
    except Exception as e:
        logger.error(f"Data refresh failed: {e}")
        try:
            audit.finish_run(run_uuid, status="failed", metadata={"error": str(e)})
        except Exception:
            pass
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
                # Get historical price data for the symbol up to the backtest date FIRST
                historical_data = []
                try:
                    # Query database directly for historical data up to backtest date
                    from app.database import db
                    
                    query = """
                        SELECT date, open, high, low, close, volume
                        FROM raw_market_data_daily 
                        WHERE symbol = :symbol AND date <= :backtest_date
                        ORDER BY date DESC
                        LIMIT 60
                    """
                    
                    result = db.execute_query(query, {
                        "symbol": symbol,
                        "backtest_date": request.backtest_date
                    })
                    
                    if result:
                        historical_data = result
                        logger.info(f"📊 Found {len(historical_data)} records for {symbol} up to {request.backtest_date}")
                    else:
                        logger.warning(f"⚠️ No historical data found for {symbol} up to {request.backtest_date}")
                        
                except Exception as e:
                    logger.error(f"❌ Error getting historical data: {e}")
                
                # Use backtest_date as timestamp if provided, otherwise use current time
                timestamp = request.backtest_date + "T23:59:59" if request.backtest_date else datetime.now().isoformat()
                
                # Ensure indicators are calculated
                indicator_service.calculate_indicators(symbol)
                
                # Get indicators for specific date (or latest if no date provided)
                from app.database import db
                
                try:
                    if request.backtest_date:
                        # For historical backtesting, get indicators as of the specified date
                        # Use helper function for backtesting indicators
                        from app.utils.indicators_query_helper import get_backtest_indicators_query
                        
                        query = get_backtest_indicators_query(symbol)
                        indicators_data = db.execute_query(query, {
                            "symbol": symbol, 
                            "backtest_date": request.backtest_date
                        })
                        
                        # Log the query result
                        logger.info(f"Query indicators for {symbol} up to {request.backtest_date}: {len(indicators_data) if indicators_data else 0} results")
                        
                        if indicators_data:
                            indicators = indicators_data[0]
                            logger.info(f"Found indicators for {symbol}: {list(indicators.keys())}")
                        else:
                            # Check if any indicators exist for this symbol at all
                            count_query = """
                                SELECT COUNT(*) as total, MAX(date) as latest_date
                                FROM indicators_daily 
                                WHERE symbol = :symbol
                            """
                            count_result = db.execute_query(count_query, {"symbol": symbol})
                            
                            if count_result:
                                count_info = count_result[0]
                                if count_info['total'] == 0:
                                    error_msg = f"No indicators found for {symbol} in database. Tables may be empty or symbol not tracked."
                                else:
                                    error_msg = f"No indicators found for {symbol} on or before {request.backtest_date}. Latest available: {count_info['latest_date']}. Try a later date."
                            else:
                                error_msg = f"Failed to check indicator availability for {symbol}. Database query error."
                            
                            logger.error(error_msg)
                            results.append({
                                "symbol": symbol,
                                "signal": "hold",
                                "confidence": 0.0,
                                "strategy": request.strategy,
                                "error": error_msg
                            })
                            continue
                    else:
                        # Get latest indicators
                        # Use helper function for latest indicators
                        from app.utils.indicators_query_helper import get_latest_indicators_query
                        
                        query = get_latest_indicators_query(symbol)
                        indicators_data = db.execute_query(query, {"symbol": symbol})
                        
                        if indicators_data:
                            indicators = indicators_data[0]
                        else:
                            error_msg = f"No indicators found for {symbol}. Symbol may not be tracked in indicators_daily table."
                            logger.error(error_msg)
                            results.append({
                                "symbol": symbol,
                                "signal": "hold",
                                "confidence": 0.0,
                                "strategy": request.strategy,
                                "error": error_msg
                            })
                            continue
                            
                except Exception as db_error:
                    error_msg = f"Database error while fetching indicators for {symbol}: {str(db_error)}"
                    logger.error(error_msg)
                    results.append({
                        "symbol": symbol,
                        "signal": "hold",
                        "confidence": 0.0,
                        "strategy": request.strategy,
                        "error": error_msg
                    })
                    continue
                
                if indicators:
                    # Add required fields for strategy
                    indicators["price"] = indicators.get("sma_50", 0)
                    indicators["ema20"] = indicators.get("ema_20", 0)
                    indicators["ema50"] = indicators.get("sma_50", 0)
                    indicators["sma200"] = indicators.get("sma_200", 0)
                    indicators["macd_line"] = indicators.get("macd", 0)
                    indicators["rsi"] = indicators.get("rsi_14", 50)
                    
                    # Generate signal using signal engines with proper error handling
                    from app.signal_engines.base import EngineTier, MarketContext
                    from app.signal_engines.tqqq_swing_engine import TQQQSwingEngine
                    from app.signal_engines.generic_swing_engine import GenericSwingEngine
                    
                    # Validate we have sufficient historical data
                    if len(historical_data) < 50:
                        results.append({
                            "symbol": symbol,
                            "signal": "hold",
                            "confidence": 0.0,
                            "strategy": request.strategy,
                            "timestamp": timestamp,
                            "error": f"Insufficient historical data: {len(historical_data)} records (minimum 50 required for backtest date {request.backtest_date})"
                        })
                        continue
                    
                    # Validate data quality
                    if not historical_data[-1].get('close') or historical_data[-1]['close'] <= 0:
                        results.append({
                            "symbol": symbol,
                            "signal": "hold",
                            "confidence": 0.0,
                            "strategy": request.strategy,
                            "timestamp": timestamp,
                            "error": f"Invalid price data: close price is {historical_data[-1].get('close')} for {request.backtest_date}"
                        })
                        continue
                    
                    # Create market context
                    from app.signal_engines.base import MarketRegime
                    context = MarketContext(
                        regime=MarketRegime.NO_TRADE,
                        regime_confidence=0.5,
                        vix=20.0,  # Default VIX
                        nasdaq_trend="neutral"
                    )
                    
                    # Create mock price data for the engine with historical context
                    import pandas as pd
                    import numpy as np
                    from datetime import datetime, timedelta
                    
                    # Get historical price data for the symbol up to the backtest date
                    historical_data = []
                    try:
                        # Query database directly for historical data up to backtest date
                        from app.database import db
                        
                        query = """
                            SELECT date, open, high, low, close, volume
                            FROM raw_market_data_daily 
                            WHERE symbol = :symbol AND date <= :backtest_date
                            ORDER BY date DESC
                            LIMIT 60
                        """
                        
                        result = db.execute_query(query, {
                            "symbol": symbol,
                            "backtest_date": request.backtest_date
                        })
                        
                        if result:
                            historical_data = result
                            print(f"📊 Found {len(historical_data)} records for {symbol} up to {request.backtest_date}")
                        else:
                            print(f"⚠️ No historical data found for {symbol} up to {request.backtest_date}")
                            
                    except Exception as e:
                        print(f"❌ Error getting historical data: {e}")
                        pass
                    
                    # If no historical data, create synthetic data
                    if not historical_data:
                        base_price = indicators.get('price', indicators.get('sma_50', 50))
                        dates = []
                        prices = []
                        
                        # Generate 60 days of synthetic data
                        for i in range(60):
                            date = (datetime.strptime(request.backtest_date, "%Y-%m-%d") - timedelta(days=60-i)).date()
                            # Add some realistic price movement
                            price_change = np.random.normal(0, 0.02)  # 2% daily volatility
                            if i == 0:
                                price = base_price
                            else:
                                price = prices[-1] * (1 + price_change)
                            
                            dates.append(date)
                            prices.append(price)
                        
                        # Create synthetic historical data
                        historical_data = []
                        for i, (date, price) in enumerate(zip(dates, prices)):
                            historical_data.append({
                                'date': date,
                                'open': price * 0.998,
                                'high': price * 1.02,
                                'low': price * 0.98,
                                'close': price,
                                'volume': 1000000 + int(np.random.normal(0, 200000))
                            })
                    
                    # Convert to DataFrame and add indicators
                    price_df = pd.DataFrame(historical_data)
                    price_df['date'] = pd.to_datetime(price_df['date'])
                    price_df.set_index('date', inplace=True)
                    
                    # Add technical indicators
                    price_df['sma_20'] = price_df['close'].rolling(window=20).mean()
                    price_df['sma_50'] = price_df['close'].rolling(window=50).mean()
                    price_df['sma_200'] = price_df['close'].rolling(window=min(200, len(price_df))).mean()
                    price_df['ema_20'] = price_df['close'].ewm(span=20).mean()
                    
                    # Calculate RSI
                    delta = price_df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    price_df['rsi'] = 100 - (100 / (1 + rs))
                    
                    # Calculate MACD
                    exp1 = price_df['close'].ewm(span=12).mean()
                    exp2 = price_df['close'].ewm(span=26).mean()
                    price_df['macd'] = exp1 - exp2
                    price_df['macd_signal'] = price_df['macd'].ewm(span=9).mean()
                    
                    # Calculate ATR
                    high_low = price_df['high'] - price_df['low']
                    high_close = np.abs(price_df['high'] - price_df['close'].shift())
                    low_close = np.abs(price_df['low'] - price_df['close'].shift())
                    ranges = pd.concat([high_low, high_close, low_close], axis=1)
                    true_range = ranges.max(axis=1)
                    price_df['atr'] = true_range.rolling(window=14).mean()
                    
                    # Fill NaN values with the most recent valid values
                    price_df = price_df.fillna(method='bfill').fillna(method='ffill')
                    
                    # Ensure the last row matches our current indicators
                    last_row = len(price_df) - 1
                    price_df.iloc[last_row, price_df.columns.get_loc('sma_20')] = indicators.get('ema20', indicators.get('sma_50', 0))
                    price_df.iloc[last_row, price_df.columns.get_loc('sma_50')] = indicators.get('sma_50', 0)
                    price_df.iloc[last_row, price_df.columns.get_loc('sma_200')] = indicators.get('sma_200', 0)
                    price_df.iloc[last_row, price_df.columns.get_loc('ema_20')] = indicators.get('ema20', indicators.get('sma_50', 0))
                    price_df.iloc[last_row, price_df.columns.get_loc('rsi')] = indicators.get('rsi', 50)
                    price_df.iloc[last_row, price_df.columns.get_loc('macd')] = indicators.get('macd_line', 0)
                    price_df.iloc[last_row, price_df.columns.get_loc('macd_signal')] = indicators.get('macd_signal', 0)
                    
                    price_data = price_df
                    
                    # Select the appropriate engine with validation
                    try:
                        if request.strategy == "tqqq_swing":
                            if symbol == "TQQQ":
                                # Try TQQQ engine first, but fallback to generic if VIX data missing
                                try:
                                    engine = TQQQSwingEngine()
                                    signal_result = engine.generate_signal(symbol, price_data, context)
                                    
                                    # Validate signal result
                                    if not hasattr(signal_result, 'signal') or not hasattr(signal_result, 'confidence'):
                                        raise ValueError("Invalid signal result from TQQQ engine")
                                    
                                    # If TQQQ engine returns HOLD due to missing data, use generic
                                    if (signal_result.signal.value == 'HOLD' and 
                                        signal_result.confidence < 0.2 and
                                        any('Missing required' in str(r) for r in signal_result.reasoning)):
                                        engine = GenericSwingEngine()
                                        signal_result = engine.generate_signal(symbol, price_data, context)
                                        
                                except Exception as tqqq_error:
                                    # Fallback to generic if TQQQ engine fails
                                    engine = GenericSwingEngine()
                                    signal_result = engine.generate_signal(symbol, price_data, context)
                                    print(f"⚠️ TQQQ engine failed, using generic: {tqqq_error}")
                            else:
                                # Non-TQQQ symbols use generic
                                engine = GenericSwingEngine()
                                signal_result = engine.generate_signal(symbol, price_data, context)
                        elif request.strategy == "generic_swing":
                            engine = GenericSwingEngine()
                            signal_result = engine.generate_signal(symbol, price_data, context)
                        else:
                            # Default to generic
                            engine = GenericSwingEngine()
                            signal_result = engine.generate_signal(symbol, price_data, context)
                        
                        # Validate final signal result
                        if not hasattr(signal_result, 'signal') or not hasattr(signal_result, 'confidence'):
                            raise ValueError(f"Invalid signal result from {engine.name}")
                        
                        if signal_result.confidence < 0 or signal_result.confidence > 1:
                            raise ValueError(f"Invalid confidence value: {signal_result.confidence}")
                        
                    except Exception as engine_error:
                        results.append({
                            "symbol": symbol,
                            "signal": "hold",
                            "confidence": 0.0,
                            "strategy": request.strategy,
                            "timestamp": timestamp,
                            "error": f"Signal generation failed: {str(engine_error)}"
                        })
                        continue
                    
                    # Store signal in database
                    from app.signal_storage import store_signal_in_database
                    
                    signal_data = {
                        "symbol": symbol,
                        "signal": signal_result.signal.value if hasattr(signal_result, 'signal') else "hold",
                        "confidence": signal_result.confidence if hasattr(signal_result, 'confidence') else 0.5,
                        "strategy": request.strategy,
                        "timestamp": timestamp,
                        "reason": " | ".join(signal_result.reasoning) if hasattr(signal_result, 'reasoning') and signal_result.reasoning else "No reasoning available",
                        "price_at_signal": indicators.get('price', indicators.get('sma_50', 0))
                    }
                    
                    await store_signal_in_database(signal_data, indicators, request.backtest_date)
                    
                    results.append(signal_data)
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
        logger.error(f"Signal generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/recent")
async def get_recent_signals(limit: int = 20):
    """Get recent trading signals from database"""
    try:
        from app.signal_storage import get_recent_signals
        return await get_recent_signals(limit)
        
    except Exception as e:
        logger.error(f"Failed to get recent signals: {e}")
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
        
        return {
            "success": True,
            "results": result,
            "total_found": len(result) if result else 0
        }
        
    except Exception as e:
        logger.error(f"Screener failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/insights/strategies")
async def get_strategy_insights():
    """Get insights for all strategies"""
    try:
        insights_service = StockInsightsService()
        
        # Get strategy overview (this is a placeholder - implement as needed)
        strategies_overview = {
            "available_strategies": [
                "technical_momentum",
                "technical_mean_reversion", 
                "fundamental_value",
                "sector_rotation"
            ],
            "active_strategies": 4,
            "total_signals_generated": 0,  # Would be calculated from database
            "success_rate": 0.0,  # Would be calculated from database
            "last_updated": datetime.now().isoformat()
        }
        
        return {
            "strategies": strategies_overview,
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get insights for strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/insights/{symbol}")
async def get_stock_insights(symbol: str):
    """Get comprehensive stock insights"""
    try:
        insights_service = StockInsightsService()
        
        insights = insights_service.get_stock_insights(symbol)
        
        return {
            "symbol": symbol,
            "insights": insights,
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get insights for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-summary/{table}")
async def get_data_summary(table: str):
    """Get data summary for a specific table"""
    try:
        def _table_exists(table_name: str) -> bool:
            try:
                rows = db.execute_query(
                    "SELECT to_regclass(:tbl) as regclass",
                    {"tbl": f"public.{table_name}"},
                )
                if not rows:
                    return False
                return rows[0].get("regclass") is not None
            except Exception:
                return False

        def _pick_existing_column(table_name: str, candidates: list[str]) -> str | None:
            if not candidates:
                return None
            in_list = ",".join([f"'{c}'" for c in candidates])
            rows = db.execute_query(
                f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = '{table_name}'
                  AND column_name IN ({in_list})
                """
            )
            if not rows:
                return None
            present = {r.get("column_name") for r in rows}
            for c in candidates:
                if c in present:
                    return c
            return None

        # Validate table name
        valid_tables = [
            "raw_market_data_daily", "raw_market_data_intraday", "indicators_daily",
            "fundamentals_snapshots", "industry_peers", "market_news", "earnings_data",
            "macro_market_data", "stocks", "data_ingestion_runs", "data_ingestion_events",
            "stock_grades", "stock_consensus_history", "analyst_firm_rankings", 
            "grade_changes", "grade_change_events", "rating_change_log",
            "financial_ratios", "financial_statements", "income_statements", 
            "balance_sheets", "cash_flow_statements", "corporate_actions",
            "fmp_company_profiles", "fmp_market_news", "fmp_real_time_prices",
            "earnings_transcripts", "short_interest", "short_volume", "share_float", "risk_factors",
            "key_metrics_ttm", "financial_scores",
        ]
        
        if table not in valid_tables:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid table: {table}. Valid tables: {valid_tables}"
            )

        if not _table_exists(table):
            raise HTTPException(
                status_code=404,
                detail=f"Table not found in database: {table}. This usually means your DB schema is older and does not include this data source.",
            )
        
        # Get summary from database - handle different column structures
        if table == "macro_market_data":
            # Use data_date instead of created_at for macro data
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(data_date) = CURRENT_DATE) as today_records,
                    MAX(data_date) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "raw_market_data_intraday":
            # Use symbol and ts for intraday data
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(ts) = CURRENT_DATE) as today_records,
                    MAX(ts) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "earnings_data":
            # Use earnings_date instead of created_at for earnings_data
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(earnings_date) = CURRENT_DATE) as today_records,
                    MAX(earnings_date) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "market_news":
            # Use published_at instead of created_at for market_news
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(published_at) = CURRENT_DATE) as today_records,
                    MAX(published_at) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "fundamentals_snapshots":
            # Use as_of_date instead of created_at for fundamentals_snapshots
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(as_of_date) = CURRENT_DATE) as today_records,
                    MAX(as_of_date) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "stock_grades":
            # Use grade_date instead of created_at for stock_grades
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(grade_date) = CURRENT_DATE) as today_records,
                    MAX(grade_date) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "stock_consensus_history":
            date_column = _pick_existing_column(table, ["consensus_date", "recorded_at", "created_at"])
            if not date_column:
                date_column = _pick_existing_column(table, ["updated_at"])

            if not date_column:
                query = f"""
                    SELECT 
                        '{table}' as table_name,
                        COUNT(*) as total_records,
                        0 as today_records,
                        NULL as last_updated,
                        pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                        (
                            SELECT COUNT(*) 
                            FROM information_schema.columns 
                            WHERE table_name = '{table}'
                        ) as column_count
                    FROM {table}
                """
            else:
                query = f"""
                    SELECT 
                        '{table}' as table_name,
                        COUNT(*) as total_records,
                        COUNT(*) FILTER (WHERE DATE({date_column}) = CURRENT_DATE) as today_records,
                        MAX({date_column}) as last_updated,
                        pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                        (
                            SELECT COUNT(*) 
                            FROM information_schema.columns 
                            WHERE table_name = '{table}'
                        ) as column_count
                    FROM {table}
                """
        elif table in ["key_metrics_ttm", "financial_scores"]:
            date_column = _pick_existing_column(table, ["date", "as_of_date", "created_at", "updated_at"])
            if not date_column:
                query = f"""
                    SELECT 
                        '{table}' as table_name,
                        COUNT(*) as total_records,
                        0 as today_records,
                        NULL as last_updated,
                        pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                        (
                            SELECT COUNT(*) 
                            FROM information_schema.columns 
                            WHERE table_name = '{table}'
                        ) as column_count
                    FROM {table}
                """
            else:
                query = f"""
                    SELECT 
                        '{table}' as table_name,
                        COUNT(*) as total_records,
                        COUNT(*) FILTER (WHERE DATE({date_column}) = CURRENT_DATE) as today_records,
                        MAX({date_column}) as last_updated,
                        pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                        (
                            SELECT COUNT(*) 
                            FROM information_schema.columns 
                            WHERE table_name = '{table}'
                        ) as column_count
                    FROM {table}
                """
        elif table in ["income_statements", "balance_sheets", "cash_flow_statements"]:
            date_column = _pick_existing_column(
                table,
                [
                    "fiscal_date_or_period",
                    "fiscal_date_ending",
                    "date",
                    "period",
                    "report_date",
                    "created_at",
                ],
            )

            if not date_column:
                query = f"""
                    SELECT 
                        '{table}' as table_name,
                        COUNT(*) as total_records,
                        0 as today_records,
                        NULL as last_updated,
                        pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                        (
                            SELECT COUNT(*) 
                            FROM information_schema.columns 
                            WHERE table_name = '{table}'
                        ) as column_count
                    FROM {table}
                """
            else:
                query = f"""
                    SELECT 
                        '{table}' as table_name,
                        COUNT(*) as total_records,
                        COUNT(*) FILTER (WHERE DATE({date_column}) = CURRENT_DATE) as today_records,
                        MAX({date_column}) as last_updated,
                        pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                        (
                            SELECT COUNT(*) 
                            FROM information_schema.columns 
                            WHERE table_name = '{table}'
                        ) as column_count
                    FROM {table}
                """
        elif table == "corporate_actions":
            # Use action_date instead of created_at for corporate_actions
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(action_date) = CURRENT_DATE) as today_records,
                    MAX(action_date) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "financial_ratios":
            # Use fiscal_date_ending instead of created_at for financial_ratios
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(fiscal_date_ending) = CURRENT_DATE) as today_records,
                    MAX(fiscal_date_ending) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "fmp_market_news":
            # Use published_date instead of created_at for fmp_market_news
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(published_date) = CURRENT_DATE) as today_records,
                    MAX(published_date) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "stocks":
            # Use updated_at for stocks table (master reference table)
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE is_active = true) as today_records,
                    MAX(updated_at) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "data_ingestion_events":
            # Use created_at for data_ingestion_events (no date column)
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                    MAX(created_at) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "share_float":
            # Use float_date for share_float table
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(float_date) = CURRENT_DATE) as today_records,
                    MAX(float_date) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "risk_factors":
            # Use created_at for risk_factors table (no specific date column)
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                    MAX(created_at) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "short_interest":
            # Use short_interest_date for short_interest table
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(short_interest_date) = CURRENT_DATE) as today_records,
                    MAX(short_interest_date) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "short_volume":
            # Use short_volume_date for short_volume table
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(short_volume_date) = CURRENT_DATE) as today_records,
                    MAX(short_volume_date) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "corporate_actions":
            # Use action_date for corporate_actions table
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(action_date) = CURRENT_DATE) as today_records,
                    MAX(action_date) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "stock_grades":
            # Use grade_date for stock_grades table
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(grade_date) = CURRENT_DATE) as today_records,
                    MAX(grade_date) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "stock_consensus_history":
            # Use recorded_at for stock_consensus_history table (no date column)
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(recorded_at) = CURRENT_DATE) as today_records,
                    MAX(recorded_at) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table in ["income_statements", "balance_sheets", "cash_flow_statements", "financial_ratios"]:
            # Use fiscal_date_ending for financial statement tables
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(fiscal_date_ending) = CURRENT_DATE) as today_records,
                    MAX(fiscal_date_ending) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        elif table == "earnings_transcripts":
            # Use transcript_date for earnings_transcripts table
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(transcript_date) = CURRENT_DATE) as today_records,
                    MAX(transcript_date) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        else:
            # Standard query for tables with created_at
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                    MAX(created_at) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            """
        
        result = db.execute_query(query)
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Table {table} not found")
        
        row = result[0]
        
        # Get quality metrics if available - handle different column names per table
        if table == "fundamentals_snapshots":
            # Use symbol and as_of_date for fundamentals_snapshots
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL AND as_of_date IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND as_of_date IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || as_of_date) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as duplicate_rate
                FROM {table}
            """
        elif table == "raw_market_data_intraday":
            # Use symbol and ts for intraday data
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL AND ts IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND ts IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    0.0 as duplicate_rate
                FROM {table}
            """
        elif table == "industry_peers":
            # Use symbol and peer_symbol
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL AND peer_symbol IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND peer_symbol IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || peer_symbol) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as duplicate_rate
                FROM {table}
            """
        elif table == "market_news":
            # No symbol/date columns, skip quality check
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) as non_null_rows,
                    0.0 as null_rate,
                    0.0 as duplicate_rate
                FROM {table}
            """
        elif table == "raw_market_data_intraday":
            # Use symbol and ts for intraday data
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL AND ts IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND ts IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    0.0 as duplicate_rate
                FROM {table}
            """
        elif table == "earnings_data":
            # Use stock_symbol and earnings_date for earnings_data (still has old naming)
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE stock_symbol IS NOT NULL AND earnings_date IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE stock_symbol IS NOT NULL AND earnings_date IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT stock_symbol || earnings_date) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as duplicate_rate
                FROM {table}
            """
        elif table == "macro_market_data":
            # Use data_date for macro data
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE data_date IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE data_date IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT data_date) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as duplicate_rate
                FROM {table}
            """
        elif table == "stocks":
            # Use symbol only for stocks table (master reference table, no date column)
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    0.0 as duplicate_rate
                FROM {table}
            """
        elif table == "data_ingestion_events":
            # Use symbol only for data_ingestion_events (no date column for quality)
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    0.0 as duplicate_rate
                FROM {table}
            """
        elif table == "share_float":
            # Use symbol and float_date for share_float table
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL AND float_date IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND float_date IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || float_date) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as duplicate_rate
                FROM {table}
            """
        elif table == "risk_factors":
            # Use symbol and risk_date for risk_factors table
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL AND risk_date IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND risk_date IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || risk_date) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as duplicate_rate
                FROM {table}
            """
        elif table == "short_interest":
            # Use symbol and short_interest_date for short_interest table
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL AND short_interest_date IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND short_interest_date IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || short_interest_date) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as duplicate_rate
                FROM {table}
            """
        elif table == "short_volume":
            # Use symbol and short_volume_date for short_volume table
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL AND short_volume_date IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND short_volume_date IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || short_volume_date) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as duplicate_rate
                FROM {table}
            """
        elif table == "corporate_actions":
            # Use stock_symbol and action_date for corporate_actions table
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE stock_symbol IS NOT NULL AND action_date IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE stock_symbol IS NOT NULL AND action_date IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT stock_symbol || action_date) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as duplicate_rate
                FROM {table}
            """
        elif table == "stock_grades":
            # Use symbol and grade_date for stock_grades table
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL AND grade_date IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND grade_date IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || grade_date) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as duplicate_rate
                FROM {table}
            """
        elif table == "stock_consensus_history":
            # Use symbol only for stock_consensus_history (no date column for quality)
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    0.0 as duplicate_rate
                FROM {table}
            """
        elif table in ["income_statements", "balance_sheets", "cash_flow_statements", "financial_ratios"]:
            # Use symbol and fiscal_date_ending for financial statement tables
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL AND fiscal_date_ending IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND fiscal_date_ending IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || fiscal_date_ending) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as duplicate_rate
                FROM {table}
            """
        elif table == "earnings_transcripts":
            # Use symbol and transcript_date for earnings_transcripts table
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL AND transcript_date IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND transcript_date IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || transcript_date) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as duplicate_rate
                FROM {table}
            """
        elif table == "rating_change_log":
            date_column = _pick_existing_column(
                table,
                [
                    "event_date",
                    "change_date",
                    "rating_date",
                    "date",
                    "created_at",
                    "updated_at",
                ],
            )

            if not date_column:
                quality_query = f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE symbol IS NOT NULL) as non_null_rows,
                        CASE 
                            WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL) * 100.0 / COUNT(*)
                            ELSE 0.0 
                        END as null_rate,
                        0.0 as duplicate_rate
                    FROM {table}
                """
            else:
                quality_query = f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE symbol IS NOT NULL AND {date_column} IS NOT NULL) as non_null_rows,
                        CASE 
                            WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND {date_column} IS NOT NULL) * 100.0 / COUNT(*)
                            ELSE 0.0 
                        END as null_rate,
                        CASE 
                            WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || {date_column}) * 100.0 / COUNT(*)
                            ELSE 0.0 
                        END as duplicate_rate
                    FROM {table}
                """
        else:
            # Use symbol and date for standard tables (raw_market_data_daily, indicators_daily)
            date_column = _pick_existing_column(table, ["date", "created_at", "updated_at", "ts"]) 
            if not date_column:
                quality_query = f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE symbol IS NOT NULL) as non_null_rows,
                        CASE 
                            WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL) * 100.0 / COUNT(*)
                            ELSE 0.0 
                        END as null_rate,
                        0.0 as duplicate_rate
                    FROM {table}
                """
            else:
                quality_query = f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE symbol IS NOT NULL AND {date_column} IS NOT NULL) as non_null_rows,
                        CASE 
                            WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND {date_column} IS NOT NULL) * 100.0 / COUNT(*)
                            ELSE 0.0 
                        END as null_rate,
                        CASE 
                            WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || {date_column}) * 100.0 / COUNT(*)
                            ELSE 0.0 
                        END as duplicate_rate
                    FROM {table}
                """
        
        quality_result = db.execute_query(quality_query)
        quality = quality_result[0] if quality_result else {}
        
        return {
            "table_name": row["table_name"],
            "total_records": row["total_records"],
            "today_records": row["today_records"],
            "last_updated": row["last_updated"],
            "size_gb": row["size_gb"],
            "column_count": row["column_count"],
            "quality_metrics": {
                "null_rate": float(quality.get("null_rate", 0.0)),
                "duplicate_rate": float(quality.get("duplicate_rate", 0.0)),
                "quality_score": 1.0 - (float(quality.get("null_rate", 0.0)) + float(quality.get("duplicate_rate", 0.0))),
                "null_rows": quality.get("total", 0) - quality.get("non_null_rows", 0),
                "total": quality.get("total", 0)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get data summary for {table}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fair-value-v2/category-overrides/ensure-table")
async def ensure_fair_value_v2_category_overrides_table():
    """Create the fair_value_v2_category_overrides table if it doesn't exist."""
    try:
        with db.get_session() as session:
            session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS fair_value_v2_category_overrides (
                        symbol VARCHAR(10) PRIMARY KEY,
                        category_override VARCHAR(50) NOT NULL,
                        enabled BOOLEAN NOT NULL DEFAULT TRUE,
                        reason TEXT,
                        updated_by VARCHAR(100),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );

                    CREATE INDEX IF NOT EXISTS idx_fv2_cat_overrides_enabled
                        ON fair_value_v2_category_overrides(enabled);

                    CREATE INDEX IF NOT EXISTS idx_fv2_cat_overrides_category
                        ON fair_value_v2_category_overrides(category_override);
                    """
                )
            )
            session.commit()
        return {"success": True, "message": "✅ fair_value_v2_category_overrides ensured"}
    except Exception as e:
        logger.error(f"Failed to ensure fair_value_v2_category_overrides table: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fair-value-v2/category-overrides")
async def list_fair_value_v2_category_overrides(enabled_only: bool = True):
    """List Fair Value V2 category overrides."""
    try:
        where = "WHERE enabled = TRUE" if enabled_only else ""
        rows = db.execute_query(
            f"""
            SELECT symbol, category_override, enabled, reason, updated_by, created_at, updated_at
            FROM fair_value_v2_category_overrides
            {where}
            ORDER BY updated_at DESC
            """
        )
        return {"success": True, "overrides": rows or []}
    except Exception as e:
        logger.error(f"Failed to list fair value v2 category overrides: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fair-value-v2/category-overrides")
async def upsert_fair_value_v2_category_override(req: FairValueV2CategoryOverrideRequest):
    """Upsert a Fair Value V2 category override."""
    try:
        from app.fair_value_v2.feature_store.postgres_point_in_time import PostgresPointInTimeFeatureStore

        store = PostgresPointInTimeFeatureStore()
        store.upsert_category_override(
            symbol=req.symbol.strip().upper(),
            category_override=req.category_override.strip(),
            enabled=bool(req.enabled),
            reason=req.reason,
            updated_by=req.updated_by,
        )
        return {"success": True, "message": "✅ category override upserted", "symbol": req.symbol.strip().upper()}
    except Exception as e:
        logger.error(f"Failed to upsert fair value v2 category override: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fair-value-v2/category-overrides/{symbol}/disable")
async def disable_fair_value_v2_category_override(symbol: str, updated_by: Optional[str] = None):
    """Disable an override (soft delete)."""
    try:
        from app.fair_value_v2.feature_store.postgres_point_in_time import PostgresPointInTimeFeatureStore

        store = PostgresPointInTimeFeatureStore()
        store.disable_category_override(symbol.strip().upper(), updated_by=updated_by)
        return {"success": True, "message": "✅ category override disabled", "symbol": symbol.strip().upper()}
    except Exception as e:
        logger.error(f"Failed to disable fair value v2 category override: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/earnings-calendar")
async def get_earnings_calendar(start_date: str = None, end_date: str = None):
    """Get earnings calendar data"""
    try:
        from datetime import datetime
        from app.repositories.earnings_calendar_repository import EarningsCalendarRepository
        
        # Parse dates or use defaults
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        else:
            start_dt = datetime.now().date()
        
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        else:
            from datetime import timedelta
            end_dt = start_dt + timedelta(days=30)
        
        # Get earnings data
        earnings_data = EarningsCalendarRepository.fetch_earnings_by_date_range(start_dt, end_dt)
        
        return {
            "success": True,
            "start_date": start_date,
            "end_date": end_date,
            "count": len(earnings_data),
            "data": earnings_data
        }
        
    except Exception as e:
        logger.error(f"Failed to get earnings calendar: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-logs")
async def get_audit_logs(start_date: str = None, end_date: str = None, level: str = "ALL", limit: int = 20):
    """Get audit logs"""
    try:
        from datetime import datetime
        
        # Parse dates
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end_dt = datetime.now()
        
        # Query audit logs (basic implementation)
        query = """
            SELECT 
                run_id,
                level,
                provider,
                operation,
                event_ts as timestamp,
                message,
                context as metadata
            FROM data_ingestion_events
            WHERE event_ts BETWEEN :start_date AND :end_date
            AND (:level = 'ALL' OR level = :level)
            ORDER BY event_ts DESC
            LIMIT :limit
        """
        
        try:
            result = db.execute_query(query, {
                "start_date": start_dt,
                "end_date": end_dt,
                "level": level,
                "limit": limit
            })
            
            return {
                "success": True,
                "start_date": start_date,
                "end_date": end_date,
                "level": level,
                "limit": limit,
                "count": len(result),
                "logs": result
            }
        except Exception as e:
            # If table doesn't exist, return empty result
            return {
                "success": True,
                "start_date": start_date,
                "end_date": end_date,
                "level": level,
                "limit": limit,
                "count": 0,
                "logs": [],
                "note": "Audit logs table not available"
            }
        
    except Exception as e:
        logger.error(f"Failed to get audit logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-ingestion-runs")
async def get_data_ingestion_runs(limit: int = 50, status: str = None):
    """Get data ingestion runs with detailed information"""
    try:
        # Build query with optional status filter
        status_filter = ""
        params = {"limit": limit}
        
        if status and status != "ALL":
            status_filter = "WHERE status = :status"
            params["status"] = status
        
        query = f"""
            SELECT 
                run_id,
                started_at,
                finished_at,
                status,
                environment,
                git_sha,
                metadata,
                EXTRACT(EPOCH FROM (finished_at - started_at)) * 1000 as duration_ms,
                CASE 
                    WHEN finished_at IS NULL THEN 'running'
                    WHEN status = 'completed' THEN 'success'
                    WHEN status = 'failed' THEN 'error'
                    ELSE status
                END as result_status
            FROM data_ingestion_runs
            {status_filter}
            ORDER BY started_at DESC
            LIMIT :limit
        """
        
        result = db.execute_query(query, params)
        
        # Get event counts for each run
        runs_with_stats = []
        for run in result or []:
            run_id = run['run_id']
            
            # Count events by level for this run
            event_stats_query = """
                SELECT 
                    level,
                    COUNT(*) as count,
                    COUNT(*) FILTER (WHERE error_message IS NOT NULL) as error_count,
                    COUNT(*) FILTER (WHERE records_saved > 0) as success_count,
                    SUM(records_saved) FILTER (WHERE records_saved > 0) as total_records_saved
                FROM data_ingestion_events
                WHERE run_id = :run_id
                GROUP BY level
            """
            
            try:
                event_stats = db.execute_query(event_stats_query, {"run_id": run_id})
                
                # Parse metadata for additional info
                metadata = run.get('metadata', {})
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except:
                        metadata = {}
                
                # Calculate totals
                total_events = sum(stat['count'] for stat in event_stats) if event_stats else 0
                total_errors = sum(stat['error_count'] for stat in event_stats) if event_stats else 0
                total_saved = sum(stat['total_records_saved'] for stat in event_stats) if event_stats else 0
                
                run_info = {
                    **run,
                    'total_events': total_events,
                    'total_errors': total_errors,
                    'total_records_saved': total_saved,
                    'event_stats': event_stats or [],
                    'symbols_count': len(metadata.get('symbols', [])) if metadata.get('symbols') else 0,
                    'data_types_count': len(metadata.get('data_types', [])) if metadata.get('data_types') else 0,
                    'operation': metadata.get('operation', 'unknown')
                }
                
                runs_with_stats.append(run_info)
                
            except Exception as e:
                logger.warning(f"Failed to get event stats for run {run_id}: {e}")
                runs_with_stats.append({
                    **run,
                    'total_events': 0,
                    'total_errors': 0,
                    'total_records_saved': 0,
                    'event_stats': [],
                    'symbols_count': 0,
                    'data_types_count': 0,
                    'operation': 'unknown'
                })
        
        return {
            "success": True,
            "runs": runs_with_stats,
            "count": len(runs_with_stats),
            "status_filter": status or "ALL"
        }
        
    except Exception as e:
        logger.error(f"Failed to get data ingestion runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-ingestion-events/{run_id}")
async def get_data_ingestion_events(run_id: str, level: str = None):
    """Get detailed events for a specific data ingestion run"""
    try:
        # Build query with optional level filter
        level_filter = ""
        params = {"run_id": run_id}
        
        if level and level != "ALL":
            level_filter = "AND level = :level"
            params["level"] = level
        
        query = f"""
            SELECT 
                id,
                event_ts,
                level,
                provider,
                operation,
                symbol,
                duration_ms,
                records_in,
                records_saved,
                message,
                error_type,
                error_message,
                root_cause_type,
                root_cause_message,
                context
            FROM data_ingestion_events
            WHERE run_id = CAST(:run_id AS uuid)
            {level_filter}
            ORDER BY event_ts DESC
        """
        
        result = db.execute_query(query, params)
        
        # Parse context for each event
        events = []
        for event in result or []:
            context = event.get('context', {})
            if isinstance(context, str):
                try:
                    context = json.loads(context)
                except:
                    context = {}
            
            event_info = {
                **event,
                'context': context,
                'has_error': event.get('error_message') is not None,
                'success': event.get('records_saved', 0) > 0 and event.get('error_message') is None
            }
            events.append(event_info)
        
        return {
            "success": True,
            "run_id": run_id,
            "events": events,
            "count": len(events),
            "level_filter": level or "ALL"
        }
        
    except Exception as e:
        logger.error(f"Failed to get data ingestion events for {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data-ingestion-rerun/{run_id}")
async def rerun_data_ingestion(run_id: str):
    """Re-run a data ingestion run with the same parameters"""
    try:
        # Get original run details
        run_query = """
            SELECT metadata, status
            FROM data_ingestion_runs
            WHERE run_id = CAST(:run_id AS uuid)
        """
        
        run_result = db.execute_query(run_query, {"run_id": run_id})
        
        if not run_result:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        
        original_run = run_result[0]
        metadata = original_run.get('metadata', {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except:
                metadata = {}
        
        # Extract original parameters
        symbols = metadata.get('symbols', [])
        data_types = metadata.get('data_types', [])
        operation = metadata.get('operation', 'refresh')
        
        if not symbols or not data_types:
            raise HTTPException(status_code=400, detail="Original run has incomplete metadata for rerun")
        
        # Create new run ID
        new_run_id = str(uuid.uuid4())
        set_ingestion_run_id(new_run_id)
        
        # Start new run
        audit.start_run(new_run_id, metadata={
            "operation": operation,
            "symbols": symbols,
            "data_types": data_types,
            "rerun_of": run_id,
            "rerun_reason": "manual_rerun"
        })
        
        audit.log_event(level="info", provider="system", operation="rerun.start", 
                       message=f"Starting rerun of {run_id}")
        
        # Execute the same operation
        refresh_manager = DataRefreshManager()
        
        # Convert string data types to DataType enum
        # Support all DataType enum values by their `.value` strings.
        data_type_mapping = {dt.value: dt for dt in DataType}
        # Backward-compatible alias used by UIs
        data_type_mapping["market_news"] = DataType.NEWS
        
        results = {}
        for symbol in symbols:
            symbol_results = {}
            try:
                mapped_types = [data_type_mapping[dt] for dt in data_types]
                refresh_result = refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=mapped_types,
                    # Use PERIODIC to enable freshness-based skipping and self-healing backfills.
                    # force=True will still override freshness checks.
                    mode=RefreshMode.PERIODIC,
                    force=True,
                )

                for dt in data_types:
                    dt_key = str(dt)
                    res = (refresh_result.results or {}).get(dt_key)
                    success = bool(res and res.status == RefreshStatus.SUCCESS)
                    msg = res.message if res and getattr(res, "message", None) else (
                        f"Successfully refreshed {dt} for {symbol}" if success else f"Failed to refresh {dt} for {symbol}"
                    )

                    symbol_results[dt] = {
                        "success": success,
                        "message": msg,
                    }

                    audit.log_event(
                        level="info",
                        provider="system",
                        operation="rerun.symbol_complete",
                        symbol=symbol,
                        context={"data_type": dt, "success": success}
                    )
            except Exception as e:
                logger.error(f"Failed to refresh data for {symbol}: {e}")
                for dt in data_types:
                    symbol_results[dt] = {
                        "success": False,
                        "message": f"Error refreshing {dt} for {symbol}: {str(e)}",
                    }
            
            results[symbol] = symbol_results
        
        audit.finish_run(new_run_id, status="completed", metadata={"results": results})
        
        return {
            "success": True,
            "message": f"Rerun completed for {len(symbols)} symbols",
            "new_run_id": new_run_id,
            "original_run_id": run_id,
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Failed to rerun {run_id}: {e}")
        try:
            audit.finish_run(new_run_id, status="failed", metadata={"error": str(e)})
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-loading-summary")
async def get_data_loading_summary(hours: int = 24):
    """Get comprehensive data loading summary for the last N hours"""
    try:
        from datetime import datetime, timedelta
        
        start_time = datetime.now() - timedelta(hours=hours)
        
        # Get runs summary
        runs_query = """
            SELECT 
                status,
                COUNT(*) as count,
                AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) * 1000) as avg_duration_ms,
                MIN(started_at) as earliest,
                MAX(started_at) as latest
            FROM data_ingestion_runs
            WHERE started_at >= :start_time
            GROUP BY status
        """
        
        runs_summary = db.execute_query(runs_query, {"start_time": start_time})
        
        # Get events summary
        events_query = """
            SELECT 
                level,
                provider,
                operation,
                COUNT(*) as count,
                SUM(records_saved) as total_records_saved,
                SUM(records_in) as total_records_processed,
                AVG(duration_ms) as avg_duration_ms,
                COUNT(*) FILTER (WHERE error_message IS NOT NULL) as error_count
            FROM data_ingestion_events
            WHERE event_ts >= :start_time
            GROUP BY level, provider, operation
            ORDER BY count DESC
        """
        
        events_summary = db.execute_query(events_query, {"start_time": start_time})
        
        # Get error summary
        errors_query = """
            SELECT 
                error_type,
                error_message,
                COUNT(*) as count,
                MAX(event_ts) as last_occurrence
            FROM data_ingestion_events
            WHERE event_ts >= :start_time
            AND error_message IS NOT NULL
            GROUP BY error_type, error_message
            ORDER BY count DESC
            LIMIT 20
        """
        
        errors_summary = db.execute_query(errors_query, {"start_time": start_time})
        
        # Get symbol performance
        symbols_query = """
            SELECT 
                symbol,
                COUNT(*) as operations,
                COUNT(*) FILTER (WHERE records_saved > 0) as successful_operations,
                SUM(records_saved) as total_records_saved,
                COUNT(*) FILTER (WHERE error_message IS NOT NULL) as error_count
            FROM data_ingestion_events
            WHERE event_ts >= :start_time
            AND symbol IS NOT NULL
            GROUP BY symbol
            ORDER BY operations DESC
            LIMIT 20
        """
        
        symbols_summary = db.execute_query(symbols_query, {"start_time": start_time})
        
        return {
            "success": True,
            "summary_period_hours": hours,
            "runs_summary": runs_summary or [],
            "events_summary": events_summary or [],
            "errors_summary": errors_summary or [],
            "symbols_summary": symbols_summary or [],
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get data loading summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ensure-ema-data/{symbol}")
async def ensure_ema_data_for_symbol(symbol: str):
    """Ensure sufficient EMA data exists for reliable calculations"""
    try:
        from app.utils.market_data_utils import ensure_sufficient_ema_data
        from datetime import datetime
        
        target_date = datetime.now().date()
        db_url = os.getenv("DATABASE_URL")
        
        if not db_url:
            raise HTTPException(status_code=500, detail="DATABASE_URL not configured")
        
        success = ensure_sufficient_ema_data(symbol, target_date, db_url)
        
        if success:
            return {
                "success": True,
                "message": f"✅ EMA data ensured for {symbol}",
                "symbol": symbol,
                "target_date": str(target_date)
            }
        else:
            return {
                "success": False,
                "message": f"❌ Failed to ensure EMA data for {symbol}",
                "symbol": symbol,
                "target_date": str(target_date)
            }
        
    except Exception as e:
        logger.error(f"Failed to ensure EMA data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ema-data-health/{symbol}")
async def get_ema_data_health(symbol: str):
    """Get comprehensive EMA data health assessment for a symbol"""
    try:
        from app.utils.market_data_utils import check_ema_data_health
        import os
        
        db_url = os.getenv("DATABASE_URL")
        
        if not db_url:
            raise HTTPException(status_code=500, detail="DATABASE_URL not configured")
        
        health = check_ema_data_health(symbol, db_url)
        
        return {
            "success": True,
            "symbol": symbol,
            "health_assessment": health,
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get EMA data health for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enrich-ema-data/{symbol}")
async def enrich_ema_data_for_symbol(symbol: str):
    """Trigger comprehensive EMA data enrichment for a symbol"""
    try:
        from app.utils.market_data_utils import enrich_ema_data_for_symbol
        from datetime import datetime
        import os
        
        db_url = os.getenv("DATABASE_URL")
        
        if not db_url:
            raise HTTPException(status_code=500, detail="DATABASE_URL not configured")
        
        success = enrich_ema_data_for_symbol(symbol, db_url)
        
        if success:
            return {
                "success": True,
                "message": f"✅ EMA data enrichment completed for {symbol}",
                "symbol": symbol
            }
        else:
            return {
                "success": False,
                "message": f"❌ EMA data enrichment failed for {symbol}",
                "symbol": symbol
            }
        
    except Exception as e:
        logger.error(f"Failed to enrich EMA data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query")
async def execute_custom_query(request: Dict[str, Any]):
    """Execute custom database query (read-only operations only)"""
    try:
        query = request.get("query", "")
        params = request.get("params", {})
        
        # Security: Only allow SELECT queries
        if not query.strip().upper().startswith("SELECT"):
            raise HTTPException(
                status_code=400,
                detail="Only SELECT queries are allowed for security reasons"
            )
        
        # Execute query
        result = db.execute_query(query, params)
        
        return {
            "success": True,
            "data": result,
            "count": len(result) if result else 0
        }
        
    except Exception as e:
        logger.error(f"Custom query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health/database")
async def get_database_health():
    """Get database health and performance metrics"""
    try:
        health_checks = {}
        
        # Basic connectivity
        try:
            db.execute_query("SELECT 1")
            health_checks["connectivity"] = "healthy"
        except Exception as e:
            health_checks["connectivity"] = f"unhealthy: {str(e)}"
        
        # Table counts
        table_counts = {}
        tables = ["raw_market_data_daily", "raw_market_data_intraday", "indicators_daily"]
        
        for table in tables:
            try:
                count_query = f"SELECT COUNT(*) as count FROM {table}"
                result = db.execute_query(count_query)
                table_counts[table] = result[0]["count"] if result else 0
            except:
                table_counts[table] = "error"
        
        health_checks["table_counts"] = table_counts
        
        # Recent activity
        try:
            recent_query = """
                SELECT COUNT(*) as count 
                FROM data_ingestion_runs 
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            """
            result = db.execute_query(recent_query)
            health_checks["recent_ingestion_runs"] = result[0]["count"] if result else 0
        except:
            health_checks["recent_ingestion_runs"] = "unknown"
        
        return {
            "status": "healthy" if health_checks["connectivity"] == "healthy" else "unhealthy",
            "checks": health_checks,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-quality/validation")
async def get_data_quality_validation():
    """Get data quality validation results"""
    try:
        validation_results = {}
        
        # Volume data completeness
        try:
            volume_check = """
                SELECT 
                    'daily_volume' as check_type,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE volume IS NOT NULL) as records_with_volume,
                    ROUND(COUNT(*) FILTER (WHERE volume IS NOT NULL) * 100.0 / COUNT(*), 2) as completeness_pct
                FROM raw_market_data_daily
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                
                UNION ALL
                
                SELECT 
                    'intraday_volume' as check_type,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE volume IS NOT NULL) as records_with_volume,
                    ROUND(COUNT(*) FILTER (WHERE volume IS NOT NULL) * 100.0 / COUNT(*), 2) as completeness_pct
                FROM raw_market_data_intraday
                WHERE ts >= NOW() - INTERVAL '24 hours'
            """
            
            result = db.execute_query(volume_check)
            validation_results["volume_completeness"] = result
            
        except Exception as e:
            validation_results["volume_completeness"] = [{"error": str(e)}]
        
        # Price data consistency
        try:
            price_check = """
                SELECT 
                    'price_consistency' as check_type,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE high >= low AND high >= open AND high >= close AND low <= open AND low <= close) as valid_records,
                    ROUND(COUNT(*) FILTER (WHERE high >= low AND high >= open AND high >= close AND low <= open AND low <= close) * 100.0 / COUNT(*), 2) as consistency_pct
                FROM raw_market_data_daily
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            """
            
            result = db.execute_query(price_check)
            validation_results["price_consistency"] = result
            
        except Exception as e:
            validation_results["price_consistency"] = [{"error": str(e)}]
        
        # Data freshness
        try:
            freshness_check = """
                SELECT 
                    'daily_freshness' as check_type,
                    MAX(date) as latest_date,
                    CURRENT_DATE - MAX(date) as days_old
                FROM raw_market_data_daily
                
                UNION ALL
                
                SELECT 
                    'intraday_freshness' as check_type,
                    MAX(ts::date) as latest_date,
                    CURRENT_DATE - MAX(ts::date) as days_old
                FROM raw_market_data_intraday
            """
            
            result = db.execute_query(freshness_check)
            validation_results["data_freshness"] = result
            
        except Exception as e:
            validation_results["data_freshness"] = [{"error": str(e)}]
        
        return {
            "validation_timestamp": datetime.now().isoformat(),
            "results": validation_results
        }
        
    except Exception as e:
        logger.error(f"Data quality validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/metrics")
async def get_system_metrics():
    """Get system performance and usage metrics"""
    try:
        metrics = {}
        
        # Database size
        try:
            size_query = """
                SELECT 
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
                    pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
                FROM pg_tables 
                WHERE schemaname = 'public'
                AND tablename IN ('raw_market_data_daily', 'raw_market_data_intraday', 'indicators_daily', 'fundamentals_snapshots')
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            """
            
            result = db.execute_query(size_query)
            metrics["table_sizes"] = result
            
        except Exception as e:
            metrics["table_sizes"] = [{"error": str(e)}]
        
        # Record counts by table
        try:
            count_query = """
                SELECT 
                    'raw_market_data_daily' as table_name, COUNT(*) as record_count
                FROM raw_market_data_daily
                
                UNION ALL
                
                SELECT 
                    'raw_market_data_intraday' as table_name, COUNT(*) as record_count
                FROM raw_market_data_intraday
                
                UNION ALL
                
                SELECT 
                    'indicators_daily' as table_name, COUNT(*) as record_count
                FROM indicators_daily
                
                UNION ALL
                
                SELECT 
                    'fundamentals_snapshots' as table_name, COUNT(*) as record_count
                FROM fundamentals_snapshots
            """
            
            result = db.execute_query(count_query)
            metrics["record_counts"] = result
            
        except Exception as e:
            metrics["record_counts"] = [{"error": str(e)}]
        
        # Recent ingestion activity
        try:
            activity_query = """
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as runs,
                    COUNT(DISTINCT symbol) as symbols_processed
                FROM data_ingestion_runs
                WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY DATE(created_at)
                ORDER BY date DESC
                LIMIT 30
            """
            
            result = db.execute_query(activity_query)
            metrics["ingestion_activity"] = result
            
        except Exception as e:
            metrics["ingestion_activity"] = [{"error": str(e)}]
        
        return {
            "metrics_timestamp": datetime.now().isoformat(),
            "metrics": metrics
        }
        
    except Exception as e:
        logger.error(f"System metrics failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-summary/symbol/{symbol}")
async def get_symbol_data_summary(symbol: str):
    """Get data summary for a specific symbol across all tables"""
    try:
        # Get data from all relevant tables for this symbol
        summaries = {}
        
        # Check intraday data
        try:
            intraday_query = """
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(ts) = CURRENT_DATE) as today_records,
                    MAX(ts) as last_updated,
                    COUNT(*) FILTER (WHERE volume IS NOT NULL) as records_with_volume
                FROM raw_market_data_intraday
                WHERE symbol = :symbol
            """
            intraday_result = db.execute_query(intraday_query, {"symbol": symbol})
            if intraday_result:
                summaries["intraday"] = intraday_result[0]
        except Exception as e:
            logger.warning(f"Failed to get intraday summary for {symbol}: {e}")
            summaries["intraday"] = {"error": str(e)}
        
        # Check daily data
        try:
            daily_query = """
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(date) = CURRENT_DATE) as today_records,
                    MAX(date) as last_updated,
                    COUNT(*) FILTER (WHERE volume IS NOT NULL) as records_with_volume
                FROM raw_market_data_daily
                WHERE symbol = :symbol
            """
            daily_result = db.execute_query(daily_query, {"symbol": symbol})
            if daily_result:
                summaries["daily"] = daily_result[0]
        except Exception as e:
            logger.warning(f"Failed to get daily summary for {symbol}: {e}")
            summaries["daily"] = {"error": str(e)}
        
        # Check indicators
        try:
            indicators_query = """
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(date) = CURRENT_DATE) as today_records,
                    MAX(date) as last_updated,
                    COUNT(*) FILTER (WHERE rsi_14 IS NOT NULL) as records_with_rsi,
                    COUNT(*) FILTER (WHERE ema_20 IS NOT NULL) as records_with_ema
                FROM indicators_daily
                WHERE symbol = :symbol
            """
            indicators_result = db.execute_query(indicators_query, {"symbol": symbol})
            if indicators_result:
                summaries["indicators"] = indicators_result[0]
        except Exception as e:
            logger.warning(f"Failed to get indicators summary for {symbol}: {e}")
            summaries["indicators"] = {"error": str(e)}
        
        # Check earnings data (uses stock_symbol column)
        try:
            earnings_query = """
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(report_date) = CURRENT_DATE) as today_records,
                    MAX(report_date) as last_updated
                FROM earnings_data
                WHERE stock_symbol = :symbol
            """
            earnings_result = db.execute_query(earnings_query, {"symbol": symbol})
            if earnings_result:
                summaries["earnings"] = earnings_result[0]
        except Exception as e:
            logger.warning(f"Failed to get earnings summary for {symbol}: {e}")
            summaries["earnings"] = {"error": str(e)}
        
        # Check fundamentals data
        try:
            fundamentals_query = """
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(as_of_date) = CURRENT_DATE) as today_records,
                    MAX(as_of_date) as last_updated
                FROM fundamentals_snapshots
                WHERE symbol = :symbol
            """
            fundamentals_result = db.execute_query(fundamentals_query, {"symbol": symbol})
            if fundamentals_result:
                summaries["fundamentals"] = fundamentals_result[0]
        except Exception as e:
            logger.warning(f"Failed to get fundamentals summary for {symbol}: {e}")
            summaries["fundamentals"] = {"error": str(e)}
        
        # Check market news
        try:
            news_query = """
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(published_at) = CURRENT_DATE) as today_records,
                    MAX(published_at) as last_updated
                FROM market_news
                WHERE symbols && ARRAY[:symbol]
            """
            news_result = db.execute_query(news_query, {"symbol": symbol})
            if news_result:
                summaries["news"] = news_result[0]
        except Exception as e:
            logger.warning(f"Failed to get news summary for {symbol}: {e}")
            summaries["news"] = {"error": str(e)}
        
        # Check industry peers
        try:
            peers_query = """
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                    MAX(created_at) as last_updated
                FROM industry_peers
                WHERE symbol = :symbol
            """
            peers_result = db.execute_query(peers_query, {"symbol": symbol})
            if peers_result:
                summaries["peers"] = peers_result[0]
        except Exception as e:
            logger.warning(f"Failed to get peers summary for {symbol}: {e}")
            summaries["peers"] = {"error": str(e)}
        
        return {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "data_summary": summaries
        }
        
    except Exception as e:
        logger.error(f"Failed to get symbol data summary for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fix-intraday-schema")
async def fix_intraday_schema():
    """Fix missing source column in raw_market_data_intraday table"""
    try:
        # Check if source column exists
        check_query = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'raw_market_data_intraday' 
            AND column_name = 'source'
        """
        
        result = db.execute_query(check_query)
        
        if result:
            return {
                "success": True,
                "message": "Source column already exists in raw_market_data_intraday table",
                "action": "none"
            }
        
        # Add source column if it doesn't exist
        alter_query = """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'raw_market_data_intraday' 
                    AND column_name = 'source'
                ) THEN
                    ALTER TABLE raw_market_data_intraday ADD COLUMN source TEXT;
                    
                    -- Update primary key to include source
                    ALTER TABLE raw_market_data_intraday DROP CONSTRAINT IF EXISTS raw_market_data_intraday_pkey;
                    ALTER TABLE raw_market_data_intraday ADD PRIMARY KEY (stock_symbol, ts, interval, source);
                    
                    RAISE NOTICE 'Added source column to raw_market_data_intraday';
                END IF;
            END $$;
        """
        
        db.execute_update(alter_query)
        
        logger.info("✅ Fixed raw_market_data_intraday table schema")
        
        return {
            "success": True,
            "message": "Successfully added source column to raw_market_data_intraday table",
            "action": "added_column"
        }
        
    except Exception as e:
        logger.error(f"Failed to fix intraday schema: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fix schema: {str(e)}")


# Import services that may not be available in all environments
try:
    from app.services.stock_screener_service import StockScreenerService
except ImportError:
    StockScreenerService = None

try:
    from app.services.stock_insights_service import StockInsightsService
except ImportError:
    StockInsightsService = None
