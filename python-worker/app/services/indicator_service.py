"""
Indicator calculation service
Computes all indicators and saves to database
Enhanced to use FMP technical indicators API when available
"""
from datetime import datetime, date
from typing import Dict, Any, Optional, List
import json

import pandas as pd

from app.database import db
from app.services.base import BaseService
from app.exceptions import IndicatorCalculationError, DatabaseError, ValidationError
from app.utils.validation import validate_symbol
from app.data_sources import get_data_source
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
        self.data_source = get_data_source()
    
    def calculate_indicators_with_fmp(self, symbol: str) -> bool:
        """
        Calculate indicators using FMP technical indicators API
        This is the preferred method when FMP is available as the data source
        
        Args:
            symbol: Stock symbol
            
        Returns:
            True if successful
        """
        try:
            self.logger.info(f"🔄 Calculating indicators for {symbol} using FMP API")

            from app.config import settings
            if not getattr(settings, "fmp_technical_indicators_enabled", True):
                self.logger.info(
                    f"FMP technical indicators disabled by config; calculating indicators locally for {symbol}"
                )
                return self.calculate_indicators(symbol)
            
            # Check if data source supports technical indicators
            if not hasattr(self.data_source, 'fetch_technical_indicators'):
                self.logger.warning(f"Data source {self.data_source.name} doesn't support technical indicators, falling back to local calculation")
                return self.calculate_indicators(symbol)
            
            # Fetch all technical indicators from FMP
            indicators_data = self.data_source.fetch_technical_indicators(symbol)
            
            if not indicators_data:
                self.logger.warning(f"No technical indicators data received for {symbol} from FMP")
                return self.calculate_indicators(symbol)  # Fallback to local calculation
            
            # Check if fallback was used
            fallback_used = indicators_data.pop('_fallback_used', False)
            fallback_source = indicators_data.pop('_fallback_source', None)
            primary_source = indicators_data.pop('_primary_source', None)
            
            if fallback_used:
                self.logger.warning(f"🔄 FALLBACK DETECTED: Used {fallback_source} instead of {primary_source} for {symbol}")
                # Log fallback usage to audit table
                self._log_fallback_usage(symbol, primary_source, fallback_source, "technical_indicators")
            
            # Store indicators in database
            success = self._store_fmp_indicators(symbol, indicators_data)

            # FMP may not provide MACD endpoints in the current client/source implementation.
            # Backfill missing MACD fields locally (derived from close prices) to avoid incorrect analysis.
            try:
                macd_missing = (
                    not indicators_data.get('macd')
                    or not indicators_data.get('macd_signal')
                    or not indicators_data.get('macd_hist')
                )
            except Exception:
                macd_missing = True

            if macd_missing:
                self.logger.warning(
                    f"⚠️ FMP did not return full MACD series for {symbol}; backfilling MACD locally from price history"
                )
                self.logger.info(f"🔄 Starting local MACD backfill for {symbol}")
                try:
                    self.logger.info(f"📊 Calling calculate_indicators() for {symbol} (MACD backfill)")
                    _local_ok = self.calculate_indicators(symbol)
                    self.logger.info(f"✅ Local MACD backfill completed for {symbol}: success={_local_ok}")
                    success = bool(success) and bool(_local_ok)
                    
                    # Verify MACD was actually stored
                    if _local_ok:
                        try:
                            from app.database import db
                            macd_check = db.execute_query(
                                """
                                SELECT date, macd, macd_signal, macd_hist
                                FROM indicators_daily
                                WHERE symbol = %s
                                ORDER BY date DESC
                                LIMIT 1
                                """,
                                [symbol],
                            )
                            if macd_check and macd_check[0].get('macd') is not None:
                                self.logger.info(
                                    f"✅ MACD verification passed for {symbol} ({macd_check[0].get('date')}): macd={macd_check[0].get('macd')}"
                                )
                            else:
                                latest_date = macd_check[0].get('date') if macd_check else None
                                self.logger.warning(
                                    f"⚠️ MACD verification incomplete for {symbol}: latest indicators_daily row has no macd (date={latest_date})"
                                )
                        except Exception as verify_e:
                            self.logger.error(f"❌ Failed to verify MACD for {symbol}: {verify_e}")
                    
                except Exception as e:
                    self.logger.error(f"❌ Failed local MACD backfill for {symbol}: {e}")
                    self.logger.error(f"🐛 Exception details:", exc_info=True)
                    success = False

            if success:
                source_used = fallback_source if fallback_used else "fmp_api"
                self.logger.info(f"✅ Successfully calculated and stored indicators for {symbol} using {source_used}")
                return True

            self.logger.error(f"❌ Failed to store indicators for {symbol}")
            return False
                
        except Exception as e:
            self.logger.error(f"❌ Error calculating FMP indicators for {symbol}: {e}")
            # Fallback to local calculation
            self.logger.info(f"Falling back to local indicator calculation for {symbol}")
            return self.calculate_indicators(symbol)
    
    def _log_fallback_usage(self, symbol: str, primary_source: str, fallback_source: str, operation: str):
        """Log fallback usage to audit table for monitoring"""
        try:
            from app.database import db
            from datetime import datetime
            
            # Insert audit event for fallback usage
            audit_query = """
                INSERT INTO data_ingestion_events (
                    run_id, symbol, operation, provider, level, 
                    message, created_at, context
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, NOW(), %s
                )
            """
            
            context = {
                "primary_source": primary_source,
                "fallback_source": fallback_source,
                "operation_type": operation,
                "fallback_reason": "primary_source_failed"
            }
            
            # Use a generic run_id for fallback tracking
            run_id = f"fallback_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{symbol[:4]}"
            
            db.execute_query(audit_query, (
                run_id,
                symbol,
                f"fallback_{operation}",
                fallback_source,
                "WARNING",
                f"Fallback activated: {fallback_source} used instead of {primary_source}",
                json.dumps(context)
            ))
            
            self.logger.info(f"📊 Fallback usage logged to audit table for {symbol}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to log fallback usage for {symbol}: {e}")
            # Don't fail the operation if audit logging fails
    
    def _store_fmp_indicators(self, symbol: str, indicators_data: Dict[str, List[Dict[str, Any]]]) -> bool:
        """
        Store FMP technical indicators data in the database
        
        Args:
            symbol: Stock symbol
            indicators_data: Dictionary of indicator data from FMP
            
        Returns:
            True if successful
        """
        try:
            stored_count = 0
            
            for indicator_name, data_points in indicators_data.items():
                if not data_points:
                    continue
                
                # Map FMP indicator names to database columns
                db_column = self._map_indicator_to_column(indicator_name)
                if not db_column:
                    self.logger.warning(f"Unknown indicator: {indicator_name}")
                    continue
                
                # Store each data point
                for point in data_points:
                    if not isinstance(point, dict):
                        continue
                    
                    # Extract date and value - FMP uses different field names
                    point_date = point.get('date')
                    
                    # FMP API uses indicator-specific field names (ema, sma, rsi, etc.)
                    # not a generic 'value' field
                    point_value = None
                    if indicator_name.startswith('ema_'):
                        point_value = point.get('ema')
                    elif indicator_name.startswith('sma_'):
                        point_value = point.get('sma')
                    elif indicator_name.startswith('wma_'):
                        point_value = point.get('wma')
                    elif indicator_name.startswith('dema_'):
                        point_value = point.get('dema')
                    elif indicator_name.startswith('tema_'):
                        point_value = point.get('tema')
                    elif indicator_name.startswith('rsi_'):
                        point_value = point.get('rsi')
                    elif indicator_name.startswith('stddev_'):
                        point_value = point.get('standardDeviation')
                    elif indicator_name.startswith('williams_'):
                        point_value = point.get('williams')
                    elif indicator_name.startswith('adx_'):
                        point_value = point.get('adx')
                    elif indicator_name in ('macd', 'macd_signal', 'macd_hist'):
                        # If MACD endpoints are supported/returned by the data source,
                        # prefer explicit keys but fall back to 'value'.
                        point_value = (
                            point.get('macd')
                            if indicator_name == 'macd' and point.get('macd') is not None
                            else point.get('signal')
                            if indicator_name == 'macd_signal' and point.get('signal') is not None
                            else point.get('histogram')
                            if indicator_name == 'macd_hist' and point.get('histogram') is not None
                            else point.get('value')
                        )
                    else:
                        # Generic fallback
                        point_value = point.get('value')
                    
                    if not point_date or point_value is None:
                        self.logger.debug(f"Skipping point - missing date or value: {point}")
                        continue
                    
                    # Convert date string to date object
                    if isinstance(point_date, str):
                        # Handle both "2026-01-21" and "2026-01-21 00:00:00" formats
                        if 'T' in point_date:
                            # ISO format: "2026-01-21T00:00:00"
                            point_date = datetime.strptime(point_date.split('T')[0], '%Y-%m-%d').date()
                        elif ' ' in point_date:
                            # Space format: "2026-01-21 00:00:00"
                            point_date = datetime.strptime(point_date.split(' ')[0], '%Y-%m-%d').date()
                        else:
                            # Simple format: "2026-01-21"
                            point_date = datetime.strptime(point_date, '%Y-%m-%d').date()
                    
                    # Delete existing records and insert new ones (to update data_source)
                    delete_query = """
                        DELETE FROM indicators_daily 
                        WHERE symbol = $1 AND date = $2 AND indicator_name = $3
                          AND interval = '1d'
                    """
                    db.execute_update_positional(delete_query, [symbol.upper(), point_date, indicator_name])
                    
                    # Insert new record
                    insert_query = """
                        INSERT INTO indicators_daily (
                            symbol, date, interval, as_of_ts, indicator_name, indicator_value, data_source, 
                            created_at, updated_at
                        ) VALUES (
                            $1, $2, '1d', $3::timestamptz, $4, $5, 'fmp_api',
                            NOW(), NOW()
                        )
                    """
                    
                    # Use positional parameters for INSERT
                    result = db.execute_update_positional(insert_query, [
                        symbol.upper(), 
                        point_date, 
                        datetime.combine(point_date, datetime.min.time()).isoformat(),
                        indicator_name,  # Use the indicator name directly
                        float(point_value)
                    ])
                    stored_count += 1
            
            self.logger.info(f"✅ Stored {stored_count} FMP indicator data points for {symbol}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error storing FMP indicators for {symbol}: {e}")
            return False
    
    def _map_indicator_to_column(self, indicator_name: str) -> Optional[str]:
        """
        Map FMP indicator names to database column names
        
        Args:
            indicator_name: FMP indicator name
            
        Returns:
            Database column name or None if not found
        """
        mapping = {
            'ema_20': 'ema_20',
            'ema_50': 'ema_50',
            'sma_20': 'sma_20',
            'sma_50': 'sma_50',
            'sma_200': 'sma_200',
            'wma_20': 'wma_20',
            'dema_20': 'dema_20',
            'tema_20': 'tema_20',
            'rsi_14': 'rsi_14',
            'macd': 'macd',
            'macd_signal': 'macd_signal',
            'macd_hist': 'macd_hist',
            'stddev_20': 'stddev_20',
            'williams_14': 'williams_r',
            'adx_14': 'adx'
        }
        
        return mapping.get(indicator_name.lower())
    
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
            self.logger.info(f"🔄 Starting calculate_indicators for {symbol}")
            
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
                self.logger.info(f"📊 Fetching historical data for {symbol} from database")
                from app.utils.database_helper import DatabaseQueryHelper
                
                data = DatabaseQueryHelper.get_historical_data(symbol)
                
                if not data:
                    self.logger.error(f"❌ No market data found for {symbol} in database")
                    raise IndicatorCalculationError(
                        f"No market data found for {symbol}",
                        details={'symbol': symbol}
                    )
                
                self.logger.info(f"📈 Retrieved {len(data)} rows of market data for {symbol}")
                
                # Convert to DataFrame
                df = pd.DataFrame(data)
                if df.empty:
                    self.logger.error(f"❌ Empty DataFrame for {symbol} after fetching from database")
                    raise IndicatorCalculationError(
                        f"Empty DataFrame for {symbol} after fetching from database",
                        details={'symbol': symbol}
                    )
                
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                self.logger.info(f"📊 Created DataFrame for {symbol}: {len(df)} rows, date range {df.index[0]} to {df.index[-1]}")
            
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
            self.logger.info(f"📈 Calculating momentum indicators for {symbol}")
            rsi = calculate_rsi(close)
            self.logger.debug(f"📊 RSI calculated for {symbol}: {len(rsi)} points")
            
            macd_line, macd_signal, macd_histogram = calculate_macd(close)
            self.logger.info(f"📊 MACD calculated for {symbol}: line={len(macd_line)}, signal={len(macd_signal)}, hist={len(macd_histogram)} points")
            
            # Check MACD values
            latest_macd = macd_line.iloc[-1] if len(macd_line) > 0 and not pd.isna(macd_line.iloc[-1]) else None
            latest_signal = macd_signal.iloc[-1] if len(macd_signal) > 0 and not pd.isna(macd_signal.iloc[-1]) else None
            latest_hist = macd_histogram.iloc[-1] if len(macd_histogram) > 0 and not pd.isna(macd_histogram.iloc[-1]) else None
            
            self.logger.info(f"📊 Latest MACD values for {symbol}: macd={latest_macd}, signal={latest_signal}, hist={latest_hist}")
            
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
                        if isinstance(val, pd.Series):
                            if val.empty:
                                return default
                            val = val.iloc[-1]
                        return None if pd.isna(val) else val
                    return default
                except (KeyError, IndexError):
                    return default

            latest_idx = df.index[-1]
            trade_date = latest_idx.date() if hasattr(latest_idx, 'date') else pd.Timestamp(latest_idx).date()

            # Store indicators in WIDE format (direct columns) for compatibility with universal signal API
            # This matches the expected schema used by the query in universal_backtest_api.py
            self.logger.info(f"💾 Preparing wide format data for {symbol}")
            wide_format_data = {
                'sma_50': safe_get(sma50, latest_idx),
                'sma_200': safe_get(sma200, latest_idx),
                'ema_20': safe_get(ema20, latest_idx),
                'rsi_14': safe_get(rsi, latest_idx),
                'macd': safe_get(macd_line, latest_idx),
                'macd_signal': safe_get(macd_signal, latest_idx),
                'macd_hist': safe_get(macd_histogram, latest_idx),
                'atr': safe_get(atr, latest_idx),
                'bb_width': (
                    (float(safe_get(bb_upper, latest_idx)) - float(safe_get(bb_lower, latest_idx))) / float(safe_get(bb_middle, latest_idx))
                    if safe_get(bb_lower, latest_idx) is not None and safe_get(bb_upper, latest_idx) is not None and safe_get(bb_middle, latest_idx) not in (None, 0)
                    else None
                ),
                'signal': strategy_result.signal,
                'confidence_score': float(strategy_result.confidence) if strategy_result and strategy_result.confidence is not None else None,
            }
            
            self.logger.info(f"📊 Wide format data prepared for {symbol}: {len([v for v in wide_format_data.values() if v is not None])} non-null values")
            self.logger.debug(f"📊 Wide format data for {symbol}: macd={wide_format_data['macd']}, macd_signal={wide_format_data['macd_signal']}, macd_hist={wide_format_data['macd_hist']}")
            
            # Build dynamic UPDATE query for wide format
            update_columns = [col for col, val in wide_format_data.items() if val is not None]
            
            self.logger.info(f"📊 Will update {len(update_columns)} columns for {symbol}: {', '.join(update_columns)}")
            
            if update_columns:
                # Use DELETE + INSERT approach since wide format doesn't have proper unique constraint
                self.logger.info(f"💾 Storing indicators in wide format for {symbol} on {trade_date}")
                
                # First delete any existing wide format record for this symbol/date
                delete_query = """
                    DELETE FROM indicators_daily 
                    WHERE symbol = :symbol AND date = :date
                      AND interval = '1d'
                    AND (sma_50 IS NOT NULL OR ema_20 IS NOT NULL OR rsi_14 IS NOT NULL OR macd IS NOT NULL)
                """
                
                try:
                    db.execute_update(delete_query, {"symbol": symbol, "date": trade_date})
                    self.logger.debug(f"🗑️ Deleted existing wide format records for {symbol} on {trade_date}")
                except Exception as e:
                    self.logger.warning(f"⚠️ Failed to delete existing records for {symbol}: {e}")
                
                # Create INSERT query for wide format
                wide_query = f"""
                    INSERT INTO indicators_daily 
                    (symbol, date, interval, as_of_ts, {', '.join(update_columns)}, data_source, created_at, updated_at)
                    VALUES (:symbol, :date, '1d', :as_of_ts, {', '.join([f':{col}' for col in update_columns])}, :data_source, NOW(), NOW())
                """
                
                # Prepare parameters for wide format
                wide_params = {
                    "symbol": symbol,
                    "date": trade_date,
                    "as_of_ts": datetime.combine(trade_date, datetime.min.time()),
                    "data_source": "calculated"
                }
                
                # Add indicator values to parameters
                for col in update_columns:
                    value = wide_format_data[col]
                    wide_params[col] = float(value) if isinstance(value, (int, float)) and not pd.isna(value) else None
                
                try:
                    db.execute_update(wide_query, wide_params)
                    self.logger.info(f"✅ Stored {len(update_columns)} indicators in wide format for {symbol} on {trade_date}")
                    self.logger.debug(f"📊 Stored MACD values for {symbol}: macd={wide_params.get('macd')}, macd_signal={wide_params.get('macd_signal')}, macd_hist={wide_params.get('macd_hist')}")
                    return True
                except Exception as e:
                    self.logger.error(f"❌ Failed to store wide format indicators for {symbol}: {e}")
                    self.logger.error(f"🐛 Query: {wide_query}")
                    self.logger.error(f"🐛 Parameters: {wide_params}")
                    return False
            else:
                self.logger.warning(f"⚠️ No valid indicator values to store for {symbol}")
                return False
            
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
            WHERE symbol = :symbol
              AND interval = '1d'
            ORDER BY as_of_ts DESC
            LIMIT 1
        """
        
        results = db.execute_query(query, {"symbol": symbol})
        return results[0] if results else None

