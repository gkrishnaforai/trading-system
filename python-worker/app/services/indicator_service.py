"""
Indicator calculation service
Computes all indicators and saves to database
"""
from datetime import datetime, date
from typing import Dict, Any, Optional
import json

import pandas as pd

from app.database import db
from app.services.base import BaseService
from app.exceptions import IndicatorCalculationError, DatabaseError, ValidationError
from app.utils.validation import validate_symbol
from app.indicators import (
    calculate_ma7, calculate_ma21, calculate_sma50, calculate_ema20,
    calculate_ema50, calculate_sma200,
    calculate_rsi, calculate_macd, calculate_momentum_score,
    calculate_atr, calculate_bollinger_bands,
    detect_long_term_trend, detect_medium_term_trend
)
from app.indicators.moving_averages import calculate_ema, calculate_sma
from app.indicators.signals import (
    generate_signal, calculate_pullback_zones, calculate_stop_loss
)


class IndicatorService(BaseService):
    """
    Service for calculating and storing indicators
    
    SOLID: Single Responsibility - calculates and stores indicators
    """
    
    def __init__(self):
        """Initialize indicator service"""
        super().__init__()
    
    def calculate_indicators(self, symbol: str, data: Optional[pd.DataFrame] = None) -> bool:
        """
        Calculate all indicators for a symbol and save to database
        
        Industry Standard: 
        - Indicators MUST be calculated after every price data load
        - Indicators are RECOMPUTED daily from fresh price data (never use stale indicators)
        - Indicators are stored for performance/caching, but always recomputed from source
        
        Key Principle: Raw data → Derived data (indicators) → Signals
        
        Args:
            symbol: Stock symbol
            data: Optional DataFrame with price data (if None, fetches from database)
        
        Returns:
            True if successful
        
        Raises:
            ValidationError: If symbol is invalid
            IndicatorCalculationError: If calculation fails
        
        Note: Indicators are stored in indicators_daily for performance/caching,
        but they are ALWAYS recomputed from fresh price data. Never rely on stale indicators.
            DatabaseError: If database operation fails
        """
        # Validate symbol
        if not validate_symbol(symbol):
            raise ValidationError(f"Invalid symbol: {symbol}", details={'symbol': symbol})
        
        try:
            # Use provided data if available, otherwise fetch from database
            if data is not None and not data.empty:
                # Use provided DataFrame (e.g., from validated/cleaned data)
                df = data.copy()
                self.logger.debug(f"Using provided DataFrame for {symbol}: {len(df)} rows")
                
                # Ensure date is index (if not already)
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                    df.set_index('date', inplace=True)
                elif df.index.name != 'date' and not isinstance(df.index, pd.DatetimeIndex):
                    # If index is not date, try to convert
                    df.index = pd.to_datetime(df.index)
            else:
                # Fetch raw market data from database using helper
                from app.utils.database_helper import DatabaseQueryHelper
                
                data = DatabaseQueryHelper.get_historical_data(symbol)
                
                if not data:
                    raise IndicatorCalculationError(
                        f"No market data found for {symbol}",
                        details={'symbol': symbol}
                    )
                
                # Convert to DataFrame
                df = pd.DataFrame(data)
                if df.empty:
                    raise IndicatorCalculationError(
                        f"Empty DataFrame for {symbol} after fetching from database",
                        details={'symbol': symbol}
                    )
                
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
            
            # Validate we have required columns
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                raise IndicatorCalculationError(
                    f"Missing required columns for {symbol}: {missing_cols}",
                    details={'symbol': symbol, 'available_columns': list(df.columns)}
                )
            
            # Calculate moving averages
            close = df['close']
            
            # Log data availability for debugging
            self.logger.debug(f"Calculating indicators for {symbol}: {len(df)} data points, "
                             f"date range: {df.index[0]} to {df.index[-1]}")
            
            # Helper function to align Series with DataFrame index
            def align_series(series, target_index):
                """Align series with target index, filling missing values with NaN"""
                if series is None:
                    return pd.Series([None] * len(target_index), index=target_index, dtype=float)
                if len(series) == 0:
                    return pd.Series([None] * len(target_index), index=target_index, dtype=float)
                # Reindex to match target index
                aligned = series.reindex(target_index)
                return aligned
            
            ma7 = calculate_ma7(close)
            ma21 = calculate_ma21(close)
            sma50 = calculate_sma50(close)
            sma100 = calculate_sma(close, 100)  # Industry standard: intermediate trend
            ema9 = calculate_ema(close, 9)  # Fast momentum (9/21 pair)
            ema12 = calculate_ema(close, 12)  # MACD base
            ema20 = calculate_ema20(close)  # Short-term momentum
            ema21 = calculate_ema(close, 21)  # Fast momentum (9/21 pair)
            ema26 = calculate_ema(close, 26)  # MACD base
            ema50 = calculate_ema50(close)  # Medium-term trend
            sma200 = calculate_sma200(close)  # Long-term regime
            
            # Calculate momentum indicators
            rsi = calculate_rsi(close)
            macd_line, macd_signal, macd_histogram = calculate_macd(close)
            
            # Calculate volatility indicators
            atr = calculate_atr(df['high'], df['low'], df['close'])
            bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(close)
            
            # Calculate volume moving average
            volume = df['volume']
            volume_ma = volume.rolling(window=20).mean()
            
            # Calculate trend
            long_term_trend = detect_long_term_trend(close, sma200)
            medium_term_trend = detect_medium_term_trend(ema20, sma50)
            
            # Calculate momentum score
            momentum_score = calculate_momentum_score(
                close, rsi, macd_histogram, volume, volume_ma
            )
            
            # Generate signals using strategy system
            from app.services.strategy_service import StrategyService
            from app.strategies import DEFAULT_STRATEGY
            
            strategy_service = StrategyService()
            
            # Prepare indicators dictionary for strategy
            indicators_dict = {
                'price': close,
                'close': close,
                'ma7': ma7,
                'ma21': ma21,
                'sma50': sma50,
                'sma100': sma100,
                'ema9': ema9,
                'ema12': ema12,
                'ema20': ema20,
                'ema21': ema21,
                'ema26': ema26,
                'ema50': ema50,
                'sma200': sma200,
                'macd': macd_line,
                'macd_line': macd_line,
                'macd_signal': macd_signal,
                'macd_histogram': macd_histogram,
                'rsi': rsi,
                'volume': volume,
                'volume_ma': volume_ma,
                'long_term_trend': long_term_trend,
                'medium_term_trend': medium_term_trend,
                'atr': atr,
            }
            
            # Execute default strategy (can be overridden per user/portfolio)
            strategy_result = strategy_service.execute_strategy(
                DEFAULT_STRATEGY,
                indicators_dict,
                market_data=df,
                context={'symbol': symbol}
            )
            
            # Convert StrategyResult to pandas Series for compatibility
            signal = pd.Series([strategy_result.signal] * len(close), index=df.index)
            
            # Calculate pullback zones
            pullback_lower, pullback_upper = calculate_pullback_zones(
                close, ema20, atr, long_term_trend
            )
            
            # Align pullback zones and momentum score
            pullback_lower = align_series(pullback_lower, df.index) if isinstance(pullback_lower, pd.Series) else pd.Series([None] * len(df.index), index=df.index)
            pullback_upper = align_series(pullback_upper, df.index) if isinstance(pullback_upper, pd.Series) else pd.Series([None] * len(df.index), index=df.index)
            
            # Ensure momentum_score is aligned
            momentum_score = align_series(momentum_score, df.index)
            
            def safe_get(series, idx, default=None):
                try:
                    if idx in series.index:
                        val = series.loc[idx]
                        return None if pd.isna(val) else val
                    return default
                except (KeyError, IndexError):
                    return default

            latest_idx = df.index[-1]
            trade_date = latest_idx.date() if hasattr(latest_idx, 'date') else pd.Timestamp(latest_idx).date()

            params = {
                "symbol": symbol,
                "trade_date": trade_date,
                "sma_50": float(safe_get(sma50, latest_idx)) if safe_get(sma50, latest_idx) is not None else None,
                "sma_200": float(safe_get(sma200, latest_idx)) if safe_get(sma200, latest_idx) is not None else None,
                "ema_20": float(safe_get(ema20, latest_idx)) if safe_get(ema20, latest_idx) is not None else None,
                "rsi_14": float(safe_get(rsi, latest_idx)) if safe_get(rsi, latest_idx) is not None else None,
                "macd": float(safe_get(macd_line, latest_idx)) if safe_get(macd_line, latest_idx) is not None else None,
                "macd_signal": float(safe_get(macd_signal, latest_idx)) if safe_get(macd_signal, latest_idx) is not None else None,
                "macd_hist": float(safe_get(macd_histogram, latest_idx)) if safe_get(macd_histogram, latest_idx) is not None else None,
                "signal": strategy_result.signal,
                "confidence_score": float(strategy_result.confidence) if strategy_result and strategy_result.confidence is not None else None,
            }

            query = """
                INSERT INTO indicators_daily
                (stock_symbol, trade_date, sma_50, sma_200, ema_20, rsi_14, macd, macd_signal, macd_hist, signal, confidence_score)
                VALUES (:symbol, :trade_date, :sma_50, :sma_200, :ema_20, :rsi_14, :macd, :macd_signal, :macd_hist, :signal, :confidence_score)
                ON CONFLICT (stock_symbol, trade_date)
                DO UPDATE SET
                  sma_50 = EXCLUDED.sma_50,
                  sma_200 = EXCLUDED.sma_200,
                  ema_20 = EXCLUDED.ema_20,
                  rsi_14 = EXCLUDED.rsi_14,
                  macd = EXCLUDED.macd,
                  macd_signal = EXCLUDED.macd_signal,
                  macd_hist = EXCLUDED.macd_hist,
                  signal = EXCLUDED.signal,
                  confidence_score = EXCLUDED.confidence_score,
                  updated_at = NOW()
            """

            db.execute_update(query, params)

            self.log_info(
                f"✅ Calculated and saved daily indicators for {symbol}",
                context={"symbol": symbol, "trade_date": str(trade_date)},
            )
            return True
            
        except (ValidationError, IndicatorCalculationError) as e:
            # Re-raise validation and calculation errors
            raise
        except Exception as e:
            self.log_error(f"Unexpected error calculating indicators", e,
                         context={'symbol': symbol})
            raise IndicatorCalculationError(
                f"Failed to calculate indicators for {symbol}: {str(e)}",
                details={'symbol': symbol}
            ) from e
    
    def get_latest_indicators(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest indicators for a symbol"""
        query = """
            SELECT * FROM indicators_daily
            WHERE stock_symbol = :symbol
            ORDER BY trade_date DESC
            LIMIT 1
        """
        
        results = db.execute_query(query, {"symbol": symbol})
        return results[0] if results else None

