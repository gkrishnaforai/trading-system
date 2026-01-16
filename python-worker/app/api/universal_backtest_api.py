# Universal Backtest API Router
# Integrates with existing API server on port 8001

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy import create_engine

# Import existing DRY functions (no changes to TQQQ API)
from app.utils.database_helper import DatabaseQueryHelper
from app.utils.market_data_utils import calculate_market_regime_context, calculate_ema_slope
from app.services.comprehensive_data_loader import ComprehensiveDataLoader
from app.observability.logging import get_logger, log_exception, log_with_context
from app.config import settings  # Import centralized settings

# Import signal engines (will extend as needed)
from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
from app.signal_engines.signal_calculator_core import SignalConfig, SignalResult, MarketConditions

# ========================================
# IMPORTANT: Router Configuration Rules
# ========================================
# DO NOT ADD PREFIX HERE! Prefixes are managed in api_server.py
# WRONG: router = APIRouter(prefix="/api/v1/universal", tags=["universal"])
# CORRECT: router = APIRouter(tags=["universal"])
# ========================================
router = APIRouter(tags=["universal"])

# Initialize logger for the API
logger = get_logger(__name__)

# Initialize database helper and data loader
db_helper = DatabaseQueryHelper()
data_loader = ComprehensiveDataLoader()

# Request models
class HistoricalDataRequest(BaseModel):
    symbol: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: Optional[int] = None

class SignalRequest(BaseModel):
    symbol: str
    date: str
    asset_type: str = "3x_etf"  # 3x_etf, regular_etf, stock

class BacktestRequest(BaseModel):
    symbol: str
    start_date: str
    end_date: str
    asset_type: str = "3x_etf"

# Asset type configurations
ASSET_CONFIGS = {
    "3x_etf": {
        "volatility_threshold": 8.0,
        "rsi_oversold": 48,
        "risk_management": "Aggressive volatility detection",
        "engine": "unified_tqqq_swing"  # Use TQQQ engine for all 3x ETFs
    },
    "regular_etf": {
        "volatility_threshold": 5.0,
        "rsi_oversold": 35,
        "risk_management": "Standard risk management",
        "engine": "unified_tqqq_swing"  # Use TQQQ as proxy (will create dedicated engine later)
    },
    "stock": {
        "volatility_threshold": 6.0,
        "rsi_oversold": 30,
        "risk_management": "Stock-specific risk management",
        "engine": "unified_tqqq_swing"  # Use TQQQ as proxy (will create dedicated engine later)
    }
}

# Initialize database helper and data loader
db_helper = DatabaseQueryHelper()
data_loader = ComprehensiveDataLoader()

@router.get("/historical-data/{symbol}")
async def get_historical_data_endpoint(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = None
):
    """
    Get historical market data for any symbol
    Uses same data source as TQQQ backtest (/api/v1/data/{symbol})
    """
    try:
        logger.info(f"📊 Fetching historical data for {symbol}", extra={
            'context': {
                'symbol': symbol,
                'start_date': start_date,
                'end_date': end_date,
                'limit': limit
            }
        })
        
        # Use existing DatabaseQueryHelper method instead of direct SQL
        # Use the same method that TQQQ API uses
        historical_data = DatabaseQueryHelper.get_historical_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        if not historical_data:
            raise HTTPException(
                status_code=404,
                detail=f"No historical data available for {symbol}"
            )
        
        logger.info(f"✅ Retrieved {len(historical_data)} records for {symbol}")
        
        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "historical_data": historical_data,
                "total_records": len(historical_data),
                "start_date": start_date,
                "end_date": end_date
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching historical data for {symbol}: {str(e)}")
        log_exception(logger, e, f"Historical data fetch for {symbol}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/signal/universal")
