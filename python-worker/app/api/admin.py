"""
Admin API endpoints for trading system
Clean version with signal generation and storage
"""

from datetime import datetime
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

logger = get_logger("admin_api")

router = APIRouter(prefix="/admin", tags=["admin"])

# Request/Response Models
class RefreshRequest(BaseModel):
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


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_data(request: RefreshRequest, background_tasks: BackgroundTasks):
    """Trigger data refresh for specific symbols and data types"""
    run_id = datetime.now().isoformat()
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
            "indicators": DataType.INDICATORS,
            "fundamentals": DataType.FUNDAMENTALS,
            "earnings": DataType.EARNINGS,
            "market_news": DataType.MARKET_NEWS,
            "economic_calendar": DataType.ECONOMIC_CALENDAR
        }
        
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
            for data_type in request.data_types:
                try:
                    # Refresh data for this symbol and type
                    success = refresh_manager.refresh_symbol_data(
                        symbol=symbol,
                        data_type=data_type_mapping[data_type],
                        force=request.force
                    )
                    
                    symbol_results[data_type] = {
                        "success": success,
                        "message": f"Successfully refreshed {data_type} for {symbol}" if success else f"Failed to refresh {data_type} for {symbol}"
                    }
                    
                    audit.log_event(
                        level="info",
                        provider="system",
                        operation="refresh.symbol_complete",
                        metadata={"symbol": symbol, "data_type": data_type, "success": success}
                    )
                    
                except Exception as e:
                    logger.error(f"Failed to refresh {data_type} for {symbol}: {e}")
                    symbol_results[data_type] = {
                        "success": False,
                        "message": f"Error refreshing {data_type} for {symbol}: {str(e)}"
                    }
            
            results[symbol] = symbol_results
        
        audit.finish_run(run_id, status="completed", metadata={"results": results})
        
        return RefreshResponse(
            success=True,
            message=f"Data refresh completed for {len(request.symbols)} symbols",
            results=results
        )
        
    except Exception as e:
        logger.error(f"Data refresh failed: {e}")
        try:
            audit.finish_run(run_id, status="failed", metadata={"error": str(e)})
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
                        query = """
                            SELECT sma_50, sma_200, ema_20, rsi_14, macd, macd_signal 
                            FROM indicators_daily 
                            WHERE symbol = :symbol AND date <= :backtest_date 
                            ORDER BY date DESC LIMIT 1
                        """
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
                        query = """
                            SELECT sma_50, sma_200, ema_20, rsi_14, macd, macd_signal 
                            FROM indicators_daily 
                            WHERE symbol = :symbol 
                            ORDER BY date DESC LIMIT 1
                        """
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
        # Validate table name
        valid_tables = [
            "raw_market_data_daily", "raw_market_data_intraday", "indicators_daily",
            "fundamentals_snapshots", "industry_peers", "market_news", "earnings_data",
            "macro_market_data", "stocks", "data_ingestion_runs", "data_ingestion_events"
        ]
        
        if table not in valid_tables:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid table: {table}. Valid tables: {valid_tables}"
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
            # Use report_date instead of created_at for earnings_data
            query = f"""
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE(report_date) = CURRENT_DATE) as today_records,
                    MAX(report_date) as last_updated,
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
        else:
            # Use symbol and date for standard tables (raw_market_data_daily, indicators_daily)
            quality_query = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL AND date IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND date IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || date) * 100.0 / COUNT(*)
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
        
    except Exception as e:
        logger.error(f"Failed to get data summary for {table}: {e}")
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
            end_dt = start_dt.replace(day=start_dt.day + 30) if start_dt.day <= 28 else start_dt.replace(month=start_dt.month + 1, day=1)
        
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
                timestamp,
                message,
                metadata
            FROM data_ingestion_events
            WHERE timestamp BETWEEN :start_date AND :end_date
            AND (:level = 'ALL' OR level = :level)
            ORDER BY timestamp DESC
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
