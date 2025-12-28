"""
Swing Trend Following Strategy
Multi-timeframe trend following for swing trades
Industry Standard: EMA crossover with trend confirmation
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

from app.strategies.swing.base import BaseSwingStrategy, SwingStrategyResult
from app.indicators.moving_averages import calculate_ema, calculate_sma
from app.indicators.momentum import calculate_rsi, calculate_macd
from app.indicators.volatility import calculate_atr
from app.exceptions import ValidationError

logger = logging.getLogger(__name__)


class SwingTrendStrategy(BaseSwingStrategy):
    """
    Swing Trend Following Strategy
    
    Logic:
    1. Weekly trend confirmation (50-week SMA)
    2. Daily entry signals (9/21 EMA crossover)
    3. RSI momentum (50-70 range)
    4. MACD confirmation
    5. Volume confirmation
    
    Industry Standard: Multi-timeframe trend following
    """
    
    def get_name(self) -> str:
        return "swing_trend"
    
    def get_description(self) -> str:
        return "Multi-timeframe trend following strategy for swing trades (2-10 days)"
    
    def generate_swing_signal(
        self,
        daily_data: pd.DataFrame,
        weekly_data: Optional[pd.DataFrame] = None,
        indicators: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> SwingStrategyResult:
        """
        Generate swing trend signal
        
        Args:
            daily_data: Daily OHLCV data (required)
            weekly_data: Weekly OHLCV data (optional, for trend confirmation)
            indicators: Pre-calculated indicators (optional)
            context: Additional context (account balance, etc.)
        
        Returns:
            SwingStrategyResult with signal
        
        Raises:
            ValidationError: If inputs are invalid
        """
        if daily_data is None or daily_data.empty:
            raise ValidationError("Daily data is required and cannot be empty")
        
        if len(daily_data) < 50:
            return SwingStrategyResult(
                signal='HOLD',
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                position_size=0.0,
                confidence=0.0,
                timeframe='daily',
                entry_reason="Insufficient daily data (need at least 50 periods)"
            )
        
        # Normalize daily data
        daily_data = self._normalize_dataframe(daily_data)
        
        # Get latest data
        latest = daily_data.iloc[-1]
        close = float(latest['close'])
        
        # Calculate indicators if not provided
        if indicators is None:
            try:
                indicators = self._calculate_indicators(daily_data)
            except Exception as e:
                # Get symbol from context if available, otherwise use placeholder
                symbol = context.get('symbol', 'unknown') if context else 'unknown'
                logger.error(f"Error calculating indicators for {symbol}: {e}", exc_info=True)
                return SwingStrategyResult(
                    signal='HOLD',
                    entry_price=0.0,
                    stop_loss=0.0,
                    take_profit=0.0,
                    position_size=0.0,
                    confidence=0.0,
                    timeframe='daily',
                    entry_reason=f"Failed to calculate indicators: {str(e)}"
                )
        
        # Weekly trend confirmation
        weekly_trend = self._get_weekly_trend(weekly_data)
        
        # Daily signals
        ema9 = indicators.get('ema9')
        ema21 = indicators.get('ema21')
        sma50 = indicators.get('sma50')
        rsi = indicators.get('rsi')
        macd = indicators.get('macd')
        macd_signal = indicators.get('macd_signal')
        volume_avg = indicators.get('volume_avg')
        atr = indicators.get('atr')
        
        # Validate indicators - check if they exist and have valid (non-NaN) values
        def has_valid_data(series, min_valid=2):
            """Check if series has at least min_valid non-NaN values"""
            if series is None:
                return False
            if not isinstance(series, pd.Series):
                return False
            if len(series) < min_valid:
                return False
            # Check if we have at least min_valid non-NaN values
            valid_count = series.notna().sum()
            return valid_count >= min_valid
        
        if not has_valid_data(ema9, 2) or not has_valid_data(ema21, 2):
            # Get symbol from context if available, otherwise use placeholder
            symbol = context.get('symbol', 'unknown') if context else 'unknown'
            
            # Calculate detailed diagnostics
            total_candles = len(daily_data)
            ema9_valid_count = ema9.notna().sum() if ema9 is not None and isinstance(ema9, pd.Series) else 0
            ema21_valid_count = ema21.notna().sum() if ema21 is not None and isinstance(ema21, pd.Series) else 0
            
            # Count NaN rows in critical columns
            critical_cols = ['close', 'high', 'low', 'open', 'volume']
            available_cols = [col for col in critical_cols if col in daily_data.columns]
            nan_rows = 0
            if available_cols:
                nan_rows = daily_data[available_cols].isna().any(axis=1).sum()
            
            # Build detailed reason message
            reason_parts = [
                f"Total candles: {total_candles}",
                f"Valid EMA9 points: {ema9_valid_count} (need ≥2)",
                f"Valid EMA21 points: {ema21_valid_count} (need ≥2)",
                f"Rows with NaN in critical columns: {nan_rows}"
            ]
            
            if nan_rows > 0:
                reason_parts.append(f"⚠️ {nan_rows} rows dropped due to NaN values")
            
            reason_parts.append("💡 The EMA series derived from the candles don't have enough valid points at the tail (due to NaNs/dropped rows/data quality issues), so failing safe with HOLD.")
            reason_parts.append("💡 Re-fetch historical data with indicators for this symbol to fix it.")
            
            detailed_reason = " | ".join(reason_parts)
            
            logger.warning(f"Insufficient indicator data for {symbol}: "
                          f"ema9 valid={has_valid_data(ema9, 2)} ({ema9_valid_count} valid), "
                          f"ema21 valid={has_valid_data(ema21, 2)} ({ema21_valid_count} valid), "
                          f"data length={total_candles}, NaN rows={nan_rows}")
            
            return SwingStrategyResult(
                signal='HOLD',
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                position_size=0.0,
                confidence=0.0,
                timeframe='daily',
                entry_reason=detailed_reason
            )
        
        # Check for EMA crossover
        ema9_current = float(ema9.iloc[-1])
        ema9_prev = float(ema9.iloc[-2])
        ema21_current = float(ema21.iloc[-1])
        ema21_prev = float(ema21.iloc[-2])
        
        # Bullish crossover
        bullish_cross = (ema9_prev <= ema21_prev) and (ema9_current > ema21_current)
        
        # Entry conditions
        price_above_sma50 = sma50 is not None and len(sma50) > 0 and close > float(sma50.iloc[-1])
        rsi_healthy = rsi is not None and len(rsi) > 0 and 50 <= float(rsi.iloc[-1]) <= 70
        macd_positive = (
            macd is not None and macd_signal is not None and
            len(macd) > 0 and len(macd_signal) > 0 and
            float(macd.iloc[-1]) > float(macd_signal.iloc[-1])
        )
        volume_confirmed = (
            volume_avg is not None and len(volume_avg) > 0 and
            float(latest['volume']) > float(volume_avg.iloc[-1])
        )
        
        # Generate BUY signal
        if bullish_cross and price_above_sma50 and rsi_healthy and macd_positive:
            # Calculate entry/exit levels
            entry_price = close
            
            if atr is not None and len(atr) > 0:
                atr_value = float(atr.iloc[-1])
                stop_loss = entry_price - (2 * atr_value)
                take_profit = entry_price + (6 * atr_value)  # 3:1 risk-reward
            else:
                stop_loss = entry_price * 0.98  # 2% stop
                take_profit = entry_price * 1.06  # 6% target
            
            # Calculate confidence
            confidence = 0.6  # Base confidence
            if weekly_trend == 'bullish':
                confidence += 0.2
            if volume_confirmed:
                confidence += 0.1
            if rsi is not None and len(rsi) > 0 and float(rsi.iloc[-1]) > 55:
                confidence += 0.1
            
            confidence = min(confidence, 1.0)
            
            risk_reward = self.calculate_risk_reward(entry_price, stop_loss, take_profit)
            
            # Calculate position size if account balance provided
            position_size = 0.01  # Default 1%
            if context and 'account_balance' in context:
                position_size = self.calculate_position_size(
                    entry_price,
                    stop_loss,
                    float(context['account_balance'])
                )
            
            rsi_value = float(rsi.iloc[-1]) if rsi is not None and len(rsi) > 0 else 0
            
            return SwingStrategyResult(
                signal='BUY',
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size=position_size,
                confidence=confidence,
                timeframe='daily',
                entry_reason=f"EMA crossover, weekly trend: {weekly_trend}, RSI: {rsi_value:.1f}",
                risk_reward_ratio=risk_reward,
                max_hold_days=self.max_hold_days
            )
        
        # Exit conditions
        bearish_cross = (ema9_prev >= ema21_prev) and (ema9_current < ema21_current)
        rsi_overbought = rsi is not None and len(rsi) > 0 and float(rsi.iloc[-1]) > 75
        
        if bearish_cross or rsi_overbought:
            exit_reason = "EMA bearish cross" if bearish_cross else "RSI overbought"
            
            return SwingStrategyResult(
                signal='SELL',
                entry_price=close,
                stop_loss=0.0,
                take_profit=0.0,
                position_size=0.0,
                confidence=0.7,
                timeframe='daily',
                entry_reason="Exit signal",
                exit_reason=exit_reason
            )
        
        return SwingStrategyResult(
            signal='HOLD',
            entry_price=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            position_size=0.0,
            confidence=0.0,
            timeframe='daily',
            entry_reason="No clear signal"
        )
    
    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize dataframe columns
        
        Handles various column name formats from different data sources
        """
        if df is None or df.empty:
            raise ValidationError("DataFrame is None or empty")
        
        # Make a copy to avoid modifying original
        df = df.copy()
        
        # Normalize column names to lowercase
        df.columns = [col.lower() for col in df.columns]
        
        # Ensure date column exists
        if 'date' not in df.columns:
            # Check if date is in index
            if df.index.name and df.index.name.lower() == 'date':
                df = df.reset_index()
                if 'date' not in df.columns:
                    # Try to find date-like column
                    for col in df.columns:
                        if 'date' in col.lower() or 'time' in col.lower():
                            df = df.rename(columns={col: 'date'})
                            break
            else:
                # Check if any column looks like a date
                for col in df.columns:
                    if 'date' in col.lower() or 'time' in col.lower():
                        df = df.rename(columns={col: 'date'})
                        break
        
        # If still no date column, try to infer from index
        if 'date' not in df.columns:
            if isinstance(df.index, pd.DatetimeIndex):
                df = df.reset_index()
                df = df.rename(columns={df.columns[0]: 'date'})
            else:
                logger.warning(f"No date column found. Available columns: {list(df.columns)}")
                # Create a dummy date column from index
                df = df.reset_index()
                if 'date' not in df.columns:
                    df['date'] = pd.date_range(start='2020-01-01', periods=len(df), freq='D')
        
        # Ensure required columns exist (case-insensitive)
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = []
        for col in required_cols:
            if col not in df.columns:
                # Try to find case-insensitive match
                found = False
                for df_col in df.columns:
                    if df_col.lower() == col.lower():
                        df = df.rename(columns={df_col: col})
                        found = True
                        break
                if not found:
                    missing_cols.append(col)
        
        if missing_cols:
            raise ValidationError(f"Missing required columns: {missing_cols}. Available: {list(df.columns)}")
        
        # Ensure numeric columns are numeric
        for col in required_cols:
            if not pd.api.types.is_numeric_dtype(df[col]):
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Remove rows with NaN in required columns
        initial_len = len(df)
        df = df.dropna(subset=required_cols)
        if len(df) < initial_len:
            logger.warning(f"Removed {initial_len - len(df)} rows with NaN values")
        
        # Sort by date
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.sort_values('date').reset_index(drop=True)
        
        # Validate we have enough data after normalization
        if len(df) < 50:
            raise ValidationError(f"Insufficient data after normalization: {len(df)} rows (need at least 50)")
        
        logger.debug(f"✅ Normalized DataFrame: {len(df)} rows, columns: {list(df.columns)}")
        
        return df
    
    def _get_weekly_trend(self, weekly_data: Optional[pd.DataFrame]) -> str:
        """
        Get weekly trend
        
        Returns:
            'bullish', 'bearish', or 'neutral'
        """
        if weekly_data is None or weekly_data.empty:
            return 'neutral'
        
        if len(weekly_data) < 50:
            return 'neutral'
        
        try:
            weekly_data = self._normalize_dataframe(weekly_data)
            weekly_sma50 = calculate_sma(weekly_data['close'], 50)
            
            if len(weekly_sma50) == 0:
                return 'neutral'
            
            current_price = float(weekly_data['close'].iloc[-1])
            sma50_value = float(weekly_sma50.iloc[-1])
            
            if current_price > sma50_value:
                return 'bullish'
            elif current_price < sma50_value:
                return 'bearish'
            else:
                return 'neutral'
        except Exception as e:
            logger.warning(f"Error calculating weekly trend: {e}")
            return 'neutral'
    
    def _calculate_indicators(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate required indicators
        
        Args:
            data: Daily OHLCV data
        
        Returns:
            Dictionary of indicators
        
        Raises:
            ValidationError: If data is invalid or calculation fails
        """
        # Validate required columns
        required_cols = ['close', 'high', 'low', 'volume']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            raise ValidationError(f"Missing required columns: {missing_cols}. Available: {list(data.columns)}")
        
        # Ensure we have enough data
        if len(data) < 50:
            raise ValidationError(f"Insufficient data: need at least 50 periods, have {len(data)}")
        
        close = data['close']
        high = data['high']
        low = data['low']
        volume = data['volume']
        
        # Validate data types
        for col_name, series in [('close', close), ('high', high), ('low', low), ('volume', volume)]:
            if not pd.api.types.is_numeric_dtype(series):
                try:
                    series = pd.to_numeric(series, errors='coerce')
                except Exception as e:
                    raise ValidationError(f"Column '{col_name}' is not numeric and cannot be converted: {e}")
        
        indicators = {}
        
        try:
            # Ensure close is numeric and has valid values
            close_numeric = pd.to_numeric(close, errors='coerce')
            valid_close_count = close_numeric.notna().sum()
            
            if valid_close_count < 21:
                raise ValidationError(
                    f"Insufficient valid close prices: {valid_close_count} valid values, need at least 21 for EMA21"
                )
            
            # Calculate EMAs (need at least 21 periods for EMA21)
            indicators['ema9'] = calculate_ema(close_numeric, 9)
            indicators['ema21'] = calculate_ema(close_numeric, 21)
            
            # Validate EMAs have valid data at the tail (needed for signal generation)
            ema9_valid_tail = indicators['ema9'].tail(2).notna().sum()
            ema21_valid_tail = indicators['ema21'].tail(2).notna().sum()
            
            if ema9_valid_tail < 2 or ema21_valid_tail < 2:
                raise ValidationError(
                    f"EMA calculations insufficient at tail: EMA9 has {ema9_valid_tail}/2 valid values, "
                    f"EMA21 has {ema21_valid_tail}/2 valid values. Need at least 2 valid values at tail for signal generation."
                )
            
            # Log EMA validation
            ema9_total_valid = indicators['ema9'].notna().sum()
            ema21_total_valid = indicators['ema21'].notna().sum()
            logger.debug(
                f"✅ EMA validation: EMA9={ema9_total_valid} valid, EMA21={ema21_total_valid} valid, "
                f"tail: EMA9={ema9_valid_tail}/2, EMA21={ema21_valid_tail}/2"
            )
            
            # Calculate other indicators
            indicators['sma50'] = calculate_sma(close, 50)
            indicators['rsi'] = calculate_rsi(close, 14)
            
            macd_line, signal_line, histogram = calculate_macd(close)
            indicators['macd'] = macd_line
            indicators['macd_signal'] = signal_line
            indicators['macd_histogram'] = histogram
            
            indicators['atr'] = calculate_atr(high, low, close, 14)
            indicators['volume_avg'] = volume.rolling(20).mean()
            
            logger.debug(f"✅ Calculated indicators: ema9 valid={indicators['ema9'].notna().sum()}, "
                        f"ema21 valid={indicators['ema21'].notna().sum()}, "
                        f"data length={len(data)}")
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}", exc_info=True)
            raise ValidationError(f"Failed to calculate indicators: {str(e)}") from e
        
        return indicators

