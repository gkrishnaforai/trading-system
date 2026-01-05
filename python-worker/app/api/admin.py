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


@router.get("/insights/{symbol}")
async def get_stock_insights(symbol: str):
    """Get comprehensive stock insights"""
    try:
        insights_service = StockInsightsService()
        
        insights = insights_service.get_comprehensive_insights(symbol)
        
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
            "fundamentals_snapshots", "industry_peers", "market_news", "earnings_calendar"
        ]
        
        if table not in valid_tables:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid table: {table}. Valid tables: {valid_tables}"
            )
        
        # Get summary from database
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
        
        # Get quality metrics if available
        quality_query = f"""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND date IS NOT NULL) as non_null_rows,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND date IS NOT NULL) * 100.0 / COUNT(*) as null_rate,
                COUNT(DISTINCT symbol || date) * 100.0 / COUNT(*) as duplicate_rate
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


# Import services that may not be available in all environments
try:
    from app.services.stock_screener_service import StockScreenerService
except ImportError:
    StockScreenerService = None

try:
    from app.services.stock_insights_service import StockInsightsService
except ImportError:
    StockInsightsService = None
