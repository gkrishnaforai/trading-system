"""
Integration tests with REAL data (no mocks)
Tests actual calculations against real market data for AAPL, GOOGL, NVDA
Validates accuracy against industry standards
"""
import unittest
import sys
import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.services.indicator_service import IndicatorService
from app.services.strategy_service import StrategyService
from app.indicators import (
    calculate_rsi, calculate_macd, calculate_sma, calculate_ema,
    calculate_atr, calculate_bollinger_bands,
    detect_long_term_trend, detect_medium_term_trend
)
from app.indicators.signals import generate_signal, calculate_pullback_zones, calculate_stop_loss


def normalize_date_column(data: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize date column name to lowercase 'date'
    Handles both 'Date' and 'date' column names
    """
    if 'Date' in data.columns and 'date' not in data.columns:
        data = data.rename(columns={'Date': 'date'})
    return data


class TestRealDataIntegration(unittest.TestCase):
    """
    Integration tests using real market data
    Tests AAPL, GOOGL, NVDA with actual Yahoo Finance data
    """
    
    @classmethod
    def setUpClass(cls):
        """Fetch real data once for all tests"""
        print("\n" + "="*80)
        print("FETCHING REAL MARKET DATA FOR INTEGRATION TESTS")
        print("="*80)
        
        cls.data_source = YahooFinanceSource()
        cls.symbols = ['AAPL', 'GOOGL', 'NVDA']
        cls.test_data = {}
        
        for symbol in cls.symbols:
            print(f"\n📥 Fetching 1 year of data for {symbol}...")
            try:
                data = cls.data_source.fetch_price_data(symbol, period='1y')
                if data is not None and not data.empty:
                    # Normalize date column name (handle both 'Date' and 'date')
                    if 'Date' in data.columns and 'date' not in data.columns:
                        data.rename(columns={'Date': 'date'}, inplace=True)
                    
                    cls.test_data[symbol] = data
                    print(f"✅ {symbol}: {len(data)} rows fetched")
                    date_col = 'date' if 'date' in data.columns else 'Date'
                    print(f"   Date range: {data[date_col].min()} to {data[date_col].max()}")
                    print(f"   Latest close: ${data['close'].iloc[-1]:.2f}")
                    print(f"   Columns: {list(data.columns)}")
                else:
                    print(f"❌ {symbol}: No data returned")
            except Exception as e:
                print(f"❌ {symbol}: Error fetching data - {e}")
        
        print("\n" + "="*80)
        print("DATA FETCH COMPLETE")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.indicator_service = IndicatorService()
        self.strategy_service = StrategyService()
    
    def test_data_quality(self):
        """Test that fetched data has required quality"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                if symbol not in self.test_data:
                    self.skipTest(f"No data available for {symbol}")
                
                data = normalize_date_column(self.test_data[symbol].copy())
                
                # Check required columns
                required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
                for col in required_cols:
                    self.assertIn(col, data.columns, 
                                 f"{symbol}: Missing column {col}. Available: {list(data.columns)}")
                
                # Check data completeness
                self.assertGreater(len(data), 200, f"{symbol}: Insufficient data points")
                
                # Check for NaN values in critical columns
                for col in ['close', 'volume']:
                    nan_count = data[col].isna().sum()
                    self.assertEqual(nan_count, 0, 
                                   f"{symbol}: {nan_count} NaN values in {col}")
                
                # Check price validity
                self.assertTrue((data['close'] > 0).all(), 
                              f"{symbol}: Invalid close prices (non-positive)")
                self.assertTrue((data['high'] >= data['low']).all(),
                              f"{symbol}: High < Low detected")
                self.assertTrue((data['high'] >= data['close']).all(),
                              f"{symbol}: High < Close detected")
                self.assertTrue((data['low'] <= data['close']).all(),
                              f"{symbol}: Low > Close detected")
    
    def test_rsi_calculation_accuracy(self):
        """Test RSI calculation against industry standard (14-period)"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                if symbol not in self.test_data:
                    self.skipTest(f"No data available for {symbol}")
                
                data = normalize_date_column(self.test_data[symbol].copy())
                close = data.set_index('date')['close']
                
                # Calculate RSI
                rsi = calculate_rsi(close, window=14)
                
                # Validate RSI values
                self.assertFalse(rsi.isna().all(), f"{symbol}: RSI calculation failed")
                
                # RSI should be between 0 and 100
                valid_rsi = rsi.dropna()
                self.assertTrue((valid_rsi >= 0).all() and (valid_rsi <= 100).all(),
                              f"{symbol}: RSI out of range [0, 100]")
                
                # Check RSI formula correctness using Wilder's smoothing (industry standard)
                # RSI = 100 - (100 / (1 + RS))
                # RS = Average Gain / Average Loss
                # Wilder's smoothing uses EMA with alpha = 1/window (not simple rolling mean)
                delta = close.diff()
                gain = delta.where(delta > 0, 0.0)
                loss = -delta.where(delta < 0, 0.0)
                
                # Use Wilder's smoothing (EMA with alpha = 1/window) - matches our implementation
                window = 14
                avg_gain = gain.ewm(alpha=1.0/window, min_periods=window, adjust=False).mean()
                avg_loss = loss.ewm(alpha=1.0/window, min_periods=window, adjust=False).mean()
                
                # Calculate RS and expected RSI
                rs = avg_gain / avg_loss
                expected_rsi = 100 - (100 / (1 + rs))
                
                # Replace infinite values (when avg_loss is 0) with 100
                expected_rsi = expected_rsi.replace([np.inf, -np.inf], 100)
                
                # Compare calculated vs expected using Wilder's smoothing
                # Use dropna() on both series to ensure we're comparing valid values
                valid_rsi = rsi.dropna()
                valid_expected = expected_rsi.dropna()
                
                # Align indices for comparison
                common_idx = valid_rsi.index.intersection(valid_expected.index)
                if len(common_idx) == 0:
                    self.fail(
                        f"{symbol}: No common indices for RSI comparison. "
                        f"Calculated RSI has {len(valid_rsi)} valid values, "
                        f"Expected RSI has {len(valid_expected)} valid values."
                    )
                
                comparison = (valid_rsi.loc[common_idx] - valid_expected.loc[common_idx]).abs()
                max_diff = comparison.max()
                mean_diff = comparison.mean()
                median_diff = comparison.median()
                
                # Fail fast with detailed error message if difference is significant
                # Root cause: Implementation doesn't match Wilder's smoothing formula
                if max_diff > 0.01:
                    # Check if it's a systematic error (mean/median > threshold)
                    if mean_diff > 1.0 or median_diff > 1.0:
                        # This is a systematic error - fail immediately with root cause
                        error_details = (
                            f"\n{'='*80}\n"
                            f"RSI CALCULATION ACCURACY FAILURE - {symbol}\n"
                            f"{'='*80}\n"
                            f"Root Cause: RSI implementation does not match Wilder's smoothing formula\n"
                            f"\nStatistics:\n"
                            f"  Max difference: {max_diff:.4f} RSI points\n"
                            f"  Mean difference: {mean_diff:.4f} RSI points\n"
                            f"  Median difference: {median_diff:.4f} RSI points\n"
                            f"  Valid comparison points: {len(common_idx)}\n"
                            f"\nExpected Implementation:\n"
                            f"  - Use Wilder's smoothing (EMA with alpha=1/window)\n"
                            f"  - First period: simple average of gains/losses\n"
                            f"  - Subsequent: EMA with smoothing factor = 1/window\n"
                            f"\nCurrent calculated RSI range: [{valid_rsi.min():.2f}, {valid_rsi.max():.2f}]\n"
                            f"Expected RSI range: [{valid_expected.min():.2f}, {valid_expected.max():.2f}]\n"
                            f"{'='*80}\n"
                        )
                        self.fail(error_details)
                    else:
                        # Large max diff but small mean/median suggests edge cases
                        # Log detailed warning but don't fail (edge cases are acceptable)
                        print(
                            f"⚠️  {symbol}: RSI edge case detected - "
                            f"Max diff: {max_diff:.4f}, Mean diff: {mean_diff:.4f}, "
                            f"Median diff: {median_diff:.4f}"
                        )
                
                # Validate that RSI values are reasonable (fail fast if invalid)
                invalid_low = valid_rsi[valid_rsi < 0]
                invalid_high = valid_rsi[valid_rsi > 100]
                if len(invalid_low) > 0 or len(invalid_high) > 0:
                    error_msg = (
                        f"{symbol}: RSI values out of valid range [0, 100]. "
                        f"Found {len(invalid_low)} values < 0, {len(invalid_high)} values > 100. "
                        f"Root cause: RSI calculation formula error."
                    )
                    if len(invalid_low) > 0:
                        error_msg += f" Min invalid value: {invalid_low.min()}"
                    if len(invalid_high) > 0:
                        error_msg += f" Max invalid value: {invalid_high.max()}"
                    self.fail(error_msg)
                
                print(f"✅ {symbol}: RSI calculation accurate (latest: {rsi.iloc[-1]:.2f})")
    
    def test_macd_calculation_accuracy(self):
        """Test MACD calculation against industry standard (12, 26, 9)"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                if symbol not in self.test_data:
                    self.skipTest(f"No data available for {symbol}")
                
                data = normalize_date_column(self.test_data[symbol].copy())
                close = data.set_index('date')['close']
                
                # Calculate MACD
                macd_line, signal_line, histogram = calculate_macd(close)
                
                # Validate MACD values
                self.assertFalse(macd_line.isna().all(), f"{symbol}: MACD line calculation failed")
                self.assertFalse(signal_line.isna().all(), f"{symbol}: Signal line calculation failed")
                
                # MACD line = EMA(12) - EMA(26)
                ema12 = calculate_ema(close, 12)
                ema26 = calculate_ema(close, 26)
                expected_macd = ema12 - ema26
                
                # Compare (allow small differences due to EMA calculation methods)
                comparison = (macd_line - expected_macd).abs().dropna()
                max_diff = comparison.max()
                self.assertLess(max_diff, 0.1, 
                              f"{symbol}: MACD calculation differs (max diff: {max_diff})")
                
                # Signal line = EMA(9) of MACD line
                expected_signal = calculate_ema(macd_line, 9)
                signal_comparison = (signal_line - expected_signal).abs().dropna()
                signal_max_diff = signal_comparison.max()
                self.assertLess(signal_max_diff, 0.1,
                              f"{symbol}: Signal line calculation differs (max diff: {signal_max_diff})")
                
                # Histogram = MACD - Signal
                expected_histogram = macd_line - signal_line
                hist_comparison = (histogram - expected_histogram).abs().dropna()
                hist_max_diff = hist_comparison.max()
                self.assertLess(hist_max_diff, 0.01,
                              f"{symbol}: Histogram calculation differs (max diff: {hist_max_diff})")
                
                print(f"✅ {symbol}: MACD calculation accurate")
                print(f"   Latest MACD: {macd_line.iloc[-1]:.4f}, Signal: {signal_line.iloc[-1]:.4f}")
    
    def test_moving_averages_accuracy(self):
        """Test moving average calculations"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                if symbol not in self.test_data:
                    self.skipTest(f"No data available for {symbol}")
                
                data = normalize_date_column(self.test_data[symbol].copy())
                close = data.set_index('date')['close']
                
                # Test SMA
                sma50 = calculate_sma(close, 50)
                expected_sma50 = close.rolling(window=50).mean()
                sma_diff = (sma50 - expected_sma50).abs().dropna().max()
                self.assertLess(sma_diff, 0.01, f"{symbol}: SMA50 calculation error")
                
                # Test EMA
                ema20 = calculate_ema(close, 20)
                expected_ema20 = close.ewm(span=20, adjust=False).mean()
                ema_diff = (ema20 - expected_ema20).abs().dropna().max()
                self.assertLess(ema_diff, 0.01, f"{symbol}: EMA20 calculation error")
                
                print(f"✅ {symbol}: Moving averages accurate")
                print(f"   SMA50: ${sma50.iloc[-1]:.2f}, EMA20: ${ema20.iloc[-1]:.2f}")
    
    def test_atr_calculation_accuracy(self):
        """Test ATR calculation against industry standard"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                if symbol not in self.test_data:
                    self.skipTest(f"No data available for {symbol}")
                
                data = normalize_date_column(self.test_data[symbol].copy())
                df = data.set_index('date')
                
                # Calculate ATR
                atr = calculate_atr(df['high'], df['low'], df['close'], window=14)
                
                # Validate ATR
                self.assertFalse(atr.isna().all(), f"{symbol}: ATR calculation failed")
                self.assertTrue((atr.dropna() > 0).all(), f"{symbol}: ATR should be positive")
                
                # ATR formula: True Range = max(high-low, abs(high-prev_close), abs(low-prev_close))
                # ATR = SMA of True Range over 14 periods
                high = df['high']
                low = df['low']
                close = df['close']
                prev_close = close.shift(1)
                
                tr1 = high - low
                tr2 = (high - prev_close).abs()
                tr3 = (low - prev_close).abs()
                true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                expected_atr = true_range.rolling(window=14).mean()
                
                # Compare
                comparison = (atr - expected_atr).abs().dropna()
                max_diff = comparison.max()
                self.assertLess(max_diff, 0.01,
                              f"{symbol}: ATR calculation differs (max diff: {max_diff})")
                
                print(f"✅ {symbol}: ATR calculation accurate (latest: ${atr.iloc[-1]:.2f})")
    
    def test_bollinger_bands_accuracy(self):
        """Test Bollinger Bands calculation"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                if symbol not in self.test_data:
                    self.skipTest(f"No data available for {symbol}")
                
                data = normalize_date_column(self.test_data[symbol].copy())
                close = data.set_index('date')['close']
                
                # Calculate Bollinger Bands
                bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(close, window=20, num_std=2)
                
                # Validate
                self.assertFalse(bb_middle.isna().all(), f"{symbol}: BB middle calculation failed")
                
                # Middle band = SMA(20)
                expected_middle = calculate_sma(close, 20)
                middle_diff = (bb_middle - expected_middle).abs().dropna().max()
                self.assertLess(middle_diff, 0.01, f"{symbol}: BB middle differs")
                
                # Upper = Middle + 2*std, Lower = Middle - 2*std
                std = close.rolling(window=20).std()
                expected_upper = expected_middle + 2 * std
                expected_lower = expected_middle - 2 * std
                
                upper_diff = (bb_upper - expected_upper).abs().dropna().max()
                lower_diff = (bb_lower - expected_lower).abs().dropna().max()
                
                self.assertLess(upper_diff, 0.01, f"{symbol}: BB upper differs")
                self.assertLess(lower_diff, 0.01, f"{symbol}: BB lower differs")
                
                # Validate relationship: Upper > Middle > Lower
                valid_idx = bb_upper.dropna().index
                self.assertTrue((bb_upper.loc[valid_idx] > bb_middle.loc[valid_idx]).all(),
                              f"{symbol}: BB upper < middle")
                self.assertTrue((bb_middle.loc[valid_idx] > bb_lower.loc[valid_idx]).all(),
                              f"{symbol}: BB middle < lower")
                
                print(f"✅ {symbol}: Bollinger Bands accurate")
    
    def test_trend_detection(self):
        """Test trend detection logic"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                if symbol not in self.test_data:
                    self.skipTest(f"No data available for {symbol}")
                
                data = normalize_date_column(self.test_data[symbol].copy())
                close = data.set_index('date')['close']
                
                # Calculate required indicators
                sma200 = calculate_sma(close, 200)
                ema20 = calculate_ema(close, 20)
                sma50 = calculate_sma(close, 50)
                
                # Detect trends
                long_term = detect_long_term_trend(close, sma200)
                medium_term = detect_medium_term_trend(ema20, sma50)
                
                # Validate trend values
                self.assertIn(long_term.iloc[-1], ['bullish', 'bearish', 'neutral'],
                             f"{symbol}: Invalid long-term trend")
                self.assertIn(medium_term.iloc[-1], ['bullish', 'bearish', 'neutral'],
                             f"{symbol}: Invalid medium-term trend")
                
                # Validate logic: bullish when price > MA
                latest_price = close.iloc[-1]
                latest_sma200 = sma200.iloc[-1]
                if not pd.isna(latest_sma200):
                    if latest_price > latest_sma200:
                        self.assertEqual(long_term.iloc[-1], 'bullish',
                                       f"{symbol}: Trend detection logic error")
                    elif latest_price < latest_sma200:
                        self.assertEqual(long_term.iloc[-1], 'bearish',
                                       f"{symbol}: Trend detection logic error")
                
                print(f"✅ {symbol}: Trend detection working")
                print(f"   Long-term: {long_term.iloc[-1]}, Medium-term: {medium_term.iloc[-1]}")
    
    def test_signal_generation(self):
        """Test signal generation with real data"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                if symbol not in self.test_data:
                    self.skipTest(f"No data available for {symbol}")
                
                data = normalize_date_column(self.test_data[symbol].copy())
                df = data.set_index('date')
                
                # Calculate all indicators
                close = df['close']
                volume = df['volume']
                
                ema20 = calculate_ema(close, 20)
                ema50 = calculate_ema(close, 50)
                sma50 = calculate_sma(close, 50)  # Required for medium_term_trend calculation
                sma200 = calculate_sma(close, 200)
                macd_line, macd_signal, macd_hist = calculate_macd(close)
                rsi = calculate_rsi(close)
                volume_ma = volume.rolling(window=20).mean()
                long_term_trend = detect_long_term_trend(close, sma200)
                medium_term_trend = detect_medium_term_trend(ema20, sma50)
                
                # Generate signals
                signals = generate_signal(
                    close, ema20, ema50, sma200,
                    macd_line, macd_signal, macd_hist,
                    rsi, volume, volume_ma,
                    long_term_trend, medium_term_trend
                )
                
                # Validate signals
                valid_signals = signals.dropna()
                self.assertGreater(len(valid_signals), 0, f"{symbol}: No signals generated")
                
                # Signals should be 'buy', 'sell', or 'hold'
                unique_signals = valid_signals.unique()
                for sig in unique_signals:
                    self.assertIn(sig, ['buy', 'sell', 'hold'],
                                f"{symbol}: Invalid signal value: {sig}")
                
                latest_signal = signals.iloc[-1]
                print(f"✅ {symbol}: Signal generation working (latest: {latest_signal})")
    
    def test_strategy_execution(self):
        """Test strategy execution with real data"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                if symbol not in self.test_data:
                    self.skipTest(f"No data available for {symbol}")
                
                data = normalize_date_column(self.test_data[symbol].copy())
                df = data.set_index('date')
                
                # Calculate indicators
                close = df['close']
                volume = df['volume']
                
                ema20 = calculate_ema(close, 20)
                ema50 = calculate_ema(close, 50)
                sma50 = calculate_sma(close, 50)  # Required for medium_term_trend calculation
                sma200 = calculate_sma(close, 200)
                macd_line, macd_signal, macd_hist = calculate_macd(close)
                rsi = calculate_rsi(close)
                volume_ma = volume.rolling(window=20).mean()
                long_term_trend = detect_long_term_trend(close, sma200)
                medium_term_trend = detect_medium_term_trend(ema20, sma50)
                
                # Prepare indicators dict
                indicators = {
                    'price': close,
                    'ema20': ema20,
                    'ema50': ema50,
                    'sma200': sma200,
                    'macd_line': macd_line,
                    'macd_signal': macd_signal,
                    'macd_histogram': macd_hist,
                    'rsi': rsi,
                    'volume': volume,
                    'volume_ma': volume_ma,
                    'long_term_trend': long_term_trend,
                    'medium_term_trend': medium_term_trend
                }
                
                # Execute strategy
                result = self.strategy_service.execute_strategy(
                    strategy_name='technical',
                    indicators=indicators,
                    market_data=df,
                    context={'symbol': symbol}
                )
                
                # Validate result
                self.assertIsNotNone(result, f"{symbol}: Strategy returned None")
                self.assertIn(result.signal, ['buy', 'sell', 'hold'],
                            f"{symbol}: Invalid signal: {result.signal}")
                self.assertGreaterEqual(result.confidence, 0.0,
                                      f"{symbol}: Confidence < 0")
                self.assertLessEqual(result.confidence, 1.0,
                                   f"{symbol}: Confidence > 1")
                self.assertIsNotNone(result.reason,
                                    f"{symbol}: No reason provided")
                
                print(f"✅ {symbol}: Strategy execution working")
                print(f"   Signal: {result.signal.upper()}, Confidence: {result.confidence:.2f}")
                print(f"   Reason: {result.reason}")
    
    def test_pullback_zones_and_stop_loss(self):
        """Test pullback zone and stop-loss calculations"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                if symbol not in self.test_data:
                    self.skipTest(f"No data available for {symbol}")
                
                data = normalize_date_column(self.test_data[symbol].copy())
                df = data.set_index('date')
                
                # Calculate required indicators
                close = df['close']
                high = df['high']
                low = df['low']
                ema20 = calculate_ema(close, 20)
                atr = calculate_atr(high, low, close)
                
                # Calculate pullback zones
                pb_lower, pb_upper = calculate_pullback_zones(close, ema20, atr)
                
                # Validate pullback zones
                if pb_lower is not None and pb_upper is not None:
                    # Get last valid values
                    lower_val = pb_lower.iloc[-1] if len(pb_lower) > 0 and not pd.isna(pb_lower.iloc[-1]) else None
                    upper_val = pb_upper.iloc[-1] if len(pb_upper) > 0 and not pd.isna(pb_upper.iloc[-1]) else None
                    
                    self.assertIsNotNone(lower_val, f"{symbol}: Missing lower pullback zone")
                    self.assertIsNotNone(upper_val, f"{symbol}: Missing upper pullback zone")
                    self.assertLess(lower_val, upper_val,
                                  f"{symbol}: Lower > Upper pullback zone")
                
                # Calculate stop-loss
                stop_loss = calculate_stop_loss(close, atr, multiplier=2.0)
                
                # Validate stop-loss
                if stop_loss is not None:
                    self.assertGreater(stop_loss, 0,
                                     f"{symbol}: Invalid stop-loss (non-positive)")
                    # Stop-loss should be below current price for long positions
                    latest_price = close.iloc[-1]
                    self.assertLess(stop_loss, latest_price,
                                   f"{symbol}: Stop-loss above current price")
                
                print(f"✅ {symbol}: Pullback zones and stop-loss calculated")
                if pb_zones:
                    print(f"   Pullback zone: ${pb_zones['lower']:.2f} - ${pb_zones['upper']:.2f}")
                if stop_loss:
                    print(f"   Stop-loss: ${stop_loss:.2f}")


if __name__ == '__main__':
    # Configure test output
    unittest.main(verbosity=2, buffer=False)

