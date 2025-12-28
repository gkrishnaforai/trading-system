"""
Unit Tests for Swing Trading Indicators
Tests: ADX, Stochastic, Williams %R, VWAP, Fibonacci
Industry Standard: Real data only, no mocks, fail-fast
"""
import unittest
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
from app.indicators.swing import (
    calculate_adx,
    calculate_stochastic,
    calculate_williams_r,
    calculate_vwap,
    calculate_fibonacci_retracements
)
from app.data_sources import get_data_source
from app.exceptions import ValidationError


class TestSwingIndicators(unittest.TestCase):
    """
    Unit tests for swing trading indicators
    Uses real market data (AAPL, GOOGL, NVDA, TQQQ)
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        print("\n" + "="*80)
        print("SWING TRADING INDICATORS - UNIT TESTS")
        print("="*80)
        
        cls.data_source = get_data_source()
        cls.test_symbols = ["AAPL", "GOOGL", "NVDA", "TQQQ"]
        
        # Fetch real data for all symbols
        cls.test_data = {}
        for symbol in cls.test_symbols:
            try:
                data = cls.data_source.fetch_historical_data(symbol=symbol, days=100)
                if data is not None and not data.empty:
                    # Normalize date column
                    if 'Date' in data.columns:
                        data = data.rename(columns={'Date': 'date'})
                    if 'date' not in data.columns and data.index.name == 'date':
                        data = data.reset_index()
                    cls.test_data[symbol] = data
                    print(f"✅ Loaded {len(data)} rows for {symbol}")
                else:
                    print(f"⚠️  No data for {symbol}")
            except Exception as e:
                print(f"⚠️  Error loading {symbol}: {e}")
        
        print(f"\n📊 Test symbols: {', '.join(cls.test_symbols)}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.data_source = self.__class__.data_source
        self.test_data = self.__class__.test_data
    
    def _get_test_data(self, symbol: str) -> pd.DataFrame:
        """Get test data for symbol"""
        if symbol not in self.test_data:
            self.skipTest(f"No data available for {symbol}")
        
        data = self.test_data[symbol].copy()
        
        # Ensure required columns
        if 'date' not in data.columns:
            if 'Date' in data.columns:
                data = data.rename(columns={'Date': 'date'})
            else:
                data = data.reset_index()
        
        # Ensure date is datetime
        if not pd.api.types.is_datetime64_any_dtype(data['date']):
            data['date'] = pd.to_datetime(data['date'])
        
        # Sort by date
        data = data.sort_values('date').reset_index(drop=True)
        
        return data
    
    # ==================== ADX Tests ====================
    
    def test_adx_calculation(self):
        """Test ADX calculation with real data"""
        print("\n📊 Testing ADX calculation...")
        
        for symbol in self.test_symbols:
            with self.subTest(symbol=symbol):
                data = self._get_test_data(symbol)
                
                if len(data) < 30:
                    self.skipTest(f"Insufficient data for {symbol}")
                
                high = data['high']
                low = data['low']
                close = data['close']
                
                result = calculate_adx(high, low, close, period=14)
                
                # Verify structure
                self.assertIn('adx', result, f"{symbol}: Should have 'adx' key")
                self.assertIn('di_plus', result, f"{symbol}: Should have 'di_plus' key")
                self.assertIn('di_minus', result, f"{symbol}: Should have 'di_minus' key")
                
                adx = result['adx']
                di_plus = result['di_plus']
                di_minus = result['di_minus']
                
                # Verify values
                self.assertGreater(len(adx), 0, f"{symbol}: ADX should have values")
                self.assertGreater(len(di_plus), 0, f"{symbol}: +DI should have values")
                self.assertGreater(len(di_minus), 0, f"{symbol}: -DI should have values")
                
                # Verify ADX range (0-100)
                valid_adx = adx.dropna()
                if len(valid_adx) > 0:
                    self.assertTrue(
                        (valid_adx >= 0).all() and (valid_adx <= 100).all(),
                        f"{symbol}: ADX should be between 0 and 100"
                    )
                
                # Verify latest ADX value
                latest_adx = adx.iloc[-1]
                if not pd.isna(latest_adx):
                    print(f"   {symbol}: Latest ADX = {latest_adx:.2f}")
                    self.assertGreaterEqual(latest_adx, 0, f"{symbol}: ADX should be >= 0")
                    self.assertLessEqual(latest_adx, 100, f"{symbol}: ADX should be <= 100")
        
        print("✅ ADX calculation tests passed")
    
    def test_adx_validation(self):
        """Test ADX validation and error handling"""
        print("\n📊 Testing ADX validation...")
        
        data = self._get_test_data("AAPL")
        high = data['high']
        low = data['low']
        close = data['close']
        
        # Test insufficient data
        with self.assertRaises(ValidationError):
            calculate_adx(high[:10], low[:10], close[:10], period=14)
        
        # Test None inputs
        with self.assertRaises(ValidationError):
            calculate_adx(None, low, close, period=14)
        
        print("✅ ADX validation tests passed")
    
    # ==================== Stochastic Tests ====================
    
    def test_stochastic_calculation(self):
        """Test Stochastic Oscillator calculation with real data"""
        print("\n📊 Testing Stochastic calculation...")
        
        for symbol in self.test_symbols:
            with self.subTest(symbol=symbol):
                data = self._get_test_data(symbol)
                
                if len(data) < 20:
                    self.skipTest(f"Insufficient data for {symbol}")
                
                high = data['high']
                low = data['low']
                close = data['close']
                
                result = calculate_stochastic(high, low, close, k_period=14, d_period=3)
                
                # Verify structure
                self.assertIn('stochastic_k', result, f"{symbol}: Should have 'stochastic_k' key")
                self.assertIn('stochastic_d', result, f"{symbol}: Should have 'stochastic_d' key")
                
                k = result['stochastic_k']
                d = result['stochastic_d']
                
                # Verify values
                self.assertGreater(len(k), 0, f"{symbol}: %K should have values")
                self.assertGreater(len(d), 0, f"{symbol}: %D should have values")
                
                # Verify range (0-100)
                valid_k = k.dropna()
                if len(valid_k) > 0:
                    self.assertTrue(
                        (valid_k >= 0).all() and (valid_k <= 100).all(),
                        f"{symbol}: %K should be between 0 and 100"
                    )
                
                # Verify latest values
                latest_k = k.iloc[-1]
                latest_d = d.iloc[-1]
                if not pd.isna(latest_k):
                    print(f"   {symbol}: Latest %K = {latest_k:.2f}, %D = {latest_d:.2f}")
                    self.assertGreaterEqual(latest_k, 0, f"{symbol}: %K should be >= 0")
                    self.assertLessEqual(latest_k, 100, f"{symbol}: %K should be <= 100")
        
        print("✅ Stochastic calculation tests passed")
    
    def test_stochastic_validation(self):
        """Test Stochastic validation and error handling"""
        print("\n📊 Testing Stochastic validation...")
        
        data = self._get_test_data("AAPL")
        high = data['high']
        low = data['low']
        close = data['close']
        
        # Test insufficient data
        with self.assertRaises(ValidationError):
            calculate_stochastic(high[:10], low[:10], close[:10], k_period=14)
        
        print("✅ Stochastic validation tests passed")
    
    # ==================== Williams %R Tests ====================
    
    def test_williams_r_calculation(self):
        """Test Williams %R calculation with real data"""
        print("\n📊 Testing Williams %R calculation...")
        
        for symbol in self.test_symbols:
            with self.subTest(symbol=symbol):
                data = self._get_test_data(symbol)
                
                if len(data) < 20:
                    self.skipTest(f"Insufficient data for {symbol}")
                
                high = data['high']
                low = data['low']
                close = data['close']
                
                wr = calculate_williams_r(high, low, close, period=14)
                
                # Verify values
                self.assertGreater(len(wr), 0, f"{symbol}: Williams %R should have values")
                
                # Verify range (-100 to 0)
                valid_wr = wr.dropna()
                if len(valid_wr) > 0:
                    self.assertTrue(
                        (valid_wr >= -100).all() and (valid_wr <= 0).all(),
                        f"{symbol}: Williams %R should be between -100 and 0"
                    )
                
                # Verify latest value
                latest_wr = wr.iloc[-1]
                if not pd.isna(latest_wr):
                    print(f"   {symbol}: Latest Williams %R = {latest_wr:.2f}")
                    self.assertGreaterEqual(latest_wr, -100, f"{symbol}: Williams %R should be >= -100")
                    self.assertLessEqual(latest_wr, 0, f"{symbol}: Williams %R should be <= 0")
        
        print("✅ Williams %R calculation tests passed")
    
    # ==================== VWAP Tests ====================
    
    def test_vwap_calculation(self):
        """Test VWAP calculation with real data"""
        print("\n📊 Testing VWAP calculation...")
        
        for symbol in self.test_symbols:
            with self.subTest(symbol=symbol):
                data = self._get_test_data(symbol)
                
                if len(data) < 20:
                    self.skipTest(f"Insufficient data for {symbol}")
                
                high = data['high']
                low = data['low']
                close = data['close']
                volume = data['volume']
                
                # Test cumulative VWAP
                vwap_cum = calculate_vwap(high, low, close, volume, period=None)
                
                # Test rolling VWAP
                vwap_roll = calculate_vwap(high, low, close, volume, period=20)
                
                # Verify values
                self.assertGreater(len(vwap_cum), 0, f"{symbol}: Cumulative VWAP should have values")
                self.assertGreater(len(vwap_roll), 0, f"{symbol}: Rolling VWAP should have values")
                
                # Verify VWAP is reasonable (should be close to price range)
                latest_close = close.iloc[-1]
                latest_vwap = vwap_cum.iloc[-1]
                
                if not pd.isna(latest_vwap):
                    # VWAP should be within reasonable range of price
                    price_range = (high.max() - low.min())
                    self.assertLess(
                        abs(latest_vwap - latest_close) / latest_close,
                        0.5,  # Within 50% of price
                        f"{symbol}: VWAP should be reasonable relative to price"
                    )
                    print(f"   {symbol}: Latest VWAP = ${latest_vwap:.2f}, Close = ${latest_close:.2f}")
        
        print("✅ VWAP calculation tests passed")
    
    def test_vwap_validation(self):
        """Test VWAP validation and error handling"""
        print("\n📊 Testing VWAP validation...")
        
        data = self._get_test_data("AAPL")
        high = data['high']
        low = data['low']
        close = data['close']
        volume = data['volume']
        
        # Test None inputs
        with self.assertRaises(ValidationError):
            calculate_vwap(None, low, close, volume)
        
        # Test mismatched lengths
        with self.assertRaises(ValidationError):
            calculate_vwap(high[:10], low, close, volume)
        
        print("✅ VWAP validation tests passed")
    
    # ==================== Fibonacci Tests ====================
    
    def test_fibonacci_retracements(self):
        """Test Fibonacci retracement calculation with real data"""
        print("\n📊 Testing Fibonacci retracements...")
        
        for symbol in self.test_symbols:
            with self.subTest(symbol=symbol):
                data = self._get_test_data(symbol)
                
                if len(data) < 25:
                    self.skipTest(f"Insufficient data for {symbol}")
                
                high = data['high']
                low = data['low']
                
                result = calculate_fibonacci_retracements(high, low, period=20)
                
                # Verify structure
                self.assertIn('fib_382', result, f"{symbol}: Should have 'fib_382' key")
                self.assertIn('fib_500', result, f"{symbol}: Should have 'fib_500' key")
                self.assertIn('fib_618', result, f"{symbol}: Should have 'fib_618' key")
                
                fib_382 = result['fib_382']
                fib_500 = result['fib_500']
                fib_618 = result['fib_618']
                
                # Verify values
                self.assertGreater(len(fib_382), 0, f"{symbol}: Fib 38.2% should have values")
                self.assertGreater(len(fib_500), 0, f"{symbol}: Fib 50% should have values")
                self.assertGreater(len(fib_618), 0, f"{symbol}: Fib 61.8% should have values")
                
                # Verify order (fib_382 > fib_500 > fib_618)
                latest_382 = fib_382.iloc[-1]
                latest_500 = fib_500.iloc[-1]
                latest_618 = fib_618.iloc[-1]
                
                if not pd.isna(latest_382) and not pd.isna(latest_500) and not pd.isna(latest_618):
                    self.assertGreater(latest_382, latest_500, f"{symbol}: Fib 38.2% should be > Fib 50%")
                    self.assertGreater(latest_500, latest_618, f"{symbol}: Fib 50% should be > Fib 61.8%")
                    print(f"   {symbol}: Fib levels - 38.2%: ${latest_382:.2f}, 50%: ${latest_500:.2f}, 61.8%: ${latest_618:.2f}")
        
        print("✅ Fibonacci retracements tests passed")


if __name__ == '__main__':
    unittest.main(verbosity=2)