async def get_universal_signal(request: SignalRequest):
    """
    Get signal for any asset type using appropriate engine
    Reuses existing TQQQ engine for 3x ETFs, proxy for others
    """
    try:
        logger.info(f"🎯 Generating universal signal for {request.symbol}", extra={
            'context': {
                'symbol': request.symbol,
                'date': request.date,
                'asset_type': request.asset_type
            }
        })
        
        # Get asset configuration
        asset_config = ASSET_CONFIGS.get(request.asset_type, ASSET_CONFIGS["3x_etf"])
        
        # Check if data exists for the symbol using existing DatabaseQueryHelper
        try:
            # Use the existing DatabaseQueryHelper method that TQQQ API uses
            # This checks the raw_market_data_daily table properly
            data = DatabaseQueryHelper.get_historical_data(
                symbol=request.symbol,
                start_date=None,
                end_date=None,
                limit=1  # Just check if any data exists
            )
            
            if not data or len(data) == 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Symbol '{request.symbol}' not found in database. Please verify the symbol is correct and data has been loaded."
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error checking data availability for '{request.symbol}': {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Error checking data availability for '{request.symbol}': {str(e)}"
            )
        
        # Load market data using same method as TQQQ API for consistency
        target_date = datetime.strptime(request.date, "%Y-%m-%d").date()
        
        # For TQQQ, use the exact same method as TQQQ API for consistency
        if request.symbol.upper() == 'TQQQ':
            # Use the same query and logic as TQQQ Engine API (unchanged)
            from sqlalchemy import create_engine, text
            
            engine = create_engine(settings.database_url)
            
            # Build the same query as TQQQ API
            query = """
                SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
                FROM indicators_daily i
                JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
                WHERE i.symbol = 'TQQQ' AND i.date = :target_date
                ORDER BY i.date
            """
            
            with engine.connect() as conn:
                result = conn.execute(text(query), {"target_date": target_date.strftime("%Y-%m-%d")})
                rows = result.fetchall()
                
                if not rows:
                    # Try to get most recent data if specific date not found
                    query_latest = """
                        SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
                        FROM indicators_daily i
                        JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
                        WHERE i.symbol = 'TQQQ'
                        ORDER BY i.date DESC
                        LIMIT 1
                    """
                    result = conn.execute(text(query_latest))
                    rows = result.fetchall()
                
                if not rows:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No TQQQ data available for {request.date}"
                    )
                
                row = rows[0]
                
                # Use the same market context calculation as TQQQ API (no asset_type parameter)
                market_context = calculate_market_regime_context(
                    symbol='TQQQ',
                    target_date=target_date.strftime("%Y-%m-%d"),
                    db_url=settings.database_url
                )
                
                # Create market conditions exactly like TQQQ API
                conditions = MarketConditions(
                    rsi=row[2],                    # rsi_14
                    sma_20=row[4],                # ema_20
                    sma_50=row[3],                # sma_50
                    ema_20=row[4],                # ema_20
                    current_price=row[1],          # close
                    recent_change=market_context['recent_change'] / 100,
                    macd=row[5],                  # macd
                    macd_signal=row[6],           # macd_signal
                    volatility=market_context['volatility'],
                    vix_level=market_context['vix_level'],
                    volatility_trend='stable'
                )
        else:
            # For other symbols, use the enhanced methodology with same data source
            from app.utils.market_data_utils import get_symbol_indicators_data
            
            # Get symbol data using same indicators methodology as TQQQ
            symbol_data = get_symbol_indicators_data(
                symbol=request.symbol,
                target_date=target_date.strftime("%Y-%m-%d"),
                db_url=settings.database_url
            )
            
            if not symbol_data:
                raise HTTPException(
                    status_code=404,
                    detail=f"No {request.symbol} data available for {request.date}"
                )
            
            # Use enhanced market context calculation with asset-type-specific thresholds
            market_context = calculate_market_regime_context(
                symbol=request.symbol,
                target_date=target_date.strftime("%Y-%m-%d"),
                db_url=settings.database_url,
                asset_type=request.asset_type  # Pass asset type for specific calculations
            )
            
            if not market_context:
                raise HTTPException(
                    status_code=404,
                    detail=f"No market data available for {request.symbol} on {request.date}"
                )
            
            # Create market conditions using same indicators data as TQQQ methodology
            # Debug: Log available keys in symbol_data
            logger.info(f"Available keys in symbol_data: {list(symbol_data.keys())}")
            
            conditions = MarketConditions(
                rsi=symbol_data['rsi_14'],        # From indicators table (same as TQQQ)
                sma_20=symbol_data.get('sma_20', symbol_data.get('ema_20', 0)),     # ✅ Use SMA20 if available, fallback to EMA20
                sma_50=symbol_data['sma_50'],     # From indicators table (same as TQQQ)
                ema_20=symbol_data['ema_20'],     # From indicators table (same as TQQQ)
                current_price=symbol_data['close'], # From raw data (same as TQQQ)
                recent_change=market_context['recent_change'] / 100,
                macd=float(symbol_data['macd']) if symbol_data['macd'] is not None else 0.0,         # From indicators table (same as TQQQ)
                macd_signal=float(symbol_data['macd_signal']) if symbol_data['macd_signal'] is not None else 0.0, # From indicators table (same as TQQQ)
                volatility=market_context['volatility'],
                vix_level=market_context['vix_level'],
                volatility_trend='stable',
                volume=float(symbol_data['volume']) if symbol_data['volume'] is not None else 0.0,  # Current volume
                avg_volume_20d=float(symbol_data['avg_volume_20d']) if symbol_data.get('avg_volume_20d') is not None else 0.0  # 20-day average volume
            )
        
        # Calculate EMA slope for trend analysis
        try:
            ema_slope = calculate_ema_slope(request.symbol, request.date, settings.database_url)
        except Exception as e:
            logger.warning(f"Failed to calculate EMA slope for {request.symbol}: {e}")
            ema_slope = 0.0
        
        # Use TQQQ engine for all (will extend later)
        # Create appropriate config based on asset type
        if request.asset_type == "3x_etf":
            config = SignalConfig(
                rsi_oversold=48,  # Higher threshold for 3x ETFs
                rsi_overbought=70,
                max_volatility=10.0  # Higher volatility tolerance
            )
        elif request.asset_type == "regular_etf":
            config = SignalConfig(
                rsi_oversold=35,  # Standard ETF threshold
                rsi_overbought=70,
                max_volatility=6.0  # Standard volatility
            )
        else:  # stock
            config = SignalConfig(
                rsi_oversold=30,  # Stock threshold
                rsi_overbought=70,
                max_volatility=8.0  # Stock volatility
            )
        
        engine = UnifiedTQQQSwingEngine(config)
        
        # Generate signal
        signal_result = engine.generate_signal(conditions)
        
        # Adapt response for requested symbol
        response_data = {
            "engine": {
                "name": f"Universal {request.asset_type.replace('_', ' ').title()} Engine",
                "type": request.asset_type,
                "description": f"Optimized for {request.asset_type.replace('_', ' ').title()} trading",
                "config": asset_config
            },
            "market_data": {
                "symbol": request.symbol,
                "date": request.date,
                "price": conditions.current_price,
                "rsi": conditions.rsi,
                "sma_20": conditions.sma_20,
                "sma_50": conditions.sma_50,
                "ema_20": conditions.ema_20,
                "macd": conditions.macd,
                "macd_signal": conditions.macd_signal,
                "high": market_context.get('high', conditions.current_price),
                "low": market_context.get('low', conditions.current_price),
                "volume": conditions.volume,  # ✅ Add current volume
                "avg_volume_20d": conditions.avg_volume_20d,  # ✅ Add average volume
                "data_source": "python_worker"  # ✅ Add data source
            },
            "signal": {
                "signal": signal_result.signal.value,
                "confidence": signal_result.confidence,
                "reasoning": signal_result.reasoning,
                "metadata": signal_result.metadata,
                "volume": conditions.volume,  # ✅ Add volume to signal
                "avg_volume_20d": conditions.avg_volume_20d,  # ✅ Add average volume to signal
                "data_source": "python_worker"  # ✅ Add data source
            },
            "analysis": {
                "daily_range": f"{market_context.get('low', 0):.2f} - {market_context.get('high', 0):.2f}",
                "intraday_change": f"{market_context.get('intraday_change', 0):.2f}%",
                "real_volatility": f"{conditions.volatility:.2f}%",
                "recent_change": f"{conditions.recent_change:.2f}%",
                "vix_level": f"{conditions.vix_level:.2f}",
                "market_stress": conditions.volatility > asset_config['volatility_threshold'],
                "volatility_level": "HIGH" if conditions.volatility > asset_config['volatility_threshold'] else "NORMAL",
                "current_volume": conditions.volume,  # ✅ Add current volume for UI mapping
                "avg_volume_20d": conditions.avg_volume_20d,  # ✅ Add average volume for UI mapping
                "volume_ratio": conditions.volume / conditions.avg_volume_20d if conditions.avg_volume_20d > 0 else 1.0,  # ✅ Add volume ratio
                "price_range": f"{market_context.get('low', 0):.2f} - {market_context.get('high', 0):.2f}",  # ✅ Add price range
                "ema_slope": ema_slope,  # ✅ Add EMA slope for trend analysis
                "data_source": "python_worker"  # ✅ Add data source
            },
            "timestamp": datetime.now().isoformat(),
            "asset_type": request.asset_type
        }
        
        logger.info(f"✅ Generated {request.asset_type} signal for {request.symbol}: {signal_result.signal.value}")
        
        return {
            "success": True,
            "data": response_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error generating signal for {request.symbol}: {str(e)}")
        log_exception(logger, e, f"Universal signal generation for {request.symbol}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/backtest/universal")
async def run_universal_backtest(request: BacktestRequest):
    """
    Run backtest for any asset type over date range
    Reuses existing historical data infrastructure
    """
    try:
        logger.info(f"🔄 Starting universal backtest for {request.symbol}", extra={
            'context': {
                'symbol': request.symbol,
                'start_date': request.start_date,
                'end_date': request.end_date,
                'asset_type': request.asset_type
            }
        })
        
        # Parse dates
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d").date()
        
        # Get historical data using existing function
        historical_data = DatabaseQueryHelper.get_historical_data(
            symbol=request.symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        if not historical_data:
            raise HTTPException(
                status_code=404,
                detail=f"No historical data available for {request.symbol} in specified date range"
            )
        
        # Generate signals for each date
        signals = []
        current_date = start_date
        
        while current_date <= end_date:
            try:
                # Skip weekends (market closed)
                if current_date.weekday() >= 5:
                    current_date += timedelta(days=1)
                    continue
                
                # Generate signal for this date
                signal_request = SignalRequest(
                    symbol=request.symbol,
                    date=current_date.strftime("%Y-%m-%d"),
                    asset_type=request.asset_type
                )
                
                signal_response = await get_universal_signal(signal_request)
                
                if signal_response["success"]:
                    signal_data = signal_response["data"]
                    signals.append({
                        "date": current_date.strftime("%Y-%m-%d"),
                        "signal": signal_data["signal"]["signal"],
                        "confidence": signal_data["signal"]["confidence"],
                        "price": signal_data["market_data"]["price"],
                        "reasoning": signal_data["signal"]["reasoning"][:3],  # Top 3 reasons
                        "metadata": signal_data["signal"]["metadata"]
                    })
                
                current_date += timedelta(days=1)
                
            except Exception as e:
                logger.warning(f"⚠️ Could not generate signal for {current_date}: {str(e)}")
                current_date += timedelta(days=1)
                continue
        
        # Calculate performance metrics
        performance = calculate_backtest_performance(historical_data, signals)
        
        response_data = {
            "backtest_info": {
                "symbol": request.symbol,
                "asset_type": request.asset_type,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "total_days": (end_date - start_date).days,
                "signals_generated": len(signals)
            },
            "signals": signals,
            "performance": performance,
            "asset_config": ASSET_CONFIGS[request.asset_type]
        }
        
        logger.info(f"✅ Completed backtest for {request.symbol}: {len(signals)} signals generated")
        
        return {
            "success": True,
            "data": response_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error running backtest for {request.symbol}: {str(e)}")
        log_exception(logger, e, f"Universal backtest for {request.symbol}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/assets/supported")
async def get_supported_assets():
    """
    Get list of supported asset types and example symbols
    """
    try:
        supported_assets = {
            "3x_etf": {
                "description": "3x Leveraged ETFs",
                "examples": ["TQQQ", "SOXL", "FNGO", "LABU", "TECL"],
                "volatility_profile": "Very High",
                "optimal_for": "Short-term trading, volatility capture"
            },
            "regular_etf": {
                "description": "Standard ETFs",
                "examples": ["QQQ", "SPY", "SMH", "IWM", "VTI", "XLF"],
                "volatility_profile": "Moderate",
                "optimal_for": "Core holdings, mean reversion"
            },
            "stock": {
                "description": "Individual Stocks",
                "examples": ["NVDA", "GOOGL", "AAPL", "TSLA", "MSFT", "AMD"],
                "volatility_profile": "Variable",
                "optimal_for": "Company-specific opportunities"
            }
        }
        
        return {
            "success": True,
            "data": {
                "supported_assets": supported_assets,
                "total_types": len(supported_assets)
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error fetching supported assets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/data/availability/{symbol}")
async def check_data_availability(symbol: str):
    """
    Check data availability for a symbol
    Reuses existing database infrastructure
    """
    try:
        logger.info(f"🔍 Checking data availability for {symbol}")
        
        # Get recent data
        recent_data = DatabaseQueryHelper.get_historical_data(symbol=symbol, limit=5)
        
        # Get total count
        all_data = DatabaseQueryHelper.get_historical_data(symbol=symbol)
        
        if not all_data:
            return {
                "success": True,
                "data": {
                    "symbol": symbol,
                    "available": False,
                    "total_records": 0,
                    "date_range": None,
                    "recent_data": []
                }
            }
        
        # Calculate date range
        dates = [record['date'] for record in all_data]
        start_date = min(dates)
        end_date = max(dates)
        
        # Convert to string if needed, or use directly if already date objects
        if isinstance(start_date, str):
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
        else:
            start_date_obj = start_date
            
        if isinstance(end_date, str):
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
        else:
            end_date_obj = end_date
        
        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "available": True,
                "total_records": len(all_data),
                "date_range": {
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "days_coverage": (end_date_obj - start_date_obj).days
                },
                "recent_data": recent_data
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error checking data availability for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def calculate_backtest_performance(historical_data: List[Dict], signals: List[Dict]) -> Dict:
    """
    Calculate performance metrics for backtest
    Simple implementation - can be enhanced
    """
    try:
        if not signals or not historical_data:
            return {"error": "Insufficient data for performance calculation"}
        
        # Create price lookup
        price_lookup = {record['date']: record['close'] for record in historical_data}
        
        # Calculate basic metrics
        buy_signals = [s for s in signals if s['signal'] == 'buy']
        sell_signals = [s for s in signals if s['signal'] == 'sell']
        hold_signals = [s for s in signals if s['signal'] == 'hold']
        
        # Simple return calculation (can be enhanced)
        total_return = 0.0
        winning_trades = 0
        losing_trades = 0
        
        for signal in buy_signals:
            signal_date = signal['date']
            entry_price = signal.get('price', 0)
            
            # Find next sell signal or end of data
            next_sell_date = None
            for future_signal in signals:
                if (future_signal['date'] > signal_date and 
                    future_signal['signal'] in ['sell', 'hold']):
                    next_sell_date = future_signal['date']
                    break
            
            if next_sell_date and next_sell_date in price_lookup:
                exit_price = price_lookup[next_sell_date]
                trade_return = (exit_price - entry_price) / entry_price * 100
                total_return += trade_return
                
                if trade_return > 0:
                    winning_trades += 1
                else:
                    losing_trades += 1
        
        total_trades = winning_trades + losing_trades
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        return {
            "total_return_pct": round(total_return, 2),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate_pct": round(win_rate, 2),
            "buy_signals": len(buy_signals),
            "sell_signals": len(sell_signals),
            "hold_signals": len(hold_signals),
            "period_return_pct": round(
                ((price_lookup.get(max(price_lookup.keys()), 0) - 
                  price_lookup.get(min(price_lookup.keys()), 0)) / 
                 price_lookup.get(min(price_lookup.keys()), 1)) * 100, 2
            ) if len(price_lookup) > 1 else 0
        }
        
    except Exception as e:
        logger.error(f"❌ Error calculating performance: {str(e)}")
        return {"error": f"Performance calculation failed: {str(e)}"}
